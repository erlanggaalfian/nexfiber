/** Regresi Detail ONU: hitungan delta trafik + bentuk halaman. Dijalankan tanpa framework:
 *
 *      node frontend/tests/onu-detail.check.mjs
 *
 *  Node mengurai `../src/lib/traffic.ts` langsung (type stripping bawaan Node >= 22.18/23),
 *  jadi fungsi yang diuji benar-benar fungsi yang dipakai halaman — bukan salinan.
 *  Bagian layout diperiksa sebagai teks karena repo ini tidak punya renderer DOM; kompilasi
 *  tipe tetap dijaga `npm run build` (`tsc -b`).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { deltaMbps } from "../src/lib/traffic.ts";

const here = dirname(fileURLToPath(import.meta.url));
const page = readFileSync(join(here, "..", "src", "pages", "OnuDetail.tsx"), "utf8");

let passed = 0;
const check = (name, fn) => {
  fn();
  passed += 1;
  console.log(`ok  ${name}`);
};

const sample = (t, inO, outO, bits = 64) =>
  ({ sampled_at: t, in_octets: String(inO), out_octets: String(outO), counter_bits: bits });

// ---------------------------------------------------------------- delta Mbps

check("delta lurus: 1 MB dalam 5 s = 1,6777 Mbps", () => {
  const p = deltaMbps(
    sample("2026-10-24T10:00:00Z", 0, 0),
    sample("2026-10-24T10:00:05Z", 1_048_576, 524_288),
  );
  assert.ok(p);
  assert.ok(Math.abs(p.inMbps - 1.677_721_6) < 1e-9, p.inMbps);
  assert.ok(Math.abs(p.outMbps - 0.838_860_8) < 1e-9, p.outMbps);
});

check("wrap counter 32 bit dihitung, bukan jadi negatif", () => {
  const max32 = 2 ** 32;
  const p = deltaMbps(
    sample("2026-10-24T10:00:00Z", max32 - 1000, 0, 32),
    sample("2026-10-24T10:00:05Z", 24, 0, 32),
  );
  assert.ok(p);
  // 1024 oktet * 8 / 5 s
  assert.ok(Math.abs(p.inMbps - (1024 * 8) / 5 / 1e6) < 1e-12, p.inMbps);
});

check("counter 64 bit di atas 2^53 tetap presisi (BigInt, bukan Number)", () => {
  const base = 2n ** 60n;
  const p = deltaMbps(
    sample("2026-10-24T10:00:00Z", base, base),
    sample("2026-10-24T10:00:05Z", base + 1_250_000n, base + 1n),
  );
  assert.ok(p);
  assert.ok(Math.abs(p.inMbps - (1_250_000 * 8) / 5 / 1e6) < 1e-9, p.inMbps);
  // Selisih 1 oktet tidak boleh hilang jadi 0 karena pembulatan float.
  assert.ok(p.outMbps > 0, p.outMbps);
});

check("reset counter (lompatan > setengah ruang) tidak menghasilkan titik palsu", () => {
  assert.equal(
    deltaMbps(
      sample("2026-10-24T10:00:00Z", 5_000_000_000, 0),
      sample("2026-10-24T10:00:05Z", 10, 0),
    ),
    null,
  );
});

check("sampel tanpa kemajuan waktu / lebar counter berubah ditolak", () => {
  assert.equal(
    deltaMbps(sample("2026-10-24T10:00:05Z", 0, 0), sample("2026-10-24T10:00:05Z", 10, 10)),
    null,
  );
  assert.equal(
    deltaMbps(sample("2026-10-24T10:00:00Z", 0, 0, 32), sample("2026-10-24T10:00:05Z", 10, 10, 64)),
    null,
  );
  assert.equal(
    deltaMbps(sample("bukan-tanggal", 0, 0), sample("2026-10-24T10:00:05Z", 10, 10)),
    null,
  );
});

// ------------------------------------------------------------ bentuk halaman

check("urutan blok mengikuti desain: kartu atas, diagnostik, trafik, profil, port, wifi, aksi", () => {
  const order = [
    "Informasi & status ONU",
    "Diagnostik ONU:",
    'label="Trafik / Sinyal"',
    'label="Profil Kecepatan"',
    'label="Port Ethernet"',
    'label="WiFi"',
    "Restore factory",
  ];
  const at = order.map((m) => {
    const i = page.indexOf(m);
    assert.notEqual(i, -1, `blok hilang: ${m}`);
    return i;
  });
  for (let i = 1; i < at.length; i += 1) assert.ok(at[i] > at[i - 1], order[i]);
});

check("diagnostik memakai endpoint kontrak backend + view sebagai body", () => {
  assert.ok(page.includes("/diagnostics"), "endpoint diagnostics");
  assert.ok(page.includes("json: { view }"), "body { view }");
  for (const v of ['"status"', '"running"', '"software"']) assert.ok(page.includes(v), v);
});

check("running-config hanya dirender untuk manager (RBAC backend tetap penentu)", () => {
  const i = page.indexOf("DIAG_LABEL.running");
  assert.notEqual(i, -1);
  assert.ok(page.slice(i - 400, i).includes("isManager"), "tombol running-config tanpa isManager");
});

check("LIVE: interval 5 s, auto-off 10 menit, jeda saat tab tersembunyi, mati saat unmount", () => {
  assert.ok(page.includes("const TRAFFIC_MS = 5_000"), "interval 5 s");
  assert.ok(page.includes("LIVE_MAX_MS = 10 * 60_000"), "auto-off 10 menit");
  assert.ok(page.includes("document.hidden"), "jeda saat tab tersembunyi");
  assert.ok(page.includes("clearInterval(id)"), "interval dibersihkan");
  assert.ok(page.includes("useEffect(() => () => setLive(false), [])"), "LIVE mati saat unmount");
});

check("tidak ada angka trafik karangan: grafik butuh dua sampel nyata", () => {
  assert.ok(page.includes("points.length < 2"), "penjaga dua sampel");
  assert.ok(!/inMbps:\s*\d/.test(page), "nilai Mbps hardcode");
});

check("param URL numerik di-resolve lewat endpoint ID, operasi tetap pakai serial dari respons", () => {
  assert.ok(page.includes("/api/onus/by-id/"), "resolver ID");
  assert.ok(page.includes("onu.data?.serial_number ?? \"\""), "serial dari respons");
  assert.ok(page.includes("detailPath(routeKey)"), "detail harus lewat detailPath()");
  // Tidak boleh ada permintaan yang menempelkan param URL langsung ke path per-serial.
  assert.ok(!/\/api\/onus\/\$\{routeKey\}/.test(page), "param URL dipakai sebagai serial");
});

check("VLAN terpasang = daftar; VLAN management disembunyikan tanpa nomor hardcode", () => {
  assert.ok(page.includes("function serviceVlans"), "helper daftar VLAN");
  assert.ok(page.includes("vlanList.map"), "daftar dirender");
  assert.ok(page.includes("service_vlans"), "pakai field kontrak service_vlans");
  assert.ok(page.includes("v.is_management === true"), "penanda management dari data");
  // Tidak boleh ada nomor VLAN yang jadi aturan penyaringan (mis. 100).
  assert.ok(!/vlan_id\s*[!=]==?\s*\d/.test(page), "nomor VLAN di-hardcode sebagai aturan");
  assert.ok(!/=== 100|!== 100/.test(page), "VLAN 100 di-hardcode");
  // Tampilan tidak boleh bergantung pada satu vlan_number saja di luar fallback.
  assert.equal((page.match(/d\.vlan_number/g) ?? []).length, 1, "masih bergantung vlan_number");
  assert.ok(page.includes("in_master === false"), "VLAN luar master ditandai, bukan disembunyikan");
});

check("metadata description dipakai hanya saat master kosong + ditandai asalnya", () => {
  assert.ok(page.includes("device_metadata"), "kontrak metadata perangkat");
  assert.ok(page.includes("dari description perangkat"), "penanda asal");
  for (const f of ["meta?.zone", "meta?.address", "meta?.splitter", "meta?.authorized_on"]) {
    assert.ok(page.includes(f), f);
  }
  // Master kosong tidak boleh menang atas nilai description yang nyata.
  const fn = page.slice(page.indexOf("function fromMasterOrDescription"));
  assert.ok(fn.slice(0, 400).includes('master === ""'), "string kosong master tidak dianggap kosong");
});

check("status header: admin_state disabled menang atas status perangkat", () => {
  assert.ok(page.includes('d.admin_state === "disabled" ? "disabled" : d.status'));
});

check("StatusBadge dipakai apa adanya (ikon default + withLabel), bukan ikon lokal", () => {
  assert.ok(page.includes("<StatusBadge status={statusKey}"), "StatusBadge dipakai");
  assert.ok(page.includes("withLabel"), "withLabel");
  assert.ok(!page.includes("const ONU_STATUS"), "peta status disalin ke halaman");
});

check("bucket sinyal tidak dihitung ulang: pakai rxBucket/RX_BUCKETS bersama", () => {
  assert.ok(page.includes("rxBucket(") && page.includes("RX_BUCKETS["));
  assert.ok(!/-2[578]\s*\)?\s*\?/.test(page.replace(/\[-25, -27\]/g, "")), "ambang bucket ditulis ulang");
});

check("penanda TR-069 status tidak dirender (prasyarat ACS internal belum ada)", () => {
  const bar = page.slice(page.indexOf("Diagnostik ONU:"), page.indexOf('label="Trafik / Sinyal"'));
  assert.ok(!bar.includes("TR-069 status"));
  assert.ok(!page.includes("tr069_profile"));
});

check("password PPPoE tidak pernah dirender", () => {
  assert.ok(!page.includes("pppoe_password"));
  assert.ok(page.includes("Tidak ditampilkan"));
});

check("aksi merusak tetap minta ketik serial + manager-only", () => {
  assert.ok(page.includes("typed === d.serial_number"));
  for (const action of ['setConfirm("restore-factory")', 'setConfirm("delete")']) {
    const i = page.indexOf(action);
    assert.notEqual(i, -1, action);
    assert.ok(page.slice(i - 220, i).includes("isManager"), action);
  }
});

check("jumlah port/SSID/VoIP/CATV dari katalog ONU Types, bukan hardcode", () => {
  assert.ok(page.includes("/api/onu-types"));
  for (const f of ["specs.eth_ports", "specs.wifi_ssids", "specs.voip_ports", "specs?.catv"]) {
    assert.ok(page.includes(f), f);
  }
});

check("tidak ada branding/contoh data dari desain yang disalin", () => {
  const forbidden = ["smartolt", "ibu tukini", "cemong", "fhttc", "mmr_olt", "kismantoro"];
  const lower = page.toLowerCase();
  for (const w of forbidden) assert.ok(!lower.includes(w), w);
});

check("satu markup untuk dua ukuran: tabel bisa digulir, kolom menumpuk, toolbar membungkus", () => {
  assert.ok(page.includes("overflow-x-auto"), "tabel digulir di layar kecil");
  assert.ok(page.includes("lg:grid-cols-2"), "kartu atas dua kolom di lg");
  assert.ok(page.includes("flex-wrap"), "toolbar membungkus");
  assert.ok(!/max-w-\[\d+px\]/.test(page), "lebar viewport di-hardcode");
});

// ------------------------------------------- tata letak desain acuan (design/onu-detail-stitch)

check("grid label/nilai: label rata kanan bold di sm+, menumpuk satu kolom di bawah sm", () => {
  const fn = page.slice(page.indexOf("function DRow"), page.indexOf("function CardHead"));
  assert.ok(fn.includes("sm:text-right"), "label rata kanan");
  assert.ok(fn.includes("font-semibold"), "label bold");
  assert.ok(fn.includes("sm:grid-cols-12"), "grid 12 kolom di sm+");
  assert.ok(fn.includes("grid w-full"), "satu kolom (menumpuk) di bawah sm");
});

check("field yang dibuang pemilik tidak pernah dirender", () => {
  for (const f of ["d.tx_power_dbm", "d.temperature_c", "d.voltage_v", "d.mac_address"]) {
    assert.ok(!page.includes(f), `masih dirender: ${f}`);
  }
  // Label baris yang dibuang tidak boleh muncul sebagai `label="..."` DRow/Section.
  for (const l of ["Shelf", "Board", "Slot", "Kanal", "GPON channel", "Suhu", "Tegangan", "MAC"]) {
    assert.ok(!page.includes(`label="${l}`), `baris masih ada: ${l}`);
  }
  // Slot/port hanya boleh dipakai untuk menyusun nama antarmuka, bukan sebagai baris sendiri.
  assert.equal((page.match(/d\.slot/g) ?? []).length, 1, "slot dipakai di luar nama antarmuka");
  // IP hanya dipakai di baris mode WAN: penjaga, href, dan teks tautan. Tidak ada baris IP sendiri.
  assert.ok(page.includes("http://${d.ip_address}"), "IP harus jadi tautan mode WAN");
  assert.equal((page.match(/d\.ip_address/g) ?? []).length, 3, "IP dipakai di luar tautan WAN");
});

check("mode setup WAN: nama mode + IP sebagai tautan tab baru; PPPoE hanya saat mode pppoe", () => {
  assert.ok(page.includes("{dash(d.wan_mode)}"), "nama mode dari data nyata");
  assert.ok(page.includes('target="_blank" rel="noopener noreferrer"'), "tautan IP aman");
  const i = page.lastIndexOf('label="Nama pengguna PPPoE"');
  assert.notEqual(i, -1);
  assert.ok(page.slice(i - 300, i).includes('d.wan_mode === "pppoe"'), "baris PPPoE tanpa penjaga mode");
});

check("Rx tanpa bacaan = LOS, bukan angka karangan", () => {
  const fn = page.slice(page.indexOf("function RxBox"), page.indexOf("function RxChart"));
  assert.ok(fn.includes('value === null ? "LOS"'), "null ditampilkan LOS");
  // Tidak ada nilai cadangan yang mengganti bacaan kosong dengan angka.
  assert.ok(!/\?\?\s*-?\d/.test(fn), "nilai Rx punya fallback angka");
  assert.ok(!page.includes("rx_power_dbm ?? "), "rx_power_dbm punya fallback");
});

check("ilustrasi panel belakang dari katalog ONU Types, tidak digambar saat tipe tak dikenal", () => {
  assert.ok(page.includes("<OnuRearPanel"), "komponen panel dipakai");
  const i = page.indexOf("<OnuRearPanel");
  assert.ok(page.slice(i - 200, i).includes("specs &&"), "panel tanpa penjaga katalog");
  assert.ok(page.includes("ethPorts={specs.eth_ports}"), "jumlah LAN dari katalog");
  assert.ok(page.includes("voipPorts={specs.voip_ports}"), "jumlah telepon dari katalog");
});

check("blok Layanan + Aksi mengikuti pola label/nilai, tombol berbahaya tetap manager-only", () => {
  for (const m of ['label="Layanan"', 'label="Aksi"', 'label="Layanan VoIP"', 'label="IPTV"', 'label="CATV"']) {
    assert.ok(page.includes(m), m);
  }
});

console.log(`\n${passed} pemeriksaan lulus`);
