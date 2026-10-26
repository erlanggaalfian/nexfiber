/** Pemeriksaan tata letak MODAL aksi ONU di browser nyata (desktop 1440 + mobile 390).
 *
 *  Tiap modal dibuka dari titik buka yang sesungguhnya dipakai operator (baris spesifikasi,
 *  tombol pensil tabel port, panel Aksi), lalu diperiksa: dialog muncul, tidak ada overflow
 *  horizontal, dan di 390px lebarnya tidak melebihi viewport.
 *
 *  Respons API di-stub HANYA di harness ini (termasuk `/actions` dan `/config-options` yang
 *  backend-nya dikerjakan paralel) — tidak ada data contoh di kode aplikasi.
 *
 *      node frontend/tests/onu-modals.layout.mjs        # butuh `vite` di 127.0.0.1:5199
 */
import assert from "node:assert/strict";
import { chromium } from "/root/.npm/_npx/e41f203b7505f1fb/node_modules/playwright-core/index.mjs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5199";
const OUT = process.env.OUT ?? "/tmp/onu-modal";

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

/** Satu aksi sengaja `supported:false` untuk membuktikan modal tetap terbuka + tombol mati. */
const KINDS = [
  "attached-vlans", "onu-mode", "eth-port", "wifi-port", "wifi-clear", "external-id",
  "onu-type", "speed-profile", "replace-sn", "mgmt-ip", "voip-enable",
  "voip-disable", "iptv", "reboot", "disable", "enable", "restore-factory",
  "resync-config", "delete",
];
const actions = {
  actions: KINDS.map((kind) => ({
    kind,
    supported: kind !== "iptv",
    writes_device: !["external-id"].includes(kind),
    note: kind === "iptv" ? "driver belum punya perintah IPTV" : null,
  })),
};
const configOptions = {
  vlans: [
    { number: 1020, name: "Internet", is_management: false },
    { number: 1021, name: "Internet-B", is_management: false },
    { number: 4000, name: "Management", is_management: true },
  ],
  zones: [{ id: 2, name: "Zona Uji" }],
  splitters: [{ id: 4, name: "ODP-01", zone_id: 2, ports: 8 }],
  sectors: [{ id: 1, name: "Sektor 1" }],
  speed_profiles: [
    { id: 1, name: "50M-DN", direction: "download" },
    { id: 2, name: "50M-UP", direction: "upload" },
  ],
  onu_types: [{ id: 7, name: "F670L" }],
  wan_modes: ["webpage", "dhcp", "static", "pppoe"],
};

