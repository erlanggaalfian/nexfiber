/** Pemeriksaan tata letak Detail ONU di browser nyata (desktop 1440 + mobile 390).
 *
 *  Respons API di-stub HANYA untuk render halaman di harness ini — tidak ada data contoh
 *  yang masuk ke kode aplikasi. Yang diperiksa: tidak ada overflow horizontal
 *  (scrollWidth <= clientWidth) di kedua ukuran.
 *
 *      node frontend/tests/onu-detail.layout.mjs           # butuh `vite` di 127.0.0.1:5199
 */
import assert from "node:assert/strict";
import { chromium } from "/root/.npm/_npx/e41f203b7505f1fb/node_modules/playwright-core/index.mjs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5199";
const OUT = process.env.OUT ?? "/tmp/onu-detail";

const me = { id: 1, username: "demo", full_name: "Demo", role: "admin", admin_id: null, must_change_password: false };
const detail = {
  id: 91, serial_number: "AAAA00000001", name: null, customer_name: "Pelanggan Uji",
  customer_id: "C-1", olt_id: 10, olt_name: "OLT-UJI", slot: 1, port: 6, onu_index: 91,
  onu_type: "F670L", status: "online", config_state: "configured", admin_state: "enabled",
  rx_power_dbm: -24.31, olt_rx_power_dbm: null,
  download_profile_name: "50M-DN", upload_profile_name: "50M-UP",
  vlan_number: 1020, zone_name: "Zona Uji", splitter_name: "ODP-01",
  last_seen_at: "2026-10-25T01:00:00Z", last_down_at: null, last_down_reason: null,
  pon_port_id: 3, description: null, address: "Jalan Uji 1", phone: null, contact: null,
  external_id: null, auth_type: "sn", loid: null, match_state: "match",
  bias_current_ma: 12.5, last_sync_at: "2026-10-25T01:00:00Z",
  preset_id: null, preset_name: null, onu_type_id: 7, registered_by_name: "demo",
  tx_power_dbm: null, temperature_c: null, voltage_v: null, distance_m: 11990,
  mac_address: null, ip_address: "192.168.22.98", vlan_id: 5, zone_id: 2, splitter_id: 4,
  splitter_port: 3, download_speed_profile_id: 1, upload_speed_profile_id: 2,
  line_profile_id: "LP1", srv_profile_id: "SP1", software_version: "V1.0", hardware_version: "H1",
  onu_mode: "Routing", wan_mode: "pppoe", mgmt_ip_mode: "dhcp",
  pppoe_username: "user@isp.id", latitude: -6.2, longitude: 106.81666,
  registered_at: "2026-10-23T06:53:24Z",
  service_vlans: [{ vlan_id: 1020, name: "Internet", is_management: false, in_master: true }],
  device_metadata: null,
};
const onuTypes = [{
  id: 7, pon_type: "gpon", name: "F670L", eth_ports: 4, wifi_ssids: 4, voip_ports: 2,
  catv: false, capability: "routing", allow_custom_profiles: true,
}];

const routes = [
  [/\/api\/auth\/me$/, me],
  [/\/api\/onus\/[^/]+\/signal/, []],
  // Histori trafik: sampel sintetis HANYA untuk harness (bukan data pelanggan nyata),
  // supaya grafik benar-benar dirender dan overflow-nya ikut terukur.
  [/\/api\/onus\/[^/]+\/traffic\/history/, Array.from({ length: 24 }, (_, i) => ({
    sampled_at: new Date(Date.UTC(2026, 9, 25, i)).toISOString(),
    in_bps: i % 7 === 0 ? null : 1_000_000 * (i + 1),
    out_bps: i % 7 === 0 ? null : 200_000 * (i + 1),
  }))],
  [/\/api\/onus\/[^/]+\/logs/, []],
  [/\/api\/onus\/by-id\//, detail],
  [/\/api\/onus\/[^/?]+$/, detail],
  [/\/api\/onu-types/, onuTypes],
  [/\/api\/speed-profiles/, []],
  [/\/api\/vlans/, []],
  [/\/api\/zones/, []],
  [/\/api\/splitters/, []],
];

const browser = await chromium.launch({
  executablePath: "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
  args: ["--no-sandbox"],
});
const ctx = await browser.newContext();
await ctx.addInitScript(() => localStorage.setItem("token", "harness"));
await ctx.route("**/api/**", async (route) => {
  const url = route.request().url();
  for (const [re, body] of routes) {
    if (re.test(url)) return route.fulfill({ json: body });
  }
  return route.fulfill({ status: 404, json: { detail: "tidak distub" } });
});

const page = await ctx.newPage();
for (const [name, width, height] of [["desktop-1440", 1440, 1200], ["mobile-390", 390, 900]]) {
  await page.setViewportSize({ width, height });
  await page.goto(`${BASE}/onu/91`, { waitUntil: "networkidle" });
  // Bagian atas kini datar (tanpa kartu "Informasi & status ONU"); penanda siap-render
  // yang stabil adalah baris identitas pertama (`OLT`), yang hanya ada setelah detail
  // ONU benar-benar ter-render.
  await page.waitForSelector("text=Configuration Preset", { timeout: 15_000 });
  await page.screenshot({ path: `${OUT}-${name}.png`, fullPage: true });
  const over = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    worst: [...document.querySelectorAll("*")]
      .filter((e) => e.scrollWidth - e.clientWidth > 1)
      .filter((e) => {
        const c = e.className.toString();
        return !c.includes("overflow-x-auto") && !c.includes("sr-only");
      })
      .map((e) => `${e.tagName}.${e.className}`.slice(0, 90) + ` ${e.scrollWidth}/${e.clientWidth}`),
    leaves: [...document.querySelectorAll("*")]
      .filter((e) => e.children.length === 0 && e.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
      .map((e) => `${e.tagName}.${e.className}`.slice(0, 70) + ` right=${Math.round(e.getBoundingClientRect().right)}`),
  }));
  assert.ok(over.doc <= 1, `${name}: overflow horizontal ${over.doc}px`);
  assert.deepEqual(over.worst, [], `${name}: elemen meluber tanpa overflow-x-auto`);
  console.log(`ok  ${name}: tanpa overflow horizontal -> ${OUT}-${name}.png`);
}
await browser.close();
console.log("\n2 pemeriksaan layout lulus");
