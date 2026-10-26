/** Layout Settings -> Graph Data: desktop 1440 dua kartu, mobile 390 bertumpuk. */
import assert from "node:assert/strict";
import { chromium } from "/root/.npm/_npx/e41f203b7505f1fb/node_modules/playwright-core/index.mjs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5199";
const OUT = process.env.OUT ?? "/root/.hermes/profiles/skillmanager/cache/scratch/graph-data";
const me = { id: 1, username: "demo", full_name: "Demo", role: "admin", admin_id: null, must_change_password: false };
const stats = [
  { kind: "traffic", rows: 12345, oldest_at: "2026-09-01T00:00:00Z", newest_at: "2026-10-26T00:00:00Z", size_bytes: 3145728 },
  { kind: "signal", rows: 4567, oldest_at: "2026-08-01T00:00:00Z", newest_at: "2026-10-26T00:00:00Z", size_bytes: 1048576 },
];
const olts = [{ id: 10, name: "OLT UJI", host: "192.0.2.1", vendor: "zte", model: "C320" }];

const browser = await chromium.launch({
  executablePath: "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
  args: ["--no-sandbox"],
});
const ctx = await browser.newContext();
await ctx.addInitScript(() => localStorage.setItem("token", "harness"));
await ctx.route("**/api/**", async (route) => {
  const url = route.request().url();
  if (/\/api\/auth\/me$/.test(url)) return route.fulfill({ json: me });
  if (/\/api\/settings\/graph-data\/stats$/.test(url)) return route.fulfill({ json: stats });
  if (/\/api\/settings\/graph-data\/retention$/.test(url)) return route.fulfill({ json: { traffic: 30, signal: 90 } });
  if (/\/api\/olts$/.test(url)) return route.fulfill({ json: olts });
  return route.fulfill({ status: 404, json: { detail: "tidak distub" } });
});
const page = await ctx.newPage();
let checks = 0;
for (const [view, width, height, columns] of [["desktop-1440", 1440, 1000, 2], ["mobile-390", 390, 1100, 1]]) {
  await page.setViewportSize({ width, height });
  await page.goto(`${BASE}/settings/graph-data`, { waitUntil: "networkidle" });
  await page.waitForSelector("[data-graph-kind=signal]", { timeout: 15_000 });
  const layout = await page.evaluate(() => {
    const grid = document.querySelector("[data-graph-grid]");
    const cards = [...grid.children].map((e) => e.getBoundingClientRect());
    return {
      docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      first: { x: Math.round(cards[0].x), y: Math.round(cards[0].y), width: Math.round(cards[0].width) },
      second: { x: Math.round(cards[1].x), y: Math.round(cards[1].y), width: Math.round(cards[1].width) },
    };
  });
  assert.ok(layout.docOverflow <= 1, `${view}: overflow ${layout.docOverflow}px`);
  if (columns === 2) {
    assert.ok(Math.abs(layout.first.y - layout.second.y) <= 1, `${view}: kartu tidak berdampingan`);
    assert.ok(layout.second.x > layout.first.x + layout.first.width, `${view}: kartu kedua tidak di kanan`);
  } else {
    assert.ok(layout.second.y > layout.first.y, `${view}: kartu tidak bertumpuk`);
    assert.ok(Math.abs(layout.first.x - layout.second.x) <= 1, `${view}: kartu mobile tidak sejajar`);
  }
  await page.screenshot({ path: `${OUT}-${view}.png`, fullPage: true });
  checks += 1;
  console.log(`ok  ${view}: ${columns} kolom, tanpa overflow -> ${OUT}-${view}.png`);
}
await browser.close();
console.log(`\n${checks} pemeriksaan layout Graph Data lulus`);
