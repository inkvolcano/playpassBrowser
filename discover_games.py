#!/usr/bin/env python3
"""Find Play Pass games on Google Play itself and save them to data/discovered.json.

Google doesn't publish the Play Pass catalogue on the web: the full list only
exists in the Play Store app's Play Pass tab, behind a signed-in device. But
every app card on the Play Store website carries the Play Pass badge when the
app is in Play Pass. Starting from every badged game already in
data/shots_cache.json, this crawls Google Play: each badged game's store page
(its "similar games" and "more by this developer" cards), each developer's
page, a search for each developer's name, and the games home page. Every
badged app it sees is queued in turn, until no new ones turn up.

Badged games that YTECHB's list doesn't have go to data/discovered.json
(appId, store title, genre); earlier finds stay. fill_screenshots.py then
adds them to the cache like any other game, and build_index.py lists them
next to YTECHB's list.

    python3 discover_games.py            # crawl, write data/discovered.json
    python3 discover_games.py --jobs 5   # five threads (default 4)
"""
import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import quote

import fill_screenshots as fs
from google_play_scraper.constants.regex import Regex
from google_play_scraper.exceptions import NotFoundError
from google_play_scraper.utils.request import get

ROOT = Path(__file__).resolve().parent
DISCOVERED_JSON = ROOT / "data" / "discovered.json"
STORE = "https://play.google.com/store"
DETAILS_RE = re.compile(r"details\?id=([A-Za-z0-9._]+)")

# Play Store genre -> the page's genre. Anything else (Tools, Photography...) is
# a Play Pass app rather than a game and is left out.
GENRES = {
    "Action": "Action", "Adventure": "Adventure", "Arcade": "Arcade", "Board": "Board",
    "Card": "Card", "Casino": "Card", "Casual": "Casual", "Educational": "Educational",
    "Music": "Music", "Puzzle": "Puzzle", "Racing": "Racing", "Role Playing": "Role-Playing",
    "Simulation": "Simulation", "Sports": "Sports", "Strategy": "Strategy",
    "Trivia": "Word & Trivia", "Word": "Word & Trivia",
}


def cards(html):
    """{appId: badged} for every app card in a Play Store page's embedded data.

    A card is the largest piece of the page data that links to exactly one
    app; it's badged when the Play Pass marker sits inside it."""
    found = {}

    def walk(node):
        if isinstance(node, str):
            return set(DETAILS_RE.findall(node)), "playpass_family" in node
        children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
        parts = [walk(x) for x in children]
        ids = set().union(*(p[0] for p in parts)) if parts else set()
        if len(ids) > 1:
            for p_ids, p_badge in parts:
                if len(p_ids) == 1:
                    a = next(iter(p_ids))
                    found[a] = found.get(a, False) or p_badge
        return ids, any(p[1] for p in parts)

    for m in Regex.SCRIPT.findall(html):
        k, v = Regex.KEY.findall(m), Regex.VALUE.findall(m)
        if not (k and v):
            continue
        try:
            data = json.loads(v[0])
        except ValueError:
            continue
        ids, badge = walk(data)
        if len(ids) == 1:  # a whole data block about one app (a details page)
            a = next(iter(ids))
            found[a] = found.get(a, False) or badge
    return found


def fetch(url):
    """Page HTML via the throttled caller, or None when it doesn't exist."""
    try:
        return fs._call(get, url)
    except NotFoundError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=4, help="threads (default 4)")
    ap.add_argument("--delay", type=float, default=0.7, help="seconds between requests per thread (default 0.7)")
    args = ap.parse_args()

    cache = json.loads(fs.CACHE_JSON.read_text(encoding="utf-8"))
    listed = {(cache.get(g["title"]) or {}).get("appId") for g in json.loads(fs.GAMES_JSON.read_text(encoding="utf-8"))}
    old = {d["appId"]: d for d in json.loads(DISCOVERED_JSON.read_text(encoding="utf-8"))} if DISCOVERED_JSON.exists() else {}
    known = {e["appId"] for e in cache.values() if e.get("appId")} | set(old)
    seeds = {e["appId"] for e in cache.values() if e.get("appId") and e.get("playPass")} | set(old)
    developers = {e["developer"] for e in cache.values() if e.get("appId") and e.get("playPass") and e.get("developer")}

    lock = threading.Lock()
    badged = set(seeds)       # every badged app seen
    fetched = set()           # pages done
    queue = [f"{STORE}/games?hl=en&gl=us"]
    queue += [f"{STORE}/apps/details?id={quote(a)}&hl=en&gl=us" for a in sorted(seeds)]
    queue += [f"{STORE}/apps/developer?id={quote(d)}&hl=en&gl=us" for d in sorted(developers)]
    queue += [f"{STORE}/search?q={quote(d)}&c=apps&hl=en&gl=us" for d in sorted(developers)]
    stats = {"pages": 0, "new": 0}

    def work(url):
        fs._tls.throttle = getattr(fs._tls, "throttle", None) or fs.Throttle(args.delay)
        html = fetch(url)
        found = cards(html) if html else {}
        new = []
        with lock:
            stats["pages"] += 1
            for a, b in found.items():
                if b and a not in badged:
                    badged.add(a)
                    new.append(a)
            stats["new"] += sum(1 for a in new if a not in known)
            if stats["pages"] % 100 == 0:
                print(f"  {stats['pages']} pages, {len(badged)} badged apps ({len(badged - known)} new)", flush=True)
        for a in new:
            print(f"  + {a}" + ("" if a in known else "  (new)"), flush=True)
        return [f"{STORE}/apps/details?id={quote(a)}&hl=en&gl=us" for a in new]

    print(f"{len(seeds)} badged games to start from, {len(developers)} developers", flush=True)
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            while queue:
                batch = [u for u in dict.fromkeys(queue) if u not in fetched]
                queue = []
                fetched.update(batch)
                for more in pool.map(work, batch):
                    queue += more
    except fs.Blocked as e:
        sys.exit(f"STOPPED - looks blocked or rate-limited: {e}")

    new = sorted(badged - known)
    print(f"{stats['pages']} pages read: {len(badged)} badged apps, {len(new)} not seen before", flush=True)

    # Store data for the new ones: title and genre; non-games are left out.
    # Earlier finds stay (the next --refresh drops any that lost the badge).
    out = [d for a, d in old.items() if a not in listed]
    apps = []
    today = date.today().isoformat()

    def describe(a):
        fs._tls.throttle = getattr(fs._tls, "throttle", None) or fs.Throttle(args.delay)
        return a, fs.app_details(a, "en", "us")

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for a, d in pool.map(describe, new):
            if not d or not d.get("title"):
                print(f"  ? {a}: no store data", flush=True)
                continue
            genre = GENRES.get(d.get("genre"))
            if not genre:
                apps.append(f"{d['title']} ({d.get('genre')})")
                continue
            out.append({"appId": a, "title": d["title"], "genre": genre, "playGenre": d.get("genre"),
                        "developer": d.get("developer"), "found": today})
    out.sort(key=lambda d: d["title"].casefold())
    DISCOVERED_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out)} Play Pass games that YTECHB's list doesn't have -> {DISCOVERED_JSON.relative_to(ROOT)}"
          f"; {len(apps)} badged apps that aren't games left out: " + "; ".join(apps), flush=True)


if __name__ == "__main__":
    main()
