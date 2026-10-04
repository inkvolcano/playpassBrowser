#!/usr/bin/env python3
"""Look up every game in data/games.json on the Google Play Store.

For each game: search() -> pick the best match -> app() when the match has
fewer than 2 screenshots or needs checking. Results go to data/shots_cache.json
(keyed by game title) so a rerun resumes where the last one stopped. At the end
index.html is rebuilt.

How a match is chosen
- Every search hit is scored 0-1 on title similarity, minus penalties for
  Lite/Free/Demo editions, Netflix/Crunchyroll editions, companion apps (guides, save
  editors, trackers...), different sequel numbers, a developer that doesn't
  match a "... by <developer>" title, and non-game categories.
- The Play Store badges Play Pass apps: the top search card carries the badge,
  and app() reads it from the details page.
- confidence "verified": badged and the title matches well.
  confidence "strong":   near-exact distinctive title, no red flags, no badge.
  Anything else is retried with tweaked queries (subtitle dropped, developer
  added, ...). Generic titles ("Word Search", "Baby Games for 2-5 Year Olds")
  must be verified. Whatever is still doubtful is stored with appId null, so
  the page shows a placeholder instead of the wrong game.
- data/overrides.json pins a title to an appId, or to null, by hand.

    python3 fill_screenshots.py                      # resume: look up games not in the cache
    python3 fill_screenshots.py --recheck doubtful   # redo nulls and unverified matches
    python3 fill_screenshots.py --only "Mini Metro"  # (re)do specific titles
    python3 fill_screenshots.py --refresh            # re-read every matched app: all
                                                     # screenshots + today's Play Pass status
    python3 fill_screenshots.py --region nl          # which matched apps the Dutch Play Store offers
"""
import argparse
import json
import random
import re
import ssl
import subprocess
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlparse

from google_play_scraper import app as gp_app
from google_play_scraper.constants.element import ElementSpec, ElementSpecs
from google_play_scraper.constants.regex import Regex
from google_play_scraper.constants.request import Formats
from google_play_scraper.exceptions import ExtraHTTPError, NotFoundError
from google_play_scraper.utils.request import get

# google-play-scraper switches off TLS certificate checks for the whole process
# when imported. Switch them back on.
ssl._create_default_https_context = ssl.create_default_context

ROOT = Path(__file__).resolve().parent
GAMES_JSON = ROOT / "data" / "games.json"
CACHE_JSON = ROOT / "data" / "shots_cache.json"
OVERRIDES_JSON = ROOT / "data" / "overrides.json"

MAX_SHOTS = 24         # screenshots kept per game
VERIFY_MIN = 0.6       # score needed with a Play Pass badge
STRONG_MIN = 0.9       # score needed without one
CANDIDATE_MIN = 0.45   # hits below this are never considered
DETAIL_CHECKS = 3      # app() calls per search to look for the badged edition


# ---------------------------------------------------------------- library fixes

def _details_id(url):
    if not isinstance(url, str) or "details?id=" not in url:
        return None
    return (parse_qs(urlparse(url).query).get("id") or [None])[0]


def _first_details_id(node):
    if isinstance(node, str):
        return _details_id(node)
    if isinstance(node, list):
        for x in node:
            found = _first_details_id(x)
            if found:
                return found
    return None


def _top_card_id(card):
    try:
        found = _details_id(card[41][0][2])
    except (IndexError, TypeError):
        found = None
    return found or _first_details_id(card)


def _has_badge(node):
    return "playpass_family" in json.dumps(node)


# 1.2.7 reads the top search card's appId from [11,0,0], which Google no longer
# fills, so the best hit comes back as None. Its store link is at [2,41,0,2].
ElementSpecs.SearchResultOnTop["appId"] = ElementSpec(None, [2], _top_card_id)
# Play Pass badge: top search card and details page (same field, index 94).
ElementSpecs.SearchResultOnTop["playPass"] = ElementSpec(None, [2, 94], _has_badge, False)
ElementSpecs.Detail["playPass"] = ElementSpec(5, [1, 2, 94], _has_badge, False)


def _nested(obj, *path):
    for i in path:
        try:
            obj = obj[i]
        except (IndexError, KeyError, TypeError):
            return None
    return obj


