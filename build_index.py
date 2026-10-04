#!/usr/bin/env python3
"""Build index.html: index.template.html + data/games.json + data/shots_cache.json.

The page is one self-contained file; the game data is embedded as JSON. Image
URLs are stored without the googleusercontent host and get their size suffix
(=s96 icons, =w526-h296 screenshots) in the page. Each game carries only its first
screenshot and how many there are; the page reads the rest from details/<appId>.json
when someone taps through them. Standard library only.

By default the page lists only games whose Play Store page showed the Play Pass
badge at the last check; --all also keeps games that have left Play Pass and
games without a Play Store match (shown with a generated cover).

Games: YTECHB's list (data/games.json) plus the Play Pass games that
discover_games.py found on Google Play itself (data/discovered.json).

Regions: the catalogue comes from the US store. Countries checked with
`fill_screenshots.py --region CC` get an entry in the page's region menu, which
hides games that country's store doesn't offer. A country joins the menu once
90% of the listed games have been checked there.

Languages: `fill_screenshots.py --langs` saves the store's own translations
(data/translations.json, details/<lang>/); the page uses them for titles, tag
names and descriptions when someone picks that language.

Features (the last column's bits): also on Google Play Games for PC and Teacher
Approved come from the store page (fill_screenshots.py --badges or --details);
controller support from the English store description (see controller()) and
data/controller.json.
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
REGION_COVERAGE = 0.9  # share of listed games a country must have been checked for to join the menu
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
APPS = "Apps"  # Play Pass apps that aren't games (discover_games.py)


# Controller support. KEMCO's descriptions carry a "[Game Controller] - Supported" line (or Optimized,
# Partially supported, Not supported...); other developers say it in their own words: "Full gamepad support",
# "Compatible with controllers", "MFi controller support", "touch, tilt or gamepad"...
KEMCO_PAD = re.compile(r"\[Game Controller\]\s*-?\s*([A-Za-z][A-Za-z ]*)")
PAD = r"(?:game ?pads?|game ?controllers?|controllers?|joypads?|mfi)"
PAD_SAYS = re.compile(
    rf"\b{PAD}\b[^.\n!]{{0,60}}\b(?:support|supported|compatib\w*|friendly|ready|optimi[sz]ed|enabled|required)\b"
    rf"|\b(?:support|supports|supported|supporting|compatib\w*|works? with|play(?:able)? with|use|using|connect)\b[^.\n!]{{0,50}}\b{PAD}"
    rf"|\b(?:bluetooth|external|physical|hardware|usb|xbox|playstation|ps[345]|dualshock|dualsense|moga|8bitdo|razer|"
    rf"backbone|nvidia|shield|hid)\b[^.\n!]{{0,25}}\b{PAD}"
    rf"|\b(?:touch|tilt)[^.\n!]{{0,60}}\b(?:game ?pads?|game ?controllers?)\b"
    rf"|\b(?:game ?pads?|controllers?) (?:input|play|mode)\b", re.I)
PAD_NOT = re.compile(r"phones? as (?:a )?controller|virtual (?:controller|gamepad)|on-?screen (?:controller|gamepad)"
                     r"|air traffic controller", re.I)  # in the matched words
PAD_LATER = re.compile(r"\s*(?:is |are |will be )?(?:in the works|coming soon|planned|not (?:yet )?(?:available|supported))",
                       re.I)  # right after them


def controller(app_id, known):
    """4: supports game controllers, 8: partly, 0: not that we know of."""
    if not app_id or app_id in known.get("no", {}):
        return 0
    p = ROOT / "details" / f"{app_id}.json"
    text = json.loads(p.read_text(encoding="utf-8")).get("description") or "" if p.exists() else ""
    m = KEMCO_PAD.search(text)
    if m:
        level = m.group(1).strip().lower()
        return 8 if level.startswith("partial") else 4 if level in ("supported", "optimized", "optimised") else 0
    if app_id in known.get("yes", {}):
        return 8 if known["yes"][app_id].get("partly") else 4
    return 4 if any(not PAD_NOT.search(m.group()) and not PAD_LATER.match(text, m.end())
                    for m in PAD_SAYS.finditer(text)) else 0


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


def not_offered(e, regions):
    """Indexes of the regions whose store doesn't offer the app, or None when all do."""
    out = [i for i, cc in enumerate(regions) if not offered(e, cc)]
    return out or None


