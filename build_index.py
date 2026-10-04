#!/usr/bin/env python3
"""Build index.html: index.template.html + data/games.json + data/shots_cache.json.

The page is one self-contained file; the game data is embedded as JSON. Image
URLs are stored without the googleusercontent host and get their size suffix
(=s96 icons, =w526-h296 screenshots) in the page. Standard library only.

By default the page lists only games whose Play Store page showed the Play Pass
badge at the last check; --all also keeps games that have left Play Pass and
games without a Play Store match (shown with a generated cover).

Games: YTECHB's list (data/games.json) plus the Play Pass games that
discover_games.py found on Google Play itself (data/discovered.json).

Regions: the catalogue comes from the US store. Countries checked with
`fill_screenshots.py --region CC` get an entry in the page's region menu, which
hides games that country's store doesn't offer.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "index.template.html"
OUT = ROOT / "index.html"
IMG_HOST = "https://play-lh.googleusercontent.com/"
PAGE_SHOTS = 12  # screenshots per card
HOME_REGION = "us"  # the store the catalogue itself comes from
ZONE_TAB = Path("/usr/share/zoneinfo/zone.tab")


def load(name, default):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def short(url):
    if not url:
        return None
    url = url.split("=")[0]
    return url[len(IMG_HOST):] if url.startswith(IMG_HOST) else url


GOOGLE_SOURCE = "Google Play"


def title_key(title):
    return re.sub(r"[\W_]+", "", title.casefold())


def load_games(cache=None):
    """YTECHB's list plus the games discover_games.py found on Google Play.

    A discovered game whose store title is a YTECHB title that has no other
    match lends that entry its appId; the rest join the list under their store
    title, with the genre mapped from the store's."""
    cache = load("shots_cache.json", {}) if cache is None else cache
    games = [dict(g) for g in load("games.json", [])]
    by_key, titles = {}, {g["title"] for g in games}
    listed = {(cache.get(g["title"]) or {}).get("appId") for g in games}
    for g in games:
        by_key.setdefault(title_key(g["title"]), []).append(g)
    for d in load("discovered.json", []):
        same = [g for g in by_key.get(title_key(d["title"]), [])
                if not g.get("appId") and (cache.get(g["title"]) or {}).get("appId") in (None, d["appId"])]
        if same:
            same[0]["appId"] = d["appId"]
        elif d["appId"] not in listed:
            # another app already uses the name ("Spades", "Word Search"): add the developer
            title = d["title"] if d["title"] not in titles else f"{d['title']} ({d.get('developer') or d['appId']})"
            if title not in titles:
                games.append({"title": title, "genre": d["genre"], "source": GOOGLE_SOURCE, "appId": d["appId"]})
                titles.add(title)
    return games


def offered(e, cc):
    """False only when a check found that country's store doesn't offer the app."""
    return ((e.get("regions") or {}).get(cc) or {}).get("available") is not False


def alt_ids(e, regions):
    """Per region, the regional edition a country's store sells instead of the US app
    (Layton's European listings, say), or None when there's none anywhere."""
    ids = [((e.get("regions") or {}).get(cc) or {}).get("appId") for cc in regions]
    return ids if any(ids) else None