def gp_search(query, lang, country, n_hits=10, fallback=True):
    """google_play_scraper.search() with sturdier parsing: 1.2.7 crashes when a
    "Showing results for ..." section comes before the results. The library's
    fallback URL drops the country, so region checks switch it off."""
    try:
        dom = get(Formats.Searchresults.build(query=quote(query), lang=lang, country=country))
    except NotFoundError:
        if not fallback:
            raise
        dom = get(Formats.Searchresults.fallback_build(query=quote(query), lang=lang))
    ds = {}
    for m in Regex.SCRIPT.findall(dom):
        k, v = Regex.KEY.findall(m), Regex.VALUE.findall(m)
        if k and v:
            ds[k[0]] = json.loads(v[0])
    sections = _nested(ds, "ds:4", 0, 1) or []
    top = next((c for c in (_nested(s, 23, 16) for s in sections) if c), None)
    items = next((i for i in (_nested(s, 22, 0) for s in sections) if i), [])
    hits = [dict({k: spec.extract_content(top) for k, spec in ElementSpecs.SearchResultOnTop.items()}, top=True)] if top else []
    hits += [dict({k: spec.extract_content(it) for k, spec in ElementSpecs.SearchResult.items()}, top=False, playPass=None)
             for it in items]
    return hits[:n_hits]


# ---------------------------------------------------------------- requests

class Blocked(Exception):
    """403 from the proxy / Play Store, or failures that outlast the backoff."""


class Throttle:
    def __init__(self, delay):
        self.delay, self.last = delay, 0.0

    def wait(self):
        gap = self.delay * random.uniform(0.7, 1.3) - (time.monotonic() - self.last)
        if gap > 0:
            time.sleep(gap)
        self.last = time.monotonic()


THROTTLE = Throttle(0.6)
_tls = threading.local()  # parallel region checks give each thread its own throttle
_app_memo = {}


def _call(fn, *args, **kw):
    """Throttled call; backs off on 429/5xx/network errors. NotFoundError passes through."""
    throttle = getattr(_tls, "throttle", None) or THROTTLE
    for backoff in (10, 30, 90, None):
        throttle.wait()
        try:
            return fn(*args, **kw)
        except NotFoundError:
            raise
        except (ExtraHTTPError, URLError, TimeoutError, ConnectionError) as e:
            m = re.search(r"Status code (\d+)", str(e))
            if m and m.group(1) == "403":
                raise Blocked(f"HTTP 403 from {fn.__name__}: {e}")
            if backoff is None:
                raise Blocked(f"{fn.__name__} still failing after retries: {e}")
            print(f"    ! {type(e).__name__}: {e} - retrying in {backoff}s", flush=True)
            time.sleep(backoff)


def search_hits(query, lang, country):
    try:
        hits = _call(gp_search, query, lang, country)
    except NotFoundError:
        return []
    except Blocked:
        raise
    except Exception as e:  # layout surprises
        print(f"    ! search({query!r}) failed: {type(e).__name__}: {e}", flush=True)
        return []
    # "score" is the store's star rating here; matching reuses that key for its own score
    return [dict(h, rank=rank, query=query, rating=h.get("score")) for rank, h in enumerate(hits) if h.get("appId")]


def app_details(app_id, lang, country):
    key = (app_id, lang, country)
    if key not in _app_memo:
        try:
            _app_memo[key] = _call(gp_app, app_id, lang=lang, country=country)
        except NotFoundError:
            _app_memo[key] = None
        except Blocked:
            raise
        except Exception as e:
            print(f"    ! app({app_id}) failed: {type(e).__name__}: {e}", flush=True)
            _app_memo[key] = None
    return _app_memo[key]


# ---------------------------------------------------------------- matching

CJK_RE = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")
SUBTITLE_RE = re.compile(r"\s*(?::|\s[-–—|~]\s|\(|\[|：)\s*")
BY_RE = re.compile(r"^(.*\S)\s+by\s+(\S.*)$", re.I)
EDITION_RE = re.compile(r"\b(lite|free|demo|trial|ad supported)\b")
COMPANION_RE = re.compile(
    r"\b(guide|guides|walkthrough|tips|tricks|cheats?|hints?|wiki|companion|save editor|editor|"
    r"tracker|wallpapers?|mods?|maps? for|skins? for|calculator|soundboard|ringtones?|stickers?|"
    r"launcher|checklist|fan app|unofficial)\b")
