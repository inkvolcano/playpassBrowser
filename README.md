# playpassBrowser

A single-page catalogue of every Google Play Pass game: `index.html`.

Open `index.html` in a browser. It is one self-contained file (the game data is
embedded); only the screenshots, icons and fonts load from the web
(`play-lh.googleusercontent.com`, Google Fonts). Each card has the game's icon,
title, developer and genre, screenshots that cycle when you tap them, and links
to the Play Store page, a YouTube gameplay search and a Google Images search.
You can search titles and developers, filter by genre, sort A–Z or by genre,
and switch between light, dark and system themes. Games without a confident
Play Store match get a generated gradient cover and a Play Store search link.

## Files

| File | What it is |
| --- | --- |
| `fetch_games.py` | Scrapes [YTECHB's Play Pass games list](https://www.ytechb.com/google-play-pass-games-list/) into `data/games.json` |
| `fill_screenshots.py` | Looks every game up on the Play Store, caching results in `data/shots_cache.json`, then rebuilds `index.html` |
| `build_index.py` | Builds `index.html` from `index.template.html` and the data files |
| `index.template.html` | The page (HTML, CSS, JS) with a `__DATA__` placeholder |
| `data/games.json` | The game list: `title`, `genre`, `source` |
| `data/shots_cache.json` | Play Store data per game: `appId`, `icon`, `screenshots`, `url`, plus match details |
| `data/overrides.json` | Hand-made fixes: title → appId, or title → `null` |
| `data/sources.json` | Where the list came from and when it was last updated |

## Updating

```sh
pip install google-play-scraper

python3 fetch_games.py         # 1. refresh the game list from YTECHB
python3 fill_screenshots.py    # 2. look up games not in the cache yet, then rebuild index.html
```

`fill_screenshots.py` resumes from `data/shots_cache.json`, so it only looks up
games it hasn't seen; stop it at any time (Ctrl-C saves progress) and run it
again to continue. A full run over ~1,800 games takes about 45 minutes because
requests are throttled (`--delay`, 0.6 s by default) to avoid rate limiting.

Useful options:

```sh
python3 fill_screenshots.py --recheck doubtful   # redo nulls, unbadged matches and loose title matches
python3 fill_screenshots.py --recheck all        # redo everything
python3 fill_screenshots.py --only "Mini Metro" "Stardew valley"   # redo specific titles
python3 fill_screenshots.py --commit-every 200 --push               # commit (and push) the cache as it goes
python3 build_index.py                            # rebuild index.html without any lookups
```

Run `python3 fill_screenshots.py --help` for the rest.

## How games are matched

For each title the script runs a Play Store search and scores every hit on
title similarity, with penalties for Lite/Free/Demo editions, Netflix and
Crunchyroll editions, companion apps (guides, save editors, trackers), different
sequel numbers, a developer that doesn't match a "... by Developer" title, and
non-game categories. The Play Store shows a Play Pass badge on included apps;
the script reads it from the top search card or the app's details page.

- **verified**: the app has the Play Pass badge and the title matches. A badged
  app that lacks a distinctive word of the list title must still be a close
  match, so "2 Player Games – Sports" doesn't take "2 Player Games - Pastimes".
- **strong**: no badge (often a game that has left Play Pass), but the title is
  a near-exact match containing every distinctive word, no other developer has
  an app with the same name, titles under 12 characters match exactly, and the
  app has at least 100 installs (lower usually means a copycat of a game that
  has been taken down).
- Anything else is retried with tweaked queries (subtitle dropped, developer
  added, "Play Pass" added). Generic titles such as "Word Search" or "Baby Games
  for 2-5 Year Olds" must be verified. Whatever is still doubtful is stored
  with `appId: null`, so the page shows a cover instead of the wrong game.
- **manual**: set in `data/overrides.json`, mostly renamed apps (found by
  package name) and YTECHB typos, plus a few titles pinned to `null`.

YTECHB sometimes lists one game under two names (typos, old and new names,
"Premium RPG X" next to "RPG X Premium"). Both entries then resolve to the same
app and `build_index.py` shows it once.

To fix a match by hand, add it to `data/overrides.json` and rerun
`fill_screenshots.py` (overrides are applied whenever they change):

```json
{
  "Kids Learn About Animals (Intellijoy)": "com.nightboost.kids.animals",
  "Some Game": null
}
```

The script also patches two bugs in google-play-scraper 1.2.7: the top search
result's `appId` comes back as `None`, and `search()` crashes on pages that
start with "Showing results for". It turns TLS certificate checks back on,
which the library switches off on import.
