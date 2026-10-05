# playpassBrowser

A single-page catalogue of every Google Play Pass game (and the Play Pass apps
that aren't games): `index.html`.

**Live: https://inkvolcano.github.io/playpassBrowser/** (GitHub Pages, published
from `main`; every push to `main` updates it within a minute or two). It updates
itself on the 1st of every month (see [Updating](#updating)).

You can also open `index.html` straight from disk. It is one self-contained file (the game data is
embedded); only the screenshots, icons and fonts load from the web
(`play-lh.googleusercontent.com`, Google Fonts). The detail view, Discover's
descriptions and the cards' further screenshots come from `details/`, which a
browser only lets the published site read, so from disk the cards show their
first screenshot and the detail view has no description. Each card has the game's icon,
title (the Play Store's own, not YTECHB's spelling), developer, genre, Play Store
star rating and downloads, its Play Store tags, up to 12 screenshots that cycle
when you tap them, and links to the Play Store page, a YouTube gameplay search
and a Google Images search. Games added to Play Pass or released in the last 30
days carry a "New" label.

Tap a title for the detail view: the store description, every screenshot, the
trailer (it plays right there; YouTube only loads when you press play), the age
rating (PEGI and ESRB), what the game costs without Play Pass, release and update
dates, the countries that offer it, and a share button. Below that, "More like
this" lists the games whose Play Store tags overlap most with this one's (rare
tags count for more than ones most games share, and children's games go with
children's games), and a second row has the developer's other games.

You can search titles (YTECHB's names work too), developers and tags. Search is
forgiving: spaces and punctuation don't matter ("minimetro" finds Mini Metro), and
a word that matches nothing is read as a typo and matched to the closest words
("monumnet valey" finds the Monument Valleys); the status line says when it did
that. You can filter by
genre, by tag (Offline, Roguelike, Pixelated, ...; tap a tag on a card to filter
by it), by age rating (PEGI 3, 7, 12 or 16 and under) and by developer (tap a
developer's name); sort A–Z, by genre, by popularity, by rating or newest first;
and switch between light, dark and system themes. Most popular sorts by Play
Store downloads. Top rated uses a weighted average (each game's ratings plus
1,000 at the catalogue average), so a 5.0 from a handful of ratings doesn't
outrank a 4.8 from thousands. Newest sorts by the day a game was first seen in
Play Pass (tracked since 4 October 2026), then by release date. The Apps chip
switches to the Play Pass apps that aren't games (photo, music, kids' learning
and tool apps).

The address bar keeps the search, filters, sort, country and open game, so a
link opens the same view; "Copy link" copies it.

**New for you.** The page remembers (in your browser) the date of the data you
last saw. When you come back after a monthly update, a "New for you" chip lists
the games it added; it stays until you press "Mark as seen" or the next update
comes. On a first visit nothing is new for you.

**Hidden gems, controllers, PC and kids.** More chips sit next to Favourites:

- **Hidden gems**: rated 4.5 or higher by at least 300 players but downloaded
  fewer than 100,000 times (at most three per developer, their best rated).
- **Controller**: games that work with a game controller. Google Play only shows
  its "Gamepad" label in the Android app, so this comes from the store
  descriptions (KEMCO's RPGs have a "[Game Controller] - Supported" line; other
  developers write "Full gamepad support", "Compatible with controllers"...) plus
  a few games named in published lists of controller games
  (`data/controller.json`, with where each was found; the detail view says where
  it comes from). It isn't complete: games that support controllers without
  saying so are missing.
- **On PC**: also on Google Play Games for PC; the Play Store page lists
  "Available on: Android, Windows". Whether Play Pass covers the PC version is up
  to each developer.
- **For kids**: games made for young children plus every game Google Play marks
  Teacher Approved (which includes all-ages games like Hidden Folks or Pocket
  City). Cards and the detail view show the Teacher Approved badge.
- **No kids' games** hides games made for young children: the Educational
  section (bar brain training and colouring for grown-ups) and games whose name
  says they're for kids, babies or toddlers. This one is remembered in your
  browser rather than put in links.

**Favourites and Discover.** Tap ☆ on a card (or in the detail view) to keep a
game; the "★ Favourites" chip shows the list. The Discover button opens a
fullscreen view with one random game at a time: its name, description and
three screenshots under each other. Swipe right (or ♥, or the right arrow key)
to add it to your favourites, left (✕, left arrow) to skip it; undo takes back
the last swipe. Discover follows the current country and filters (open it from
"Puzzle" with "PEGI 7" to swipe through those), skips the games already swiped,
and Reset starts over, optionally clearing the favourites too. Discover leans
towards what you keep: games sharing tags, genres and developers with your
favourites come up more often, and those like the games you skip less often. It's
still a shuffle; before you've kept anything, better-rated games come up slightly
more often. Cards with a trailer can play it in Discover too.

Favourites and swipes are kept in your browser (localStorage), so they're per
device. "Share list" in the Favourites view copies a link to your list (on a
phone it opens the share sheet). Whoever opens it sees the list and can add it
to their own favourites, which is also how you move a list to another device.

**Layout.** The filter bar stays at the top: search and menus (one row from
tablet width up), one row of chips that scrolls sideways (arrows at its ends for a
mouse, a fade on touch screens; thin dividers separate your lists, the features
and the genres), and the status line. On phones the header keeps to what the page
is (the how-to and the sources line are in the footer), and the bar and the
Discover button slide out of the way while you scroll down through the games and
come back as soon as you scroll up. Past the header, the Discover button is just
its icon.

**Phone held sideways.** On a short screen the filter bar shrinks to one row of
search and menus plus the row of chips. In Discover, ✕ and ♥ sit beside the card
instead of under it, and the detail view uses the full height.

**Install as an app.** In Chrome, Edge and on Android an install button appears
next to the language menu (or use the browser's "Install app" menu item); on an
iPhone or iPad, use Safari's Share button and then Add to Home Screen. The app
opens in its own window with a Play Pass ticket icon; pressing and holding the
icon offers Discover and Favourites. A service worker (`sw.js`) keeps the page
and what you've looked at (details, screenshots, trailer stills), so it opens
quickly and works offline. When you're online it always loads the latest page,
so the monthly update shows straight away.

**Languages.** The page speaks English, Dutch, German, French, Spanish, Italian,
Portuguese and Japanese. It picks your browser's language on a first visit; the
globe menu next to the theme button switches (the choice is remembered). Numbers,
dates and country names follow the language. Game titles, descriptions and tag
names come from the Play Store in that language: the developer's translation, or
Google's automatic one.

The page lists only games whose Play Store page showed the Play Pass badge when
it was last checked (US store; the date is in the page footer). YTECHB's list
still carries games that have since left the service, plus a few that couldn't
be matched to a Play Store app; both are left out (the footer gives the counts).
`python3 build_index.py --all` builds a page that keeps them: games that have
left are marked "Not in Play Pass", unmatched ones get a generated gradient
cover and a Play Store search link.

Not every game is offered everywhere. The country menu in the header hides
games that country's Play Store doesn't offer. It has every country in
[Google's list of Play Pass countries](https://play.google/pass-availability/)
(101 in October 2026). On a first visit the page picks the country from your
time zone or browser language. The list itself comes from the US store, so
games that are in Play Pass only outside the US are missing.

## Files

| File | What it is |
| --- | --- |
| `fetch_games.py` | Scrapes [YTECHB's Play Pass games list](https://www.ytechb.com/google-play-pass-games-list/) into `data/games.json` |
| `discover_games.py` | Finds Play Pass games on Google Play itself (the games YTECHB's list lacks) and saves them to `data/discovered.json` |
| `update.py` | Runs every step below in order (the monthly update) |
| `.github/workflows/update.yml` | Runs `update.py` on the 1st of every month and pushes the result to `main` |
| `fill_screenshots.py` | Looks every game up on the Play Store, caching results in `data/shots_cache.json`, then rebuilds `index.html` |
| `build_index.py` | Builds `index.html` from `index.template.html` and the data files |
| `check_page.js` | Opens the built page in a headless browser in every language and checks it works (`npm install playwright` first) |
| `index.template.html` | The page (HTML, CSS, JS) with a `__DATA__` placeholder |
| `manifest.webmanifest`, `icons/` | What makes the page installable as an app: name, colours, icons, shortcuts |
| `sw.js` | The service worker: the page, details files, fonts and images you've seen, for offline use |
| `data/games.json` | YTECHB's game list: `title`, `genre`, `source` |
| `data/discovered.json` | Play Pass games found on Google Play that YTECHB's list lacks: `appId`, `title`, `genre` |
| `data/discovery_report.json` | How the two lists cover each other (written by each crawl) |
| `details/<appId>.json` | Detail-view data per app: description, trailer, age ratings, price, dates, all screenshots |
| `details/<lang>/<appId>.json` | The store's translated summary and description, for the apps that have one in that language |
| `data/translations.json` | Per app: English tags, titles that differ per language, which languages have a translated description; and the store's name for each tag per language |
| `GAP_ANALYSIS.md` | What each list misses, data gaps on the page, and feature ideas |
| `data/shots_cache.json` | Play Store data per game: `appId`, `icon`, `screenshots`, `url`, `playPass`, `rating`, `ratings`, `installs`, `tags`, `regions` (availability per country), `firstSeen` / `leftOn` (Play Pass badge history), `pegi`, `esrb`, `price`, `released`, `updated`, plus match details |
| `data/overrides.json` | Hand-made fixes: title → appId, or title → `null` |
| `data/sources.json` | Where the list came from and when it was last updated |

## Updating

The page updates itself. On the 1st of every month (03:17 UTC) the GitHub
Actions workflow in `.github/workflows/update.yml` runs `update.py`, commits
the new data and page to `main`, and GitHub Pages publishes it. To run it
sooner, open the repository's **Actions** tab, pick **Monthly update** and
press **Run workflow**; tick "Test run" and untick "Push" for a quick check
that changes nothing. A full run takes one to three hours, because requests
are throttled. Before pushing, it opens the new page in a headless browser in
every language (`check_page.js`: cards, search (also with a typo), country menu,
detail view with "More like this", Discover, "New for you", the feature chips);
if anything fails, nothing is pushed and the run turns red. If Google Play stops answering, the run turns red. Whatever it
finished is still committed and pushed, and the next run picks up the rest.

`update.py` runs these steps in order (`--skip` leaves steps out; run it
locally after `pip install google-play-scraper==1.2.7`):

| Step | What it does |
| --- | --- |
| list | `fetch_games.py`: YTECHB's list |
| discover | `discover_games.py`: Play Pass games and apps on Google Play that the list lacks (~15 min) |
| lookup | `fill_screenshots.py`: matches the games new to the list |
| refresh | `fill_screenshots.py --refresh`: every app's Play Pass badge, screenshots, rating, downloads and tags (~35 min). The badge dates "New" and "left Play Pass", so the history grows with each run |
| details | `fill_screenshots.py --details --recheck stale --max-age 25`: descriptions, age ratings, prices, dates, the PC and Teacher Approved badges |
| langs | `fill_screenshots.py --langs --recheck stale --max-age 90`: the store's translations |
| regions | `fill_screenshots.py --region <every country> --recheck stale --max-age 180 --budget 25000 --jobs 8 --delay 1.0`: new games in every country, then the oldest checks |
| build | `build_index.py`: rebuilds `index.html` |

The thread counts and delays are kept low on purpose: Google Play answers "429
Too Many Requests" when one address makes more than about a dozen requests a
second, and the scripts stop when that persists.

`fill_screenshots.py` resumes from `data/shots_cache.json`, so it only looks up
games it hasn't seen; stop it at any time (Ctrl-C saves progress) and run it
again to continue. Requests are throttled (`--delay`, 0.6 s by default) to
avoid rate limiting. `--refresh` keeps every match and re-reads each app's
store page; it resumes too, skipping games already refreshed that day. To add
a country, run `--region` with its two-letter code (`--region se`, or several:
`--region se pl`); the next build adds it to the page's country menu once 90%
of the games have been checked there, and the monthly update keeps it current.

Useful options:

```sh
python3 fill_screenshots.py --recheck doubtful   # redo nulls, unbadged matches and loose title matches
python3 fill_screenshots.py --recheck all        # redo everything
python3 fill_screenshots.py --only "Mini Metro" "Stardew valley"   # redo specific titles
python3 fill_screenshots.py --region nl --recheck missing --jobs 4  # only games never checked in that country
python3 fill_screenshots.py --langs --jobs 6                         # the store's translations for every app
python3 fill_screenshots.py --commit-every 200 --push               # commit (and push) the cache as it goes
python3 build_index.py                            # rebuild index.html without any lookups
python3 build_index.py --all                      # ... also listing games that left Play Pass or have no match
```

Run `python3 fill_screenshots.py --help` for the rest.

## Where the list comes from

Google doesn't publish the Play Pass catalogue on the web: the full list is
only in the Play Store app's Play Pass tab, which needs a signed-in Android
device. So the list starts from [YTECHB's](https://www.ytechb.com/google-play-pass-games-list/)
and is completed from Google Play itself. Every app card on the Play Store
website (a game's page, its "similar games", a developer's page, search
results) carries the Play Pass badge when the app is in Play Pass.
`discover_games.py` starts from every badged game already known, reads those
pages, and follows every badged app it sees until no new ones turn up (about
3,000 pages). The badged games YTECHB's list lacks go to
`data/discovered.json`; badged apps that aren't games (compasses, photo
editors...) are left out. Either way, a game is only listed when its own
Play Store page shows the badge.

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

## How translations work

`fill_screenshots.py --langs` reads each app's store page in English and in
each of the page's languages (Dutch from the Dutch store, Portuguese from the
Brazilian one, and so on). Where the summary and description differ from the
English ones, they go to `details/<lang>/<appId>.json`. That's nearly every app
in every language: the store shows Google's automatic translation where the
developer hasn't written one (about 30 MB for all seven languages). The detail view and Discover use them when you
pick that language. Titles that differ go to `data/translations.json` and
replace the English title on the cards (both stay searchable). Every language
lists an app's genre and tags in the same order, so lining the lists up gives
the store's own name for each tag (`Single player` is `Singleplayer` in Dutch,
`シングル プレーヤー` in Japanese). The interface text itself is in
`index.template.html`.