const routes = [
  [/\/api\/auth\/me$/, me],
  [/\/api\/onus\/[^/]+\/signal/, []],
  [/\/api\/onus\/[^/]+\/logs/, []],
  [/\/api\/onus\/[^/]+\/actions$/, actions],
  [/\/api\/onus\/[^/]+\/config-options$/, configOptions],
  [/\/api\/onus\/by-id\//, detail],
  [/\/api\/onus\/[^/?]+$/, detail],
  [/\/api\/onu-types/, onuTypes],
  [/\/api\/speed-profiles/, []],
  [/\/api\/vlans/, []],
  [/\/api\/zones/, []],
  [/\/api\/splitters/, []],
];

/** [nama file, cara membuka modal, judul yang harus muncul] */
const CASES = [
  ["attached-vlans", (p) => p.getByRole("button", { name: /^Attached VLANs/ }).click(), "Update attached VLANs"],
  ["onu-mode", (p) => p.getByRole("button", { name: /^ONU mode/ }).click(), "Update ONU mode"],
  ["location", (p) => p.getByRole("button", { name: /^Zone/ }).click(), "Update location details"],
  ["eth-port", (p) => p.getByLabel("Konfigurasi eth_0/1").and(p.locator(":visible")).click(), "Configure ethernet port eth_0/1"],
  ["wifi-port", (p) => p.getByLabel("Konfigurasi wifi_0/1").and(p.locator(":visible")).click(), "Configure WiFi port wifi_0/1"],
  ["onu-type", (p) => p.getByRole("button", { name: /^ONU type/ }).click(), "Change ONU type"],
  ["external-id", (p) => p.getByRole("button", { name: /^ONU external ID/ }).click(), "Update ONU external ID"],
  // Titik buka "Ubah speed"/"Replace ONU / ganti SN" di blok Aksi DIBUANG (permintaan pemilik):
  // keduanya kini hanya dibuka dari tabel Profil Kecepatan dan baris identitas SN.
  ["speed-profile", (p) => p.getByLabel("Konfigurasi profil kecepatan").and(p.locator(":visible")).click(), "Configure speed profiles"],
  ["replace-sn", (p) => p.getByRole("button", { name: /^SN/ }).click(), "Replace ONU by SN"],
  ["mgmt-ip", (p) => p.getByRole("button", { name: /^Mgmt IP/ }).click(), "Update Management and VoIP IP"],
  ["voip-enable", (p) => p.getByRole("button", { name: /^Layanan VoIP/ }).click(), "Enable VoIP"],
  ["iptv", (p) => p.getByRole("button", { name: /^IPTV/ }).click(), "Update IPTV"],
  ["reboot", (p) => p.getByRole("button", { name: "Reboot" }).first().click(), "Reboot"],
  ["disable", (p) => p.getByRole("button", { name: "Nonaktifkan ONU" }).click(), "Disable ONU"],
  ["resync", (p) => p.getByRole("button", { name: "Resync config" }).first().click(), "Recreate OLT config for this ONU"],
  ["restore-factory", (p) => p.getByRole("button", { name: "Restore factory" }).click(), "Restore to factory defaults"],
  ["delete", (p) => p.getByRole("button", { name: "Hapus" }).click(), "Delete"],
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
let checks = 0;
for (const [view, width, height] of [["desktop-1440", 1440, 1200], ["mobile-390", 390, 900]]) {
  await page.setViewportSize({ width, height });
  await page.goto(`${BASE}/onu/91`, { waitUntil: "networkidle" });
  // Bagian atas halaman kini datar (tanpa kartu "Informasi & status ONU"): penanda
  // siap-render yang stabil adalah salah satu label baris identitas.
  await page.waitForSelector("text=Configuration Preset", { timeout: 15_000 });

  for (const [name, open, title] of CASES) {
    await open(page);
    const dialog = page.locator("[role=dialog]");
    await dialog.waitFor({ state: "visible", timeout: 5_000 });
    await page.waitForFunction(
      (t) => document.querySelector("[role=dialog]")?.textContent?.includes(t) ?? false,
      title, { timeout: 5_000 },
    );
    // Animasi fade-in modal 150 ms: tunggu opasitas penuh supaya tangkapan layar tidak tembus.
    await page.waitForFunction(() => {
      const d = document.querySelector("[role=dialog]");
      return d !== null && Number(getComputedStyle(d).opacity) > 0.99;
    }, null, { timeout: 5_000 });
    await page.screenshot({ path: `${OUT}-${name}-${view}.png` });

    const over = await page.evaluate(() => {
      const dlg = document.querySelector("[role=dialog]");
      const vw = document.documentElement.clientWidth;
      const box = dlg.getBoundingClientRect();
      return {
        doc: document.documentElement.scrollWidth - vw,
        wide: Math.round(box.width) - vw,
        right: Math.round(box.right) - vw,
        inner: [...dlg.querySelectorAll("*")]
          .filter((e) => e.scrollWidth - e.clientWidth > 1)
          .filter((e) => {
            const c = e.className.toString();
            return !c.includes("overflow-y-auto") && !c.includes("overflow-x-auto") && !c.includes("sr-only");
          })
          .map((e) => `${e.tagName}.${e.className}`.slice(0, 80)),
      };
    });
    assert.ok(over.doc <= 1, `${name}/${view}: overflow halaman ${over.doc}px`);
    assert.ok(over.wide <= 0, `${name}/${view}: modal lebih lebar dari viewport (${over.wide}px)`);
    assert.ok(over.right <= 1, `${name}/${view}: modal keluar sisi kanan (${over.right}px)`);
    assert.deepEqual(over.inner, [], `${name}/${view}: isi modal meluber`);

    /** Aksi `supported:false` (iptv di stub) harus tetap terbuka dengan tombol Simpan mati. */
    if (name === "iptv") {
      const txt = await dialog.textContent();
      assert.ok(txt.includes("Belum didukung"), `${name}/${view}: catatan "Belum didukung" tidak muncul`);
      assert.equal(
        await dialog.getByRole("button", { name: "Update" }).isDisabled(), true,
        `${name}/${view}: tombol Update seharusnya mati`,
      );
    }
    /** Delete & Restore: tombol aksi mati sampai serial number diketik persis. */
    if (name === "delete" || name === "restore-factory") {
      const btn = dialog.getByRole("button", { name: name === "delete" ? "Delete" : "Restore to factory defaults" });
      assert.equal(await btn.isDisabled(), true, `${name}/${view}: tombol harus mati sebelum konfirmasi`);
      await dialog.getByLabel("Konfirmasi serial number").fill(detail.serial_number);
      assert.equal(await btn.isDisabled(), false, `${name}/${view}: tombol harus hidup setelah SN cocok`);
    }

    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "detached", timeout: 5_000 });
    checks += 1;
  }
  console.log(`ok  ${view}: ${CASES.length} modal tanpa overflow -> ${OUT}-*-${view}.png`);
}
await browser.close();
console.log(`\n${checks} pemeriksaan modal lulus`);
