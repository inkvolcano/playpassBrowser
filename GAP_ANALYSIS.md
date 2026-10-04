# Gap analysis

4 October 2026. Compares the two game lists (YTECHB's and the one built from Google
Play's own Play Pass badges), checks the data on the page, and lists features worth
adding. The numbers come from `data/discovery_report.json`, `data/shots_cache.json`
and a headless browser run of `index.html`.

## Summary

- **Both lists are needed.** Of YTECHB's 1,617 games that still carry the Play Pass
  badge, 196 (12%) never appear on any other Google Play page, so a crawl of Google
  Play alone would miss them. Google Play adds 240 games that YTECHB's list lacks. The page now
  lists **1,857 games**.
- **YTECHB's list is partly stale.** 42 of its games have lost the badge, and 119
  titles can't be found as a Play Pass app at all. Most of those have left Play Pass
  or Google Play.
- **About 10% of YTECHB's titles are misspelled or outdated** ("Bluff knight" for
  *Buff Knight*, "A Tiny Sticker Sale" for *A Tiny Sticker Tale*). The page shows
  them as YTECHB writes them.
- **The data on the page is nearly complete.** 11 games have no rating, 6 have no
  tags and 4 have fewer than 4 screenshots.
- **The page is heavy.** It's 2.3 MB with about 101,000 page elements. It loads in
  2 s on a desktop and 3.5 s on a slow phone, and changing the sort takes 0.8 s there.

## Data gaps

### 1. Two lists, partial overlap

| | Games |
| --- | --- |
| Apps with the Play Pass badge seen on Google Play (3,719 pages crawled) | 1,966 |
| YTECHB games with the badge (distinct apps) | 1,617 |
| … also found on other Google Play pages | 1,421 |
| … only known from YTECHB's list | 196 |
| Games on Google Play that YTECHB lacks | 240 |
| … that fill a YTECHB title the matcher couldn't place | 9 |
| … new to the list | 231 |
| Play Pass apps that aren't games (left out) | 109 |

Recent additions show up on Google first. The latest crawl found World of Goo 2,
Human Resource Machine, LYNE and Final Frontier Story, none of which YTECHB lists yet.

