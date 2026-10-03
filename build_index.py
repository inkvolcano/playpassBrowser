#!/usr/bin/env python3
"""Build index.html: index.template.html + data/games.json + data/shots_cache.json.

The page is one self-contained file; the game data is embedded as JSON. Image
URLs are stored without the googleusercontent host and get their size suffix
(=s96 icons, =w526-h296 screenshots) in the page. Standard library only.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "index.template.html"
OUT = ROOT / "index.html"
IMG_HOST = "https://play-lh.googleusercontent.com/"
PAGE_SHOTS = 6  # screenshots per card


def load(name, default):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def short(url):
    if not url:
        return None
    url = url.split("=")[0]
    return url[len(IMG_HOST):] if url.startswith(IMG_HOST) else url


def main():
    games = load("games.json", [])
    cache = load("shots_cache.json", {})
    source = load("sources.json", {})
    genres = sorted({g["genre"] for g in games})
    index = {g: i for i, g in enumerate(genres)}

    rows, checked = [], []
    for g in games:
        e = cache.get(g["title"]) or {}
        app_id = e.get("appId")
        shots = [short(s) for s in (e.get("screenshots") or [])[:PAGE_SHOTS]] if app_id else []
        matched = e.get("matched") if app_id and e.get("matched") != g["title"] else None
        rows.append([g["title"], index[g["genre"]], app_id, short(e.get("icon")) if app_id else None,
                     shots, e.get("developer") if app_id else None, matched])
        if e.get("checked"):
            checked.append(e["checked"])

    data = {
        "genres": genres,
        "games": rows,
        "meta": {"listUrl": source.get("url"), "listUpdated": source.get("updated"),
                 "storeChecked": max(checked) if checked else None},
    }
    # "<" is escaped so nothing inside the JSON can close the <script> element.
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = TEMPLATE.read_text(encoding="utf-8")
    if "__DATA__" not in template:
        raise SystemExit("index.template.html has no __DATA__ placeholder")
    OUT.write_text(template.replace("__DATA__", blob), encoding="utf-8")

    with_shots = sum(1 for r in rows if r[4])
    print(f"index.html: {len(rows)} games, {with_shots} with screenshots, "
          f"{len(rows) - with_shots} with generated covers, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
