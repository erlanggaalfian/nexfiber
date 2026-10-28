/** Kontrak statis Settings -> Graph Data. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const page = await readFile(new URL("../src/pages/settings/GraphData.tsx", import.meta.url), "utf8");
const nav = await readFile(new URL("../src/lib/nav.ts", import.meta.url), "utf8");
const routes = await readFile(new URL("../src/main.tsx", import.meta.url), "utf8");
let passed = 0;
const check = (name, fn) => { fn(); passed += 1; console.log(`ok  ${name}`); };

check("route dan nav Graph Data manager tersedia", () => {
  assert.match(nav, /Graph Data.*\/settings\/graph-data.*MANAGERS/);
  // Sejak audit 2026-10-28 route ini dibungkus RequireSettingsRole (manager-only),
  // jadi pola lama tanpa wrapper tidak berlaku lagi.
  assert.match(routes, /path="\/settings\/graph-data" element={<RequireSettingsRole roles={MANAGERS}><GraphData \/><\/RequireSettingsRole>}/);
});
check("dua jenis memakai satu markup kartu", () => {
  assert.match(page, /\(\["traffic", "signal"\] as Kind\[\]\)\.map/);
  assert.match(page, /data-graph-kind={kind}/);
});
check("retensi dan alur pratinjau-konfirmasi-hapus terhubung API", () => {
  for (const endpoint of ["/retention", "/preview-delete", "/delete"]) assert.ok(page.includes(endpoint));
  for (const label of ["Pratinjau", "Hapus data", "Retensi auto-delete"]) assert.ok(page.includes(label));
  assert.match(page, /<Confirm/);
});
check("tanggal dibatasi hari WIB dan OLT opsional", () => {
  assert.match(page, /timeZone: "Asia\/Jakarta"/);
  assert.match(page, /max={todayWib\(\)}/);
  assert.match(page, /Semua OLT dalam scope/);
});
console.log(`\n${passed} pemeriksaan Graph Data lulus`);