def time_zones():
    """Country code -> its IANA time zones, so the page can guess the visitor's country."""
    zones = {}
    if ZONE_TAB.exists():
        for line in ZONE_TAB.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and not line.startswith("#"):
                zones.setdefault(parts[0].lower(), []).append(parts[2])
    return zones


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true",
                    help="also list games that have left Play Pass or have no Play Store match")
    args = ap.parse_args(argv)

    cache = load("shots_cache.json", {})
    games = load_games(cache)
    source = load("sources.json", {})

    # YTECHB sometimes lists one game under two names ("Flat machine" and
    # "Flat Machine: Post-Apocalyptic"): show each Play Store app once, under
    # the title closest to its store name.
    keep = {}
    for g in games:
        e = cache.get(g["title"]) or {}
        a = e.get("appId")
        if a and (a not in keep or (e.get("similarity") or 0) > (cache[keep[a]].get("similarity") or 0)):
            keep[a] = g["title"]

    shown, merged, out_of_pass, unmatched = [], [], [], []
    for g in games:
        e = cache.get(g["title"]) or {}
        app_id = e.get("appId")
        if app_id and keep[app_id] != g["title"]:
            merged.append(f"{g['title']!r} (same app as {keep[app_id]!r})")
        elif not app_id:
            unmatched.append(g["title"])
            if args.all:
                shown.append((g, e))
        elif e.get("playPass") is not True:
            out_of_pass.append(g["title"])
            if args.all:
                shown.append((g, e))
        else:
            shown.append((g, e))

    # Region menu: the home store plus every country that has been checked.
    regions = [HOME_REGION] + sorted({cc for _, e in shown for cc in (e.get("regions") or {}) if cc != HOME_REGION})
    region_checked = {cc: [r["checked"] for _, e in shown if (r := (e.get("regions") or {}).get(cc)) and r.get("checked")]
                      for cc in regions}
    nowhere = [g["title"] for g, e in shown if e.get("appId") and not any(offered(e, cc) for cc in regions)]
    shown = [(g, e) for g, e in shown if g["title"] not in nowhere]

    genres = sorted({g["genre"] for g, _ in shown})
    genre_index = {name: i for i, name in enumerate(genres)}
    tag_counts = Counter(t for _, e in shown if e.get("appId") for t in (e.get("tags") or []))
    tags = [t for t, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    tag_index = {t: i for i, t in enumerate(tags)}

    rows, checked, pass_checked = [], [], []
    for g, e in shown:
        app_id = e.get("appId")
        shots = [short(s) for s in (e.get("screenshots") or [])[:PAGE_SHOTS]] if app_id else []
        matched = e.get("matched") if app_id and e.get("matched") != g["title"] else None
        in_pass = {True: 1, False: 0}.get(e.get("playPass")) if app_id else None
        rated = app_id and e.get("rating") and e.get("ratings")
        rows.append([g["title"], genre_index[g["genre"]], app_id, short(e.get("icon")) if app_id else None,
                     shots, e.get("developer") if app_id else None, matched, in_pass,
                     e["rating"] if rated else None, e["ratings"] if rated else None,
                     e.get("installs") if app_id else None,
                     [tag_index[t] for t in (e.get("tags") or [])] if app_id else [],
                     sum(1 << i for i, cc in enumerate(regions) if not app_id or offered(e, cc)),
                     alt_ids(e, regions) if app_id else None])
        if e.get("checked"):
            checked.append(e["checked"])
        if app_id and e.get("passChecked"):
            pass_checked.append(e["passChecked"])

    zones = time_zones()
    data = {
        "genres": genres,
        "tags": tags,
        "regions": [{"code": cc.upper(), "checked": max(region_checked[cc]) if region_checked[cc] else None,
                     "tz": zones.get(cc, []) if cc != HOME_REGION else []} for cc in regions],
        "games": rows,
        "meta": {"listUrl": source.get("url"), "listUpdated": source.get("updated"),
                 "storeChecked": max(checked) if checked else None,
                 "passChecked": max(pass_checked) if pass_checked else None,
                 "confirmedOnly": not args.all,
                 "fromGoogle": sum(1 for g, _ in shown if g.get("source") == GOOGLE_SOURCE),
                 "leftOutOfPass": len(out_of_pass), "leftOutUnmatched": len(unmatched)},
    }
    # "<" is escaped so nothing inside the JSON can close the <script> element.
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = TEMPLATE.read_text(encoding="utf-8")
    if "__DATA__" not in template:
        raise SystemExit("index.template.html has no __DATA__ placeholder")
    OUT.write_text(template.replace("__DATA__", blob), encoding="utf-8")

    with_shots = sum(1 for r in rows if r[4])
    print(f"index.html: {len(rows)} games ({with_shots} with screenshots, {sum(1 for r in rows if r[8])} rated, "
          f"{len(tags)} tags), {OUT.stat().st_size / 1024:.0f} KB")
    if not args.all:
        print(f"left out: {len(out_of_pass)} no longer in Play Pass, {len(unmatched)} without a Play Store match "
              f"(use --all to keep them)")
    matched_rows = sum(1 for r in rows if r[2])
    for i, cc in enumerate(regions):
        off = sum(1 for r in rows if not r[12] >> i & 1)
        checked = sum(1 for g, e in shown if e.get("appId") and cc in (e.get("regions") or {}))
        note = "" if cc == HOME_REGION and not checked else f", checked {checked}/{matched_rows}"
        # the home store is only checked for games not matched through its own search
        partial = cc != HOME_REGION and checked and checked < matched_rows
        print(f"region {cc}: {len(rows) - off} offered, {off} not{note}"
              + (" - INCOMPLETE: unchecked games count as offered" if partial else ""))
    if nowhere:
        print(f"left out, offered in none of the regions: {len(nowhere)}: " + "; ".join(nowhere))
    if merged:
        print(f"{len(merged)} duplicate listings shown once: " + "; ".join(merged))


if __name__ == "__main__":
    main()
