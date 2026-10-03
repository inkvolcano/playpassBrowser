#!/usr/bin/env python3
"""Fetch the current Google Play Pass games list and save it as data/games.json.

Source: YTECHB's continuously updated list, which groups every Play Pass game
under one of 16 genre headings. Those are normalised to 15 genres (Trivia and
Word are merged). Standard library only.

    python3 fetch_games.py            # download + write data/games.json
    python3 fetch_games.py --html f   # parse a saved copy of the page instead
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GAMES_JSON = ROOT / "data" / "games.json"
SOURCES_JSON = ROOT / "data" / "sources.json"

SOURCE_URL = "https://www.ytechb.com/google-play-pass-games-list/"

# Section heading id prefix ("action-games" -> "action") -> normalised genre.
GENRES = {
    "action": "Action",
    "adventure": "Adventure",
    "arcade": "Arcade",
    "board": "Board",
    "card": "Card",
    "casual": "Casual",
    "educational": "Educational",
    "music": "Music",
    "puzzle": "Puzzle",
    "racing": "Racing",
    "role-playing": "Role-Playing",
    "simulation": "Simulation",
    "sports": "Sports",
    "strategy": "Strategy",
    "trivia": "Word & Trivia",
    "word": "Word & Trivia",
}

# Names YTECHB lists twice in one genre because two different Play Pass apps
# use them (checked on the Play Store). First listing -> title for the second.
SAME_NAME_APPS = {
    "Kids Learn About animals": "Kids Learn About Animals (Intellijoy)",
    "Toddler games for 3 year olds": "Toddler Games for 3 Year Olds+",
}


class GenreListParser(HTMLParser):
    """Collects the <li> text that follows each '<h2|h3 id="<genre>-games">' heading."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section = None
        self.in_li = False
        self.buf = []
        self.items = []  # (section key, title) in page order
        self.modified = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4"):
            m = re.fullmatch(r"(.+)-games", a.get("id") or "")
            self.section = m.group(1) if m and m.group(1) in GENRES else None
        elif tag == "li" and self.section:
            self.in_li, self.buf = True, []
        elif tag == "meta" and a.get("property") == "article:modified_time":
            self.modified = (a.get("content") or "")[:10] or None

    def handle_endtag(self, tag):
        if tag == "li" and self.in_li:
            self.in_li = False
            title = " ".join("".join(self.buf).split())
            if title:
                self.items.append((self.section, title))

    def handle_data(self, data):
        if self.in_li:
            self.buf.append(data)


def dedupe_key(title):
    return re.sub(r"[^\w]+", "", title.casefold())


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (playpass-catalogue)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", help="parse this saved HTML file instead of downloading")
    args = ap.parse_args()

    page = Path(args.html).read_text(encoding="utf-8") if args.html else fetch(SOURCE_URL)
    p = GenreListParser()
    p.feed(page)
    if len(p.items) < 500:
        sys.exit(f"Only {len(p.items)} games parsed - the page layout probably changed; not overwriting.")

    games, seen, dupes = [], {}, []
    for section, title in p.items:
        k = dedupe_key(title)
        if k in seen and seen[k]["title"] in SAME_NAME_APPS:
            title = SAME_NAME_APPS[seen[k]["title"]]
            k += "#2"
        if k in seen:  # same game listed twice (usually under two genres): keep the first
            dupes.append(f"{title} ({GENRES[section]}; kept {seen[k]['title']!r}, {seen[k]['genre']})")
            continue
        seen[k] = {"title": title, "genre": GENRES[section], "source": SOURCE_URL}
        games.append(seen[k])
    games.sort(key=lambda g: g["title"].casefold())

    GAMES_JSON.parent.mkdir(exist_ok=True)
    GAMES_JSON.write_text(json.dumps(games, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    SOURCES_JSON.write_text(json.dumps({
        "name": "YTECHB - Google Play Pass Games: The Complete List",
        "url": SOURCE_URL,
        "updated": p.modified,
        "fetched": date.today().isoformat(),
    }, indent=1) + "\n", encoding="utf-8")

    counts = {}
    for g in games:
        counts[g["genre"]] = counts.get(g["genre"], 0) + 1
    print(f"{len(games)} games (page updated {p.modified}) -> {GAMES_JSON.relative_to(ROOT)}")
    for genre, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {genre}")
    if dupes:
        print(f"{len(dupes)} duplicate listings skipped:")
        for d in dupes:
            print("   ", d)


if __name__ == "__main__":
    main()
