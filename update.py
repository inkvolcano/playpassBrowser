#!/usr/bin/env python3
"""Update everything the page shows, then rebuild index.html. The GitHub workflow
(.github/workflows/update.yml) runs this on the first of every month and pushes the result.

Steps, in order:
  list       fetch_games.py: YTECHB's list
  discover   discover_games.py: Play Pass games and apps found on Google Play itself
  lookup     fill_screenshots.py: match the games that are new to the list
  refresh    every app's Play Pass badge (which dates "New" and "left"), screenshots,
             rating, downloads and tags
  regions    new games in every country already checked, plus the longest-unchecked
             older checks (up to --region-budget)
  details    detail-view data (description, price, age rating) older than a month
  langs      the store's translations (titles, descriptions, tags) older than three months
  build      build_index.py
A step that fails leaves the data as it was and the next steps carry on; once Google Play
looks blocked, the remaining network steps are skipped. The exit code is 1 if any step
failed, so a scheduled run that went wrong shows up as failed.

    python3 update.py                    # all steps
    python3 update.py --commit           # and git-commit the result
    python3 update.py --skip discover    # leave out steps
    python3 update.py --quick            # a few minutes' worth of each step (a test run)
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE_JSON = ROOT / "data" / "shots_cache.json"
STEPS = ["list", "discover", "lookup", "refresh", "regions", "details", "langs", "build"]
BLOCKED = "looks blocked"  # what the scripts print when Google Play stops answering


def countries():
    """Every country some game has been checked in: new games get checked there too."""
    cache = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    return sorted({cc for e in cache.values() for cc in (e.get("regions") or {})})


def run(name, cmd):
    """Run one step, echoing its output: 'ok', 'failed' or 'blocked'."""
    print(f"\n=== {name}: {' '.join(cmd[1:])}", flush=True)
    start, blocked = time.monotonic(), False
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        print(line, end="", flush=True)
        blocked = blocked or BLOCKED in line
    code = proc.wait()
    result = "blocked" if blocked else "ok" if code == 0 else "failed"
    print(f"=== {name}: {result} ({(time.monotonic() - start) / 60:.1f} min)", flush=True)
    return result


def summary():
    """'1,860 games and apps (+12 new, 3 left)' from today's dates in the cache."""
    cache = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    apps = {e["appId"]: e for e in cache.values() if e.get("appId")}
    listed = sum(1 for e in apps.values() if e.get("playPass") is True)
    since = min((e["firstSeen"] for e in apps.values() if e.get("firstSeen")), default=today)
    new = sum(1 for e in apps.values() if e.get("firstSeen") == today) if since < today else 0  # day one: none
    left = sum(1 for e in apps.values() if e.get("leftOn") == today)
    return f"{listed:,} games and apps in Play Pass ({new:+,} new, {left:,} left)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip", nargs="+", choices=STEPS, default=[], metavar="STEP", help=f"steps to leave out: {', '.join(STEPS)}")
    ap.add_argument("--quick", action="store_true", help="only a little of each step, to test the pipeline")
    ap.add_argument("--jobs", type=int, default=6, help="threads for the steps that take them (default 6)")
    ap.add_argument("--region-budget", type=int, default=25000, help="country checks per run (default 25000)")
    ap.add_argument("--commit", action="store_true", help="git-commit the updated data and page")
    args = ap.parse_args()

    py, fs = sys.executable, "fill_screenshots.py"
    q = args.quick
    jobs = str(args.jobs)
    steps = {
        "list": [py, "fetch_games.py"],
        "discover": [py, "discover_games.py", "--jobs", "4"] + (["--max-pages", "30"] if q else []),
        "lookup": [py, fs, "--no-build"] + (["--limit", "5"] if q else []),
        "refresh": [py, fs, "--refresh", "--no-build"] + (["--limit", "10"] if q else []),
        "regions": None,  # needs the cache as the earlier steps left it
        "details": [py, fs, "--details", "--recheck", "stale", "--max-age", "25", "--jobs", jobs, "--no-build"]
                   + (["--budget", "10"] if q else []),
        "langs": [py, fs, "--langs", "--recheck", "stale", "--max-age", "90", "--jobs", jobs, "--no-build"]
                 + (["--budget", "5"] if q else []),
        "build": [py, "build_index.py"],
    }
    results, blocked = {}, False
    for name in STEPS:
        if name in args.skip:
            continue
        if blocked and name != "build":
            results[name] = "skipped"
            print(f"\n=== {name}: skipped, Google Play looked blocked", flush=True)
            continue
        cmd = steps[name]
        if name == "regions":
            cmd = [py, fs, "--region", *countries(), "--recheck", "stale", "--max-age", "180",
                   "--budget", "40" if q else str(args.region_budget), "--jobs", "16", "--no-build"]
        results[name] = run(name, cmd)
        blocked = blocked or results[name] == "blocked"

    print("\n" + ", ".join(f"{k} {v}" for k, v in results.items()), flush=True)
    if args.commit:
        paths = ["data", "details", "index.html"]
        subprocess.run(["git", "-C", str(ROOT), "add", "-A", *paths], check=True)
        if subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"]).returncode:
            failed = [k for k, v in results.items() if v != "ok"]
            msg = f"Update {date.today().isoformat()}: {summary()}" + (f"\n\nNot finished: {', '.join(failed)}" if failed else "")
            subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m", msg], check=True)
            print(f"committed: {msg.splitlines()[0]}", flush=True)
        else:
            print("nothing changed", flush=True)
    sys.exit(1 if any(v in ("failed", "blocked") for v in results.values()) else 0)


if __name__ == "__main__":
    main()