YTECHB is thinnest in these genres (games added from Google Play, compared with
YTECHB's count):

| Genre | YTECHB | Added from Google | |
| --- | --- | --- | --- |
| Casual | 104 | 24 | +23% |
| Puzzle | 271 | 58 | +21% |
| Card | 61 | 13 | +21% |
| Strategy | 84 | 17 | +20% |
| Simulation | 143 | 27 | +19% |
| Educational | 240 | 43 | +18% |
| Role-Playing | 145 | 21 | +14% |
| Action, Arcade, Adventure, Board | 452 | 12 | +3% |

The developers with the most games YTECHB misses are KEMCO, Tizi Town, Bubadu, IDZ
Digital, Azur Games, V2R and TapNation.

### 2. Stale YTECHB entries

| Entry | Count | What it means |
| --- | --- | --- |
| Matched, but the badge is gone | 42 | Left Play Pass (e.g. Teslagrad, Spellforce, White Night) |
| Same-name app found, no badge | 32 | Probably left (Strikers 1945, Zero Gunner 2, Knock Knock, Concentration) |
| Nothing close on Google Play | 69 | Probably delisted (Lock's Quest, Homo Machina, Iris and the Giant) |
| Set to "no match" by hand | 16 | Wrong or ambiguous names |
| Only a different sequel found | 2 | Mmm Fingers 2, Time Mysteries 2 |
| Listed twice under two names | 39 | Shown once on the page |

All of these are left off the page. `python3 build_index.py --all` shows them.

### 3. Titles

- 35 shown titles differ clearly from the store name, mostly renamed apps
  ("Pango Build City Kids 3-8" is now *Pango Build & Explore City*; "Football CupPro
  2024" is *Soccer Cup Pro 2026*).
- 137 more are near-identical but misspelled ("BAIKOH Word Challenegs", "Alaphabet
  for Kids", "Hot SPrings Story", "Brain it Out" for *Brain It On!*).
- YTECHB's genres match the store's for 98% of games, so genres are fine.

### 4. Fields the page doesn't have

- **History.** There is no record of when a game joined or left Play Pass, so there is
  no "new" or "leaving" view.
- **Price.** The page doesn't show what a game costs outside Play Pass (the store
  page has it).
- **Content.** It has no age rating (PEGI/ESRB), description, release date, last
  update or size.
- **Ratings per country.** Ratings come from the US store; local averages differ and
  are often missing for small games.
- **Play Pass per country.** The badge can't be read per country, so "offered in the
  country's store" stands in for "in that country's Play Pass".

### 5. Countries

Games not offered, out of 1,857: Australia 1, Brazil 14, Canada 0, France 13,
Germany 7, Italy 7, Japan 25, the Netherlands 42, Belgium 43, Spain 7, the UK 7,
the US 0. 29 games are sold under a separate local edition somewhere (mostly
Kairosoft in Japan, Layton in Europe), and the Play links follow it. The country
menu has since grown to all 101 countries on Google's Play Pass list.

## Feature ideas

Value is how much it helps someone browsing the page; effort is roughly a few hours
(low) up to a day (medium). Built since (4 October 2026): 1, 2 (monthly), 3, 4, 5, 6, 7, 8, 10, 11,
12 (eight languages), 14 (installable, offline) and 15 to 17, plus trailers in the page, shareable favourites lists, a Discover
that learns from your swipes, and a browser check before each monthly update is published.
Google Play no longer publishes download sizes, so the detail view has no size.

| # | Feature | Value | Effort | Notes |
| --- | --- | --- | --- | --- |
| 1 | Show official store titles (built) | High | Low | Fixes the ~170 misspelled or renamed titles; YTECHB's name stays searchable |
| 2 | Automatic update (built, monthly) | High | Medium | GitHub Actions runs YTECHB + crawl + refresh + countries + build, then commits; the page stays current without anyone running scripts |
| 3 | "New in Play Pass" badge and sort (built) | High | Medium | Needs a first-seen date per game, starting now; the crawl already catches new games first |
| 4 | Shareable links (built) | High | Low | Keeps search, genre, tag, sort and country in the URL |
| 5 | Game detail view (built) | High | Medium | Tap a card for description, all screenshots, age rating, price outside Play Pass, size, last update; loaded per game so the page stays small |
| 6 | Faster page (built: 1.1 MB instead of 2.9, ready in 1.1 s instead of 3.7 on a slow phone) | Medium | Medium | Shared icons instead of inline SVG, fewer screenshot dots, render cards as they scroll in; about 3x fewer elements |
| 7 | Favourites and "played" marks (built, with Discover swiping) | Medium | Low | Saved in the browser, with a filter |
| 8 | Age rating filter (built) | Medium | Low | For parents: PEGI 3/7/12/16/18 |
| 9 | "Recently left Play Pass" list | Medium | Low | Comes free with the history from #3 |
| 10 | Developer filter (built) | Medium | Low | Tap a developer name to see their games |
| 11 | Play Pass apps section (built) | Medium | Low | The 109 non-game apps (kids' learning, photo, music, tools) |
| 12 | Dutch interface (built, with German, French, Spanish, Italian, Portuguese and Japanese) | Medium | Medium | Language switch, picked from the browser |
| 13 | Value counter | Low | Low | "These games cost €X outside Play Pass" |
| 14 | Install as an app (built, works offline) | Low | Low | Home-screen icon, works offline |
| 15 | More like this (built) | Medium | Low | In the detail view: games with the most similar tags, and the developer's other games |
| 16 | New since your last visit (built) | Medium | Low | A chip with what the monthly updates added since you last came, until you mark it as seen |
| 17 | Forgiving search (built) | Medium | Low | Spaces and punctuation don't matter; a word that matches nothing is matched as a typo |

## Tooling gaps

- **Single update command.** This is fixed: `update.py` chains the scripts, and a GitHub
  workflow runs it on the 1st of every month.
- **Tests.** Half fixed: `check_page.js` checks the page in a headless browser before
  every monthly push. The matcher still has no unit tests.
- **Crawl convergence.** This is fixed: the crawler now follows developer links on
  every game page, so a single run finds what used to take two.

## Suggested order

1. Official store titles (#1) and shareable links (#4): quick, visible wins.
2. First-seen dates and the automatic weekly update (#2, #3, #9), since history only
   builds up from the day it starts.
3. The game detail view with age rating and price (#5, #8), and the faster page (#6).