ROMAN = {"ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}
NON_GAME_GENRES = {"Tools", "Books & Reference", "Personalization", "Communication", "Social",
                   "Video Players & Editors", "Productivity", "Comics", "Libraries & Demo",
                   "Lifestyle", "Photography", "Business", "Finance", "News & Magazines"}
GENERIC_WORDS = set("""
a an the and or of for with in on to at my your our first little big super mega new
game games puzzle puzzles kids kid children child toddler toddlers baby babies preschool
kindergarten boys girls boy girl year years old olds age ages learn learning educational
education school fun free classic offline simple easy best pro premium plus hd deluxe 2d 3d
edition collection pack word words search find crossword crosswords sudoku solitaire card cards
chess checkers draughts mahjong mahjongg jigsaw brain training teaser logic math maths number
numbers letter letters alphabet abc phonics reading spelling animal animals coloring colouring
color colors colours draw drawing paint painting music piano drum drums song songs car cars
truck trucks train trains cooking kitchen doctor dress up princess farm zoo dinosaur dinosaurs
memory match matching shapes sorting counting connect dot dots pop balloon bubble bubbles tap
block blocks tile tiles merge idle tycoon simulator quiz trivia riddle riddles hangman
minesweeper nonogram nonograms picross sokoban snake pool billiards bowling darts golf bingo
dice domino dominoes backgammon reversi othello spider freecell klondike pyramid tripeaks hearts
spades euchre rummy cribbage blackjack poker yahtzee 2048 maze mazes escape room hidden object
objects difference differences sticker stickers story stories book books english spanish
about how what where who is it this that all me you we lets let go play time
adult adults senior seniors family teen teens relax relaxing daily unlimited challenge
challenges master mania blast christmas xmas halloween easter santa holiday spooky concentration
nail nails salon hair makeup makeover fashion spa beauty art arts craft crafts pet pets house
home design dream dreams mandala mandalas ludo carrom parcheesi full complete version remastered
definitive
""".split()) | {str(n) for n in range(21)}
YEAR_RE = re.compile(r"19[5-9]\d|20[0-3]\d")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("&", " and ").replace("’", "'").replace("'", "").replace("×", "x")
    s = re.sub(r"[\W_]+", " ", s)
    return " ".join(s.split())


def base(title):
    """Main title without subtitle; a leading tag like "[Premium]" is skipped."""
    title = re.sub(r"^\s*[\[(][^\])]*[\])]\s*", "", title or "")
    return SUBTITLE_RE.split(title, 1)[0]


def spelling(title):
    """Case/space/dash-insensitive but punctuation-sensitive form, to break ties
    between same-named apps ("Toddler Games for 3 Year Olds+" vs "...olds")."""
    t = re.sub(r"[‐-―]", "-", (title or "").casefold())
    return " ".join(t.split())


AGES_RE = re.compile(r"\b(\d+)\s*(?:[-–]\s*(\d+)|\+)")  # "3-8", "2 - 5", "3+"


def ages(title):
    return {m.group(0).replace(" ", "").replace("–", "-") for m in AGES_RE.finditer(title or "")}


def numbers(title):
    toks = norm(AGES_RE.sub(" ", title or "")).split()
    # a lone "i" after the first word is a numeral ("Alphadia I & II"), not the pronoun
    toks = ["1" if t == "i" and k else t for k, t in enumerate(toks)]
    return {ROMAN.get(t, t) for t in toks if (t.isdigit() or t in ROMAN) and not YEAR_RE.fullmatch(t)}


def number_mismatch(game_title, cand_title):
    """Sequel numbers differ: the list title's numbers must all appear in the
    candidate, and the candidate's main title may not add any (bar a "1").
    Age ranges ("kids 3-8") only count when both titles have one."""
    want = numbers(game_title)
    if want - numbers(cand_title) or numbers(base(cand_title)) - want - {"1"}:
        return True
    a, b = ages(game_title), ages(cand_title)
    return bool(a and b and a != b)


def developer_hint(title):
    """("Crossword", "Teazel Ltd") for "Crossword by Teazel Ltd"; None for names
    like "Color by Number – Pixel Art", "Murder by Numbers" or "Stand by Me"."""
    m = BY_RE.match(title)
    if not m or SUBTITLE_RE.search(m.group(2)):
        return None
    first = (norm(m.group(2)).split() or [""])[0]
    return None if first in {"number", "numbers", "me", "night", "day", "step", "the"} else (m.group(1), m.group(2))


def is_generic(title):
    hint = developer_hint(title)
    toks = norm(base(hint[0] if hint else title)).split()
    return bool(toks) and all(t in GENERIC_WORDS for t in toks)


def missing_words(game_title, cand_title, cand_dev=""):
    """Distinctive words of the list title that the candidate lacks ("Bob" in
    "Bob Jigsaw Puzzles for Kids" vs "Jigsaw Puzzles for Kids"). Typos pass, and
    so do words from the developer's name ("ElePant Car games" by ElePant)."""
    hint = developer_hint(game_title)
    words = norm(cand_title).split()
    have = words + norm(cand_dev).split()
    compounds = {"".join(words[i:j]) for i in range(len(words)) for j in range(i + 2, len(words) + 1)}  # "mini games"
    mine = norm(hint[0] if hint else game_title).split()
    joined = {k for i in range(len(mine)) for j in range(i + 2, len(mine) + 1)  # "off road" vs "offroad"
              if "".join(mine[i:j]) in words for k in range(i, j)}
    return [w for k, w in enumerate(mine)
            if k not in joined and w not in GENERIC_WORDS and w not in compounds
            and not any(SequenceMatcher(None, w, h).ratio() >= 0.8 for h in have)]


def similarity(a_title, b_title):
    a, b = norm(a_title), norm(b_title)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ba, bb = norm(base(a_title)), norm(base(b_title))
    r = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    r = max(r, (len(ta & tb) / len(ta) + len(ta & tb) / len(ta | tb)) / 2)
    if a == bb:
        r = max(r, 0.95)   # candidate = list title + subtitle
    elif b == ba:
        r = max(r, 0.93)   # list title = candidate title + subtitle
    elif ba == bb and not is_generic(ba):
        r = max(r, 0.88)   # same name, different subtitles
    else:
        short, long_ = sorted((a, b), key=len)
        rest = long_[len(short):].strip()
        if long_.startswith(short + " ") and not is_generic(short) and not re.match(r"(\d|ii|iii|iv|vi)\b", rest):
            r = max(r, 0.85)
    return r


def assess(game_title, c, game_genre):
    """Score a candidate (search hit or app details) against a list title."""
    t, dev = c.get("title") or "", c.get("developer") or ""
    nt, na = norm(t), norm(game_title)
    sim = similarity(game_title, t)
    flags = []
    hint = developer_hint(game_title)
    if hint and f"by {norm(hint[1])}" not in nt:  # the candidate may carry "by X" in its own name
        want = norm(hint[1])
        if want and (want in norm(dev) or SequenceMatcher(None, want, norm(dev)).ratio() > 0.8):
            sim = max(sim, similarity(hint[0], t))
        else:
            flags.append(f"developer is not {hint[1]}")
    if EDITION_RE.search(nt) and not EDITION_RE.search(na):
        flags.append("lite/free/demo edition")
    for service in ("Netflix", "Crunchyroll"):  # streaming-service editions aren't the Play Pass ones
        if service.casefold() in dev.casefold() or nt.startswith(service.casefold() + " "):
            flags.append(f"{service} edition")
    if COMPANION_RE.search(nt) and not COMPANION_RE.search(na):
        flags.append("companion app")
    if number_mismatch(game_title, t):
        flags.append("different number")
    if c.get("genre") in NON_GAME_GENRES and game_genre != "Educational":
        flags.append(f"category {c.get('genre')}")
    penalty = {"lite/free/demo edition": .3, "Netflix edition": .6, "Crunchyroll edition": .6,
               "companion app": .5, "different number": .25}
    score = sim - sum(penalty.get(f, .2) for f in flags) + (0.02 if spelling(t) == spelling(game_title) else 0)
    return round(score, 3), round(sim, 3), flags


def query_variants(title):
    out = [title]
    hint = developer_hint(title)
    if hint:
        out += [f"{hint[0]} {hint[1]}", hint[0]]
    b = base(title)
    if b != title and len(norm(b)) >= 3:
        out.append(b)
    cleaned = re.sub(r"\s*\((full version|full|premium|pro|paid|ad[- ]free|no ads)\)", "", title, flags=re.I)
    if cleaned != title:
        out.append(cleaned)
    out.append(f"{title} Play Pass")
    return list(dict.fromkeys(q for q in out if q.strip()))


def install_count(c):
    if isinstance(c.get("minInstalls"), int):
        return c["minInstalls"]
    m = re.match(r"[\d,.]+", str(c.get("installs") or ""))
    return int(re.sub(r"\D", "", m.group(0))) if m else None


def install_total(d):
    """Exact install count when the store gives it, else the lower bound ("1,000,000+")."""
    if isinstance(d.get("realInstalls"), int) and d["realInstalls"] > 0:
        return d["realInstalls"]
    return install_count(d)


def store_tags(categories):
    """The store's genre and tags for an app: ["Puzzle", "Logic", "Casual", "Offline"]."""
    seen, out = set(), []
    for c in categories or []:
        name = (c.get("name") if isinstance(c, dict) else c) or ""
        if name and name != "Miscellaneous" and name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out


def copycat(c):
    """Under 100 installs: a copycat listing of a delisted game (real Play Pass
    editions can be small: GameHouse's Decipher has 500+)."""
    n = install_count(c)
    return n is not None and n < 100


def rivals(best, pool):
    """Other developers' apps with an equally close title ("Knock Knock" x3)."""
    return [c for c in pool.values() if c is not best and c["sim"] >= best["sim"] - 0.02
            and norm(c.get("developer")) != norm(best.get("developer"))]


def star_rating(v):
    return round(v, 2) if isinstance(v, (int, float)) and v > 0 else None


def entry_from(c, game_title, confidence, query, flags):
    shots = [s for s in (c.get("screenshots") or []) if s][:MAX_SHOTS]
    return {
        "appId": c["appId"],
        "matched": c.get("title"),
        "developer": c.get("developer"),
        "playGenre": c.get("genre"),
        "icon": c.get("icon"),
        "screenshots": shots,
        "url": f"https://play.google.com/store/apps/details?id={c['appId']}",
        "playPass": c.get("playPass"),
        "rating": star_rating(c.get("rating")),
        "ratings": c.get("ratings"),
        "installs": install_total(c),
        "tags": store_tags(c["categories"]) if c.get("categories") is not None else None,
        "similarity": c.get("sim"),
        "confidence": confidence,
        "flags": flags,
        "query": query,
        "checked": date.today().isoformat(),
        "passChecked": date.today().isoformat(),
    }


def null_entry(reason, best, queries):
    e = {"appId": None, "confidence": "null", "reason": reason, "queries": queries,
         "checked": date.today().isoformat()}
    if best:
        e["candidate"] = {k: best.get(k) for k in ("appId", "title", "developer", "playPass", "sim", "flags")}
    return e


def lookup(game):
    title, genre = game["title"], game.get("genre")
    lang, country = ("ja", "jp") if CJK_RE.search(title) else ("en", "us")
    generic = is_generic(title)
    verify_min = 0.85 if generic else VERIFY_MIN  # "Word Search" must not take "Word Search Find The Words"
    pool, tried = {}, []

    def merge(c, details):
        if details:
            c.update({k: details.get(k) for k in ("title", "developer", "genre", "icon", "screenshots", "playPass",
                                                  "installs", "minInstalls", "realInstalls", "ratings",
                                                  "categories")}, rating=details.get("score"))
            c["detailed"] = True
        c["score"], c["sim"], c["flags"] = assess(title, c, genre)

    def badge_confirms(c):
        # a badged app missing a distinctive word is usually a sibling ("2 Player Games - Pastimes" vs "- Sports")
        return (c.get("playPass") and not c["flags"] and c["score"] >= verify_min
                and (c["sim"] >= 0.85 or not missing_words(title, c.get("title"), c.get("developer"))))

    for q in query_variants(title):
        tried.append(q)
        for h in search_hits(q, lang, country):
            if h["appId"] not in pool:
                merge(h, None)
                pool[h["appId"]] = h
            elif h["top"] and not pool[h["appId"]].get("top"):
                pool[h["appId"]].update(top=True, playPass=pool[h["appId"]].get("playPass") or h["playPass"])
        ranked = sorted(pool.values(), key=lambda c: (-c["score"], c["rank"]))
        for c in ranked[:DETAIL_CHECKS]:
            if c["score"] < CANDIDATE_MIN:
                break
            # top card already says whether it's Play Pass; other hits need the details page
            if not c.get("detailed") and (c.get("playPass") is None or len(c.get("screenshots") or []) < 2):
                merge(c, app_details(c["appId"], lang, country))
            if badge_confirms(c):
                return entry_from(c, title, "verified", c["query"], c["flags"])
        ranked = sorted(pool.values(), key=lambda c: (-c["score"], c["rank"]))
        best = ranked[0] if ranked else None
        # short titles must match exactly: "Replica" is not "Replicat"
        typo_ok = best and (best["sim"] >= 1.0 or len(norm(title)) >= 12)
        clone = best and copycat(best)
        if (best and typo_ok and not clone and best["score"] >= STRONG_MIN and not best["flags"] and not generic
                and not missing_words(title, best.get("title"), best.get("developer")) and not rivals(best, pool)):
            if len(best.get("screenshots") or []) < 2 and not best.get("detailed"):
                merge(best, app_details(best["appId"], lang, country))
            return entry_from(best, title, "strong", best["query"], best["flags"])

    best = max(pool.values(), key=lambda c: c["score"], default=None)
    if not best:
        return null_entry("no search results", None, tried)
    missing = missing_words(title, best.get("title"), best.get("developer"))
    no_badge = "" if best.get("playPass") else " and no Play Pass badge"
    if best["flags"]:
        reason = "closest match flagged: " + ", ".join(best["flags"])
    elif generic and best["score"] >= STRONG_MIN:
        reason = "generic title and no Play Pass badge on the closest match"
    elif best["score"] >= STRONG_MIN and rivals(best, pool):
        reason = f"{len(rivals(best, pool)) + 1} apps share this title and none has the Play Pass badge"
    elif best["score"] >= STRONG_MIN and copycat(best):
        reason = "closest match has under 100 installs and no Play Pass badge (likely a copycat)"
    elif missing and best["sim"] >= 0.6:
        reason = f"closest match lacks {', '.join(missing)!r}{no_badge}"
    else:
        reason = f"title similarity too low ({best['sim']:.2f}){no_badge}"
    return null_entry(reason, best, tried)


def from_override(game, app_id):
    if app_id is None:
        return null_entry("set to null in data/overrides.json", None, [])
    lang, country = ("ja", "jp") if CJK_RE.search(game["title"]) else ("en", "us")
    d = app_details(app_id, lang, country)
    if not d:
        return null_entry(f"override {app_id} not found on the Play Store", None, [])
    c = dict(d, appId=app_id, rating=d.get("score"))
    c["score"], c["sim"], c["flags"] = assess(game["title"], c, game.get("genre"))
    return entry_from(c, game["title"], "manual", None, c["flags"])


def refresh_entry(game, e):
    """Re-read a matched app's store page: its full screenshot set, star rating,
    installs, tags, and whether it carries the Play Pass badge today. The match
    itself is kept."""
    lang, country = ("ja", "jp") if CJK_RE.search(game["title"]) else ("en", "us")
    key = (e["appId"], lang, country)
    for attempt, wait in enumerate((0, 3, 10)):
        if attempt:
            time.sleep(wait)
            _app_memo.pop(key, None)
        d = app_details(*key)
        # The store sometimes serves a page without the app's data (no title, no
        # screenshots, no badge); that must not count as "not in Play Pass".
        if d and d.get("title") and d.get("screenshots"):
            break
    else:
        if d:  # still incomplete: keep the entry as it was, retry on the next refresh
            return dict(e, passError="store page incomplete")
    e = {k: v for k, v in e.items() if k != "passError"}
    e["passChecked"] = date.today().isoformat()
    if not d:  # store page gone: the app has been removed since it was matched
        return dict(e, playPass=None)
    shots = [s for s in (d.get("screenshots") or []) if s][:MAX_SHOTS]
    return dict(e, screenshots=shots or e["screenshots"], icon=d.get("icon") or e["icon"],
                matched=d.get("title") or e["matched"], developer=d.get("developer") or e["developer"],
                playPass=bool(d.get("playPass")), rating=star_rating(d.get("score")), ratings=d.get("ratings"),
                installs=install_total(d), tags=store_tags(d.get("categories")))


REGION_SUFFIX_RE = re.compile(r"(?:[._-]?(?:na|eu|us|uk|jp|ww|global|asia|row|intl|en|eng|ja))+$")


def package_core(app_id):
    """Package name without a trailing region or language marker: com.Level5.LT1RNA and
    com.Level5.LT1REU -> com.level5.lt1r; net.kairosoft.android.gamedev3en (English) and
    net.kairosoft.android.gamedev3 (Japanese) -> net.kairosoft.android.gamedev3."""
    return REGION_SUFFIX_RE.sub("", app_id.lower())


def is_twin(e, h):
    """Whether a search hit is a regional edition of the matched app: same developer, and the
    same title or the same package name up to a region marker (Level-5 sells Layton as
    com.Level5.LT1RNA in the US and com.Level5.LT1REU in Europe)."""
    if not h.get("appId") or h["appId"] == e["appId"] or norm(h.get("developer")) != norm(e.get("developer")):
        return False
    return norm(h.get("title")) == norm(e.get("matched")) or package_core(h["appId"]) == package_core(e["appId"])


def region_search(query, country):
    """Search hits from this country's Play Store, or None if the search failed."""
    try:
        return [h for h in _call(gp_search, query, "en", country, 50, False) if h.get("appId")]
    except NotFoundError:
        return None
    except Blocked:
        raise
    except Exception as e:  # layout surprises
        print(f"    ! search({query!r}, {country}) failed: {type(e).__name__}: {e}", flush=True)
        return None


def region_available(e, country):
    """Whether the game is offered in this country's Play Store: (available, twin appId).

    A details page loads from any country and the Play Pass badge shows
    everywhere, but search only returns apps offered in the searcher's country.
    True: a search from the country finds the app, or a regional edition of it
    that carries the Play Pass badge (returned as the twin). False: neither,
    while the same searches from a reference country (US, UK or Japan) find
    the app. None: no search finds it anywhere, so there's no telling."""
    app_id, name = e["appId"], e.get("matched") or ""
    # the package name without its region marker finds editions with a translated title
    queries = list(dict.fromkeys(q for q in (name, f"{name} {e.get('developer') or ''}".strip(), app_id,
                                             package_core(app_id)) if q))
    failed, twins = False, []
    for q in queries:
        hits = region_search(q, country)
        if hits is None:
            failed = True  # a failed search proves nothing
            continue
        if any(h["appId"] == app_id for h in hits):
            return True, None
        twins += [h["appId"] for h in hits if is_twin(e, h) and h["appId"] not in twins]
    for twin in twins:
        d = app_details(twin, "en", country)
        if d and d.get("playPass"):
            return True, twin
    if failed:
        return None, None
    for ref in [r for r in ("us", "gb", "jp") if r != country]:
        for q in queries:
            if any(h["appId"] == app_id for h in region_search(q, ref) or []):
                return False, None
    return None, None


# ---------------------------------------------------------------- cache / git

def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_cache(cache, order):
    ordered = {t: cache[t] for t in order if t in cache}
    ordered.update({t: v for t, v in cache.items() if t not in ordered})
    tmp = CACHE_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(ordered, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(CACHE_JSON)


def git_commit(msg, push):
    rel = str(CACHE_JSON.relative_to(ROOT))
    try:
        subprocess.run(["git", "-C", str(ROOT), "add", rel], check=True)
        if subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet", "--", rel]).returncode == 0:
            return
        subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m", msg, "--", rel], check=True)
    except subprocess.CalledProcessError as e:  # e.g. index.lock held by another git command
        print(f"    ! cache commit failed ({e}); will retry at the next checkpoint", flush=True)
        return
    print(f"    committed: {msg}", flush=True)
    if push:
        r = subprocess.run(["git", "-C", str(ROOT), "push", "-q", "origin", "HEAD"], capture_output=True, text=True)
        print("    pushed" if r.returncode == 0 else f"    ! push failed: {r.stderr.strip()}", flush=True)


def summarize(cache, games):
    counts = {}
    for g in games:
        e = cache.get(g["title"])
        k = "missing" if e is None else e.get("confidence")
        counts[k] = counts.get(k, 0) + 1
    matched = [cache[g["title"]] for g in games if (cache.get(g["title"]) or {}).get("appId")]
    in_pass = sum(1 for e in matched if e.get("playPass"))
    print("summary: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
          + f" | {len(matched)}/{len(games)} games have screenshots, {in_pass} carry the Play Pass badge")
    dup = {}
    for g in games:
        a = (cache.get(g["title"]) or {}).get("appId")
        if a:
            dup.setdefault(a, []).append(g["title"])
    for a, titles in dup.items():
        if len(titles) > 1:
            print(f"  shared appId {a}: {titles}")


# ---------------------------------------------------------------- regions

def region_todo(e, cc, recheck, today):
    r = (e.get("regions") or {}).get(cc) or {}
    if recheck == "all":
        return True
    if recheck == "doubtful":  # anything not found offered
        return r.get("available") is not True
    if recheck == "nulls":  # unknown or never checked
        return r.get("available") is None
    return r.get("checked") != today


def run_regions(args, games, order, cache, today):
    """--region: check every matched game in each country. Countries run in
    parallel threads (--jobs at a time), each with its own throttle."""
    queues = {cc: [g["title"] for g in games if (cache.get(g["title"]) or {}).get("appId")
                   and (g["title"] in args.only if args.only else region_todo(cache[g["title"]], cc, args.recheck, today))]
              for cc in args.region}
    total = sum(map(len, queues.values()))
    print(f"{total} checks: " + ", ".join(f"{cc} {len(q)}" for cc, q in queues.items()), flush=True)
    label = {True: "offered", False: "NOT OFFERED", None: "unknown"}
    lock, stop, done = threading.Lock(), threading.Event(), [0]

    def message():
        return f"Check Play Store availability ({', '.join(args.region)}): {done[0]}/{total} checks"

    def run(cc):
        _tls.throttle = Throttle(args.delay)
        seen = {}  # appId -> result, for apps YTECHB lists twice
        for i, t in enumerate(queues[cc], 1):
            if stop.is_set():
                return
            e = cache[t]
            if e["appId"] not in seen:
                seen[e["appId"]] = region_available(e, cc)
            available, twin = seen[e["appId"]]
            r = dict({"available": available, "checked": today}, **({"appId": twin} if twin else {}))
            with lock:
                cache[t] = dict(cache[t], regions=dict(cache[t].get("regions") or {}, **{cc: r}))
                done[0] += 1
                print(f"[{cc} {i}/{len(queues[cc])}] {t} -> {label[available]}" + (f" as {twin}" if twin else ""), flush=True)
                if done[0] % 20 == 0:
                    save_cache(cache, order)
                if args.commit_every and done[0] % args.commit_every == 0:
                    save_cache(cache, order)
                    git_commit(message(), args.push)

    pool = ThreadPoolExecutor(max_workers=max(1, args.jobs))
    try:
        for f in as_completed([pool.submit(run, cc) for cc in args.region]):
            f.result()
    except BaseException as e:
        stop.set()  # let the other countries finish the game they're on, then save
        print("STOPPED - looks blocked or rate-limited: " + str(e) if isinstance(e, Blocked)
              else f"stopping ({type(e).__name__}) - saving progress", flush=True)
        pool.shutdown(wait=True)
        save_cache(cache, order)
        sys.exit(2 if isinstance(e, Blocked) else 130 if isinstance(e, KeyboardInterrupt) else 1)
    pool.shutdown()
    save_cache(cache, order)
    if args.commit_every and done[0]:
        git_commit(message(), args.push)
    for cc in args.region:
        res = [(cache[t].get("regions") or {}).get(cc) or {} for t in queues[cc]]
        print(f"{cc}: {sum(1 for r in res if r.get('available') is True)} offered "
              f"({sum(1 for r in res if r.get('appId'))} as a regional edition), "
              f"{sum(1 for r in res if r.get('available') is False)} not offered, "
              f"{sum(1 for r in res if r.get('available') is None)} unknown", flush=True)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recheck", choices=["doubtful", "nulls", "all"],
                    help="redo nulls, unbadged matches and loose title matches (doubtful), only nulls, or everything")
    ap.add_argument("--only", nargs="+", metavar="TITLE", help="(re)do just these titles")
    ap.add_argument("--refresh", action="store_true",
                    help="re-read every matched app's store page (all screenshots, rating, installs, tags, "
                         "current Play Pass status) instead of looking games up; resumes where a refresh "
                         "stopped today")
    ap.add_argument("--region", nargs="+", metavar="CC", type=str.lower,
                    help="check which matched apps these countries' Play Stores offer (two-letter codes, "
                         "e.g. nl de); resumes where a check stopped today")
    ap.add_argument("--jobs", type=int, default=1, metavar="N",
                    help="with --region: check N countries at the same time (default 1)")
    ap.add_argument("--limit", type=int, help="stop after this many lookups")
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between requests (default 0.6)")
    ap.add_argument("--commit-every", type=int, default=0, metavar="N",
                    help="git-commit the cache every N lookups (0 = never)")
    ap.add_argument("--push", action="store_true", help="push after each cache commit")
    ap.add_argument("--no-build", action="store_true", help="don't rebuild index.html at the end")
    args = ap.parse_args()
    THROTTLE.delay = args.delay

    games = load_json(GAMES_JSON, [])
    order = [g["title"] for g in games]
    cache = load_json(CACHE_JSON, {})
    overrides = load_json(OVERRIDES_JSON, {})

    def todo(g):
        t, e = g["title"], cache.get(g["title"])
        if args.only:
            return t in args.only
        if e is None:
            return True
        if t in overrides:  # redo if the override changed since it was applied
            if overrides[t] is None:
                return e.get("reason") != "set to null in data/overrides.json"
            return e.get("confidence") != "manual" or e.get("appId") != overrides[t]
        doubtful = (e.get("appId") is None or e.get("confidence") == "strong"
                    or (e.get("confidence") == "verified" and (e.get("similarity") or 0) < 0.9))
        return {"all": True, "nulls": e.get("appId") is None, "doubtful": doubtful}.get(args.recheck, False)

    today = date.today().isoformat()
    if args.region:
        run_regions(args, games, order, cache, today)
        if not args.no_build:
            rebuild()
        return
    if args.refresh:
        queue = [g for g in games if (cache.get(g["title"]) or {}).get("appId")
                 and (cache[g["title"]].get("passChecked") != today or cache[g["title"]].get("ratings") is None
                      or cache[g["title"]].get("tags") is None)]
        print(f"{len(queue)} matched games to refresh", flush=True)
    else:
        queue = [g for g in games if todo(g)]
        print(f"{len(games)} games, {sum(1 for g in games if g['title'] in cache)} cached, "
              f"{len(queue)} to look up", flush=True)
    if args.limit:
        queue = queue[:args.limit]

    def checkpoint_message():
        if args.refresh:
            return f"Refresh Play Store data: {done}/{len(queue)} games"
        return f"Cache Play Store data: {sum(1 for x in order if x in cache)}/{len(order)} games"

    done = 0
    try:
        for i, g in enumerate(queue, 1):
            t = g["title"]
            if args.refresh:
                e = refresh_entry(g, cache[t])
                status = "store page incomplete, kept" if e.get("passError") else \
                    {True: "in Play Pass", False: "NOT in Play Pass", None: "store page gone"}[e["playPass"]]
                info = (f"{status}, shots={len(e['screenshots'])}, rating={e.get('rating')} ({e.get('ratings')}), "
                        f"installs={e.get('installs')}, tags={len(e.get('tags') or [])}")
            else:
                e = from_override(g, overrides[t]) if t in overrides else lookup(g)
                if e["appId"]:
                    info = f"{e['matched']!r} [{e['appId']}] {e['confidence']} sim={e['similarity']}" \
                           f"{' PP' if e['playPass'] else ''} shots={len(e['screenshots'])}"
                else:
                    info = f"NULL ({e['reason']})"
            cache[t] = e
            done += 1
            print(f"[{i}/{len(queue)}] {t} -> {info}", flush=True)
            if i % 10 == 0:
                save_cache(cache, order)
            if args.commit_every and done % args.commit_every == 0:
                save_cache(cache, order)
                git_commit(checkpoint_message(), args.push)
    except Blocked as e:
        print(f"STOPPED - looks blocked or rate-limited: {e}", flush=True)
        save_cache(cache, order)
        sys.exit(2)
    except KeyboardInterrupt:
        print("interrupted - saving progress", flush=True)
        save_cache(cache, order)
        sys.exit(130)
    save_cache(cache, order)
    if args.commit_every and done:
        git_commit(checkpoint_message(), args.push)
    summarize(cache, games)
    if not args.no_build:
        rebuild()


def rebuild():
    try:
        import build_index
    except ImportError:
        return
    build_index.main([])


if __name__ == "__main__":
    main()
