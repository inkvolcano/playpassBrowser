#!/usr/bin/env node
// A browser check of the built page, run by the monthly workflow before it pushes (and by hand:
// `node check_page.js` after `npm install playwright`). It serves this folder on a local port, opens
// index.html in headless Chromium in every interface language and checks that the cards, search,
// country menu, detail view and Discover work without errors, and (in English) that the page can be
// installed as an app and reloads offline. Requests to other sites are blocked, so the screenshots
// don't load and the check doesn't depend on them. Exit code 1 if anything fails.
const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = __dirname;
const LANGS = ["en", "nl", "de", "fr", "es", "it", "pt", "ja"];
const TYPES = { ".html": "text/html; charset=utf-8", ".json": "application/json", ".js": "text/javascript" };

function serve() {
  const server = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!file.startsWith(ROOT)) { res.writeHead(403).end(); return; }
    fs.readFile(fs.existsSync(file) && fs.statSync(file).isDirectory() ? path.join(file, "index.html") : file, (err, body) => {
      if (err) { res.writeHead(404).end(); return; }
      res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" }).end(body);
    });
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

(async () => {
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}/index.html`;
  const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
  const failures = [];
  const check = (lang, what, ok, detail = "") => {
    if (!ok) failures.push(`[${lang}] ${what}${detail ? ": " + detail : ""}`);
    return ok;
  };

  for (const lang of LANGS) {
    // the service worker only in English: it keeps what it fetched, which the other runs shouldn't share
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: lang === "en" ? "allow" : "block" });
    await ctx.route((url) => url.hostname !== "127.0.0.1", (route) => route.abort());
    await ctx.addInitScript((l) => { try { localStorage.setItem("ppb:lang", l); } catch (e) { /* no storage */ } }, lang);
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
    try {
      await page.goto(base);
      await page.waitForFunction(() => document.getElementById("status").textContent, null, { timeout: 15000 });
      const info = await page.evaluate(() => {
        const D = JSON.parse(document.getElementById("data").textContent);
        return { lang: document.documentElement.lang, rows: D.games.length, regions: D.regions.length,
          countries: document.querySelectorAll("#region option").length, cards: document.querySelectorAll(".card").length,
          status: document.getElementById("status").textContent };
      });
      check(lang, "page language", info.lang === lang, info.lang);
      check(lang, "game count", info.rows >= 1000, String(info.rows));
      check(lang, "cards shown", info.cards > 0 && info.cards <= 36, String(info.cards));
      check(lang, "country menu", info.countries === info.regions && info.regions >= 2, `${info.countries} of ${info.regions}`);

      await page.fill("#q", "puzzle");
      await page.waitForTimeout(400);
      const found = await page.evaluate(() => [document.getElementById("status").textContent, document.querySelectorAll(".card").length]);
      check(lang, "search", found[0] !== info.status && found[1] > 0, found.join(" / "));
      await page.fill("#q", "");
      await page.waitForTimeout(300);

      await page.click(".card .open");
      await page.waitForFunction(() => document.querySelector("#d-body .d-summary, #d-body .d-desc-text"), null, { timeout: 10000 })
        .catch(() => check(lang, "detail view", false, "no description loaded"));
      check(lang, "detail view open", await page.evaluate(() => document.getElementById("detail").open));
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);

      await page.click("#discover-btn");
      await page.waitForSelector(".dc-card", { timeout: 5000 }).catch(() => check(lang, "Discover", false, "no card"));
      await page.click("#dc-close");
      await page.waitForTimeout(300);

      if (lang === "en") {
        const before = await page.locator(".card").count();
        for (let k = 0; k < 3; k++) {
          await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
          await page.waitForTimeout(400);
        }
        check(lang, "more cards on scrolling", (await page.locator(".card").count()) > before);
        await page.selectOption("#sort", "genre");
        await page.waitForTimeout(400);
        check(lang, "by genre", (await page.locator(".group").count()) > 0);
        const missing = await page.evaluate(async () => {  // a sample of the detail files the page will ask for
          const D = JSON.parse(document.getElementById("data").textContent);
          const ids = D.games.filter((r, i) => i % 97 === 0).map((r) => r[2]).filter(Boolean);
          const res = await Promise.all(ids.map((id) => fetch(`details/${encodeURIComponent(id)}.json`).then((r) => r.ok)));
          return ids.filter((id, i) => !res[i]);
        });
        check(lang, "detail files", !missing.length, missing.join(", "));

        // forgiving search: a word only one title has, with two letters swapped, still finds that game
        const typo = await page.evaluate(() => {
          const D = JSON.parse(document.getElementById("data").textContent);
          const words = new Map();
          D.games.forEach((r) => new Set(r[0].toLowerCase().match(/[a-z]{8,}/g) || []).forEach((w) => words.set(w, words.has(w) ? null : r[0])));
          const [word, title] = [...words].find(([w, t]) => t && !D.games.some((r) => r[0] !== t && JSON.stringify(r).toLowerCase().includes(w))) || [];
          return word ? { title, text: word.slice(0, 3) + word[4] + word[3] + word.slice(5) } : null;
        });
        if (typo) {
          await page.fill("#q", typo.text);
          await page.waitForTimeout(400);
          const titles = await page.evaluate(() => [...document.querySelectorAll(".card .title")].map((x) => x.textContent));
          check(lang, "search with a typo", titles.includes(typo.title), `${typo.text}: ${titles.slice(0, 5).join(", ")}`);
          console.log(`typo search: “${typo.text}” finds ${typo.title}`);
          await page.fill("#q", "");
          await page.waitForTimeout(300);
        }

        // More like this: the most-rated game with a few tags gets a row of similar games
        const popular = await page.evaluate(() => {
          const D = JSON.parse(document.getElementById("data").textContent);
          return D.games.filter((r) => r[2] && (r[11] || []).length >= 4).sort((a, b) => (b[9] || 0) - (a[9] || 0))[0][2];
        });
        await page.evaluate((id) => { location.hash = "game=" + encodeURIComponent(id); }, popular);
        check(lang, "more like this", await page.waitForSelector("#d-body .d-like .mini", { timeout: 5000 }).then(() => true, () => false), popular);
        await page.keyboard.press("Escape");
        await page.waitForTimeout(300);

        // installable app: a manifest without errors, nothing but the test browser's private mode in
        // the way of installing, and a service worker that brings the page back without a connection
        const cdp = await ctx.newCDPSession(page);
        const manifest = await cdp.send("Page.getAppManifest");
        check(lang, "manifest", manifest.url && !manifest.errors.length && JSON.parse(manifest.data || "{}").name,
          JSON.stringify(manifest.errors));
        const { installabilityErrors } = await cdp.send("Page.getInstallabilityErrors");
        const blocking = installabilityErrors.map((e) => e.errorId).filter((id) => id !== "in-incognito");
        check(lang, "installable", !blocking.length, blocking.join(", "));
        const sw = await page.evaluate(() => Promise.race([navigator.serviceWorker.ready.then((r) => !!r.active),
          new Promise((resolve) => setTimeout(() => resolve(false), 10000))]));
        if (check(lang, "service worker", sw)) {
          await page.reload();
          await page.waitForFunction(() => navigator.serviceWorker.controller, null, { timeout: 10000 }).catch(() => {});
          await ctx.setOffline(true);
          await page.reload();
          const offline = await page.waitForFunction(() => document.getElementById("status").textContent, null, { timeout: 10000 })
            .then(() => true, () => false);
          check(lang, "works offline", offline);
          await ctx.setOffline(false);
        }
      }
    } catch (e) {
      check(lang, "page check", false, e.message.split("\n")[0]);
    }
    check(lang, "no errors", !errors.length, errors.slice(0, 3).join(" | "));
    console.log(`${lang}: ${failures.some((f) => f.startsWith(`[${lang}]`)) ? "FAILED" : "ok"}`);
    await ctx.close();
  }

  // "New for you": someone whose last visit came before the data saw every game added since tracking began
  {
    const ctx = await browser.newContext({ serviceWorkers: "block" });
    await ctx.route((url) => url.hostname !== "127.0.0.1", (route) => route.abort());
    await ctx.addInitScript(() => {
      for (const [k, v] of [["lang", "en"], ["region", "US"], ["seenData", "2000-01-01"], ["newSince", "2000-01-01"]]) localStorage.setItem("ppb:" + k, v);
    });
    const page = await ctx.newPage();
    await page.goto(base);
    await page.waitForFunction(() => document.getElementById("status").textContent, null, { timeout: 15000 });
    const r = await page.evaluate(() => {
      const D = JSON.parse(document.getElementById("data").textContent), apps = D.genres.indexOf("Apps");
      const added = D.games.filter((g) => g[15] && g[15] > D.meta.trackingSince && g[1] !== apps).length;
      return { added, shown: !document.getElementById("since-chip").hidden, chip: document.getElementById("since-chip").textContent.trim() };
    });
    check("en", "new for you", r.added ? r.shown && r.chip.endsWith(String(r.added).replace(/\B(?=(\d{3})+$)/g, ",")) : !r.shown, JSON.stringify(r));
    console.log(`new for you: ${r.added ? r.chip : "nothing added since tracking began"}`);
    await ctx.close();
  }

  await browser.close();
  server.close();
  if (failures.length) {
    console.log("\nPage check failed:\n  " + failures.join("\n  "));
    process.exit(1);
  }
  console.log("Page check passed.");
})();