def alt_ids(e, regions):
    """{region index: the regional edition that country's store sells instead of the US app}
    (Layton's European listings, say), or None when there's none anywhere."""
    ids = {str(i): a for i, cc in enumerate(regions) if (a := ((e.get("regions") or {}).get(cc) or {}).get("appId"))}
    return ids or None


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
    translations = load("translations.json", {})
    tr_apps, tag_names = translations.get("apps", {}), translations.get("tagNames", {})

    def app_tags(e):  # English tags (the cache has Japanese ones for apps read from the Japanese store)
        return (tr_apps.get(e.get("appId")) or {}).get("tags") or e.get("tags") or []

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

    # Region menu: the home store plus every country that has been checked for most games.
    matched = [e for _, e in shown if e.get("appId")]
    coverage = Counter(cc for e in matched for cc in (e.get("regions") or {}))
    pending = sorted(cc for cc, n in coverage.items() if cc != HOME_REGION and n < REGION_COVERAGE * len(matched))
    regions = [HOME_REGION] + sorted(cc for cc in coverage if cc != HOME_REGION and cc not in pending)
    region_checked = {cc: [r["checked"] for _, e in shown if (r := (e.get("regions") or {}).get(cc)) and r.get("checked")]
                      for cc in regions}
    nowhere = [g["title"] for g, e in shown if e.get("appId") and not any(offered(e, cc) for cc in regions)]
    shown = [(g, e) for g, e in shown if g["title"] not in nowhere]

    genres = sorted({g["genre"] for g, _ in shown}, key=lambda x: (x == APPS, x))  # Apps last
    genre_index = {name: i for i, name in enumerate(genres)}
    tag_counts = Counter(t for _, e in shown if e.get("appId") for t in app_tags(e))
    tags = [t for t, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    tag_index = {t: i for i, t in enumerate(tags)}

    text_langs = sorted({lang for x in tr_apps.values() for lang in x.get("texts", [])} | set(tag_names))
    known_pads = load("controller.json", {})
    rows, checked, pass_checked = [], [], []
    for g, e in shown:
        app_id = e.get("appId")
        shots = [short(s) for s in (e.get("screenshots") or [])[:PAGE_SHOTS]] if app_id else []
        # cards show the store's own title; YTECHB's name (often misspelled or outdated) stays searchable
        name = e.get("matched") if app_id and e.get("matched") else g["title"]
        listed_as = g["title"] if title_key(g["title"]) != title_key(name) else None
        in_pass = {True: 1, False: 0}.get(e.get("playPass")) if app_id else None
        rated = app_id and e.get("rating") and e.get("ratings")
        rows.append([name, genre_index[g["genre"]], app_id, short(e.get("icon")) if app_id else None,
                     [shots[0], len(shots)] if shots else None, e.get("developer") if app_id else None, listed_as, in_pass,
                     e["rating"] if rated else None, e["ratings"] if rated else None,
                     e.get("installs") if app_id else None,
                     [tag_index[t] for t in app_tags(e)] if app_id else [],
                     not_offered(e, regions) if app_id else None,
                     alt_ids(e, regions) if app_id else None,
                     e.get("pegi") if app_id else None, e.get("firstSeen") if app_id else None,
                     e.get("released") if app_id else None,
                     e.get("playGenre") if app_id and g["genre"] == APPS else None,
                     (tr_apps.get(app_id) or {}).get("titles") or None if app_id else None,
                     sum(1 << i for i, lang in enumerate(text_langs) if lang in (tr_apps.get(app_id) or {}).get("texts", []))
                     if app_id else 0,
                     (1 if e.get("onPC") else 0) | (2 if e.get("teacherApproved") else 0) | controller(app_id, known_pads)
                     if app_id else 0])
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
        # per language: the store's name for each tag (None: same as English), and which languages
        # have translated descriptions (bit i of a game's last column: textLangs[i])
        "tagNames": {lang: [names.get(t) for t in tags] for lang, names in tag_names.items()},
        "textLangs": text_langs,
        # where a game's controller support was found, when it isn't its store description
        "padSources": {a: x["source"] for a, x in known_pads.get("yes", {}).items() if x.get("source")},
        "meta": {"listUrl": source.get("url"), "listUpdated": source.get("updated"),
                 "storeChecked": max(checked) if checked else None,
                 "passChecked": max(pass_checked) if pass_checked else None,
                 "confirmedOnly": not args.all,
                 "fromGoogle": sum(1 for g, _ in shown if g.get("source") == GOOGLE_SOURCE and g["genre"] != APPS),
                 "trackingSince": min((e["firstSeen"] for _, e in shown if e.get("firstSeen")), default=None),
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
        off = sum(1 for r in rows if i in (r[12] or []))
        checked = sum(1 for g, e in shown if e.get("appId") and cc in (e.get("regions") or {}))
        note = "" if cc == HOME_REGION and not checked else f", checked {checked}/{matched_rows}"
        # the home store is only checked for games not matched through its own search
        partial = cc != HOME_REGION and checked and checked < matched_rows
        print(f"region {cc}: {len(rows) - off} offered, {off} not{note}"
              + (" - INCOMPLETE: unchecked games count as offered" if partial else ""))
    if pending:
        print(f"not in the menu yet, checked for under {REGION_COVERAGE:.0%} of the games: "
              + ", ".join(f"{cc} {coverage[cc]}/{len(matched)}" for cc in pending))
    if text_langs:
        print("translations: " + ", ".join(f"{lang} {sum(1 for r in rows if r[19] >> i & 1)} descriptions, "
                                            f"{sum(1 for r in rows if r[18] and lang in r[18])} titles"
                                            for i, lang in enumerate(text_langs)))
    print(f"features: {sum(1 for r in rows if r[20] & 1)} also on PC, {sum(1 for r in rows if r[20] & 2)} Teacher Approved, "
          f"{sum(1 for r in rows if r[20] & 4)} with controller support, {sum(1 for r in rows if r[20] & 8)} partly")
    if nowhere:
        print(f"left out, offered in none of the regions: {len(nowhere)}: " + "; ".join(nowhere))
    if merged:
        print(f"{len(merged)} duplicate listings shown once: " + "; ".join(merged))


if __name__ == "__main__":
    main()
