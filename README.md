# playpassBrowser

A single-page catalogue of every Google Play Pass game: `index.html`.

**Live: https://inkvolcano.github.io/playpassBrowser/** (GitHub Pages, published
from `main`; every push to `main` updates it within a minute or two).

You can also open `index.html` straight from disk. It is one self-contained file (the game data is
embedded); only the screenshots, icons and fonts load from the web
(`play-lh.googleusercontent.com`, Google Fonts). Each card has the game's icon,
title, developer, genre, Play Store star rating and downloads, its Play Store
tags, up to 12 screenshots that cycle when you tap them, and links to the Play
Store page, a YouTube gameplay search and a Google Images search.

You can search titles, developers and tags, filter by genre and by tag
(Offline, Roguelike, Pixelated, ...; tap a tag on a card to filter by it), sort
A–Z, by genre, by popularity or by rating, and switch between light, dark and
system themes. Most popular sorts by Play Store downloads. Top rated uses a
weighted average (each game's ratings plus 1,000 at the catalogue average), so
a 5.0 from a handful of ratings doesn't outrank a 4.8 from thousands.

The page lists only games whose Play Store page showed the Play Pass badge when
it was last checked (US store; the date is in the page footer). YTECHB's list
still carries games that have since left the service, plus a few that couldn't
be matched to a Play Store app; both are left out (the footer gives the counts).
`python3 build_index.py --all` builds a page that keeps them: games that have
left are marked "Not in Play Pass", unmatched ones get a generated gradient
cover and a Play Store search link.

Not every game is offered everywhere. The country menu in the header hides
games that country's Play Store doesn't offer: Australia, Belgium, Brazil,
Canada, France, Germany, Italy, Japan, the Netherlands, Spain, the United
Kingdom and the United States so far. On a first visit the page picks the
country from your time zone or browser language. The list itself comes from the US store, so games that
are in Play Pass only outside the US are missing.

## Files

| File | What it is |
| --- | --- |
| `fetch_games.py` | Scrapes [YTECHB's Play Pass games list](https://www.ytechb.com/google-play-pass-games-list/) into `data/games.json` |
| `fill_screenshots.py` | Looks every game up on the Play Store, caching results in `data/shots_cache.json`, then rebuilds `index.html` |
| `build_index.py` | Builds `index.html` from `index.template.html` and the data files |
| `index.template.html` | The page (HTML, CSS, JS) with a `__DATA__` placeholder |
| `data/games.json` | The game list: `title`, `genre`, `source` |
| `data/shots_cache.json` | Play Store data per game: `appId`, `icon`, `screenshots`, `url`, `playPass`, `rating`, `ratings`, `installs`, `tags`, `regions` (availability per country), plus match details |
| `data/overrides.json` | Hand-made fixes: title → appId, or title → `null` |
| `data/sources.json` | Where the list came from and when it was last updated |

## Updating

```sh
pip install google-play-scraper

python3 fetch_games.py                # 1. refresh the game list from YTECHB
python3 fill_screenshots.py           # 2. look up games not in the cache yet
python3 fill_screenshots.py --refresh # 3. re-check every game's Play Pass status, rating,
                                      #    downloads, tags and screenshots, then rebuild index.html
python3 fill_screenshots.py --region au be br ca de es fr gb it jp nl us --jobs 6
                                      # 4. re-check which games each country's store offers
```

`fill_screenshots.py` resumes from `data/shots_cache.json`, so it only looks up
games it hasn't seen; stop it at any time (Ctrl-C saves progress) and run it
again to continue. A full run over ~1,800 games takes about 45 minutes because
requests are throttled (`--delay`, 0.6 s by default) to avoid rate limiting.
`--refresh` keeps every match and re-reads each app's store page (about 35
minutes); it resumes too, skipping games already refreshed that day. So does
`--region` (about 20 minutes per country per thread; `--jobs 6` runs six
threads, splitting a country between threads when there are more threads than
countries). To add a country, run it with that country's two-letter code
(`--region se`, or several: `--region se pl`); the next build adds it to the
page's country menu.

Useful options:

```sh
python3 fill_screenshots.py --recheck doubtful   # redo nulls, unbadged matches and loose title matches
python3 fill_screenshots.py --recheck all        # redo everything
python3 fill_screenshots.py --only "Mini Metro" "Stardew valley"   # redo specific titles
python3 fill_screenshots.py --commit-every 200 --push               # commit (and push) the cache as it goes
python3 build_index.py                            # rebuild index.html without any lookups
python3 build_index.py --all                      # ... also listing games that left Play Pass or have no match
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

## How availability per country is checked

A Play Store details page loads from any country, and the Play Pass badge shows
in every country (even ones without Play Pass), so neither says what a country
offers. Search does: a Play Store search from a country only returns apps
offered there. For each app, `--region` searches its store name, then name plus
developer, then its package name, from that country. If a search finds the app,
it's offered. If none does, the same searches run from the US, the UK or
Japan; when they find the app there, it's marked as not offered. When no search finds it anywhere, it's unknown and stays listed.
Some games are sold under a separate listing per region (Level-5's Layton games
have European editions, Kairosoft's games Japanese ones): when a country's
search turns up an app from the same developer with the same title or the same
package name apart from a region or language marker (`com.Level5.LT1RNA` /
`com.Level5.LT1REU`, `net.kairosoft.android.gamedev3en` /
`net.kairosoft.android.gamedev3`), and that app has the Play Pass badge, the
game counts as offered and its Play link points to that edition. The searches
include the package name without its marker, which finds editions whose title
is translated. Re-check games marked as not offered with
`python3 fill_screenshots.py --region nl --recheck doubtful`.
