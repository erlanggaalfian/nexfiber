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

check("urutan blok mengikuti desain: 3 blok atas, baris Diagnostik, trafik, profil, port, wifi, aksi", () => {
  const order = [
    // Bagian atas kini TIGA blok berjudul (Identitas | Jaringan & layanan | Status perangkat).
    'title="Identitas"',
    'label="OLT"',
    'title="Jaringan & layanan"',
    'title="Status perangkat"',
    // Baris tombol diagnostik memakai <Section label="Diagnostik"> (nama lama "Status"
    // dipakai blok Status perangkat, jadi tidak boleh tabrakan).
    '<Section label="Diagnostik">',
    'label="Trafik/Sinyal"',
    'label="Profil Kecepatan"',
    'label="Port Ethernet"',
    'label="WiFi"',
    "Restore default",
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

check("penanda TR-069 tidak jadi tombol aktif (prasyarat ACS internal belum ada)", () => {
  const i = page.indexOf("TR-069\n              </Button>");
  assert.notEqual(i, -1, "tombol TR-069 hilang");
  const btn = page.slice(i - 260, i);
  assert.ok(btn.includes("disabled"), "tombol TR-069 tanpa disabled");
  assert.ok(!btn.includes("onClick"), "tombol TR-069 punya onClick");
  assert.ok(!page.includes("tr069_profile"));
});

check("password PPPoE tampil (dari backend, manager saja) dan TR069 bertanda segera rilis", () => {
  assert.ok(page.includes("d.pppoe_password"));
  assert.ok(page.includes("Segera rilis"));
});

check("aksi merusak tetap minta ketik serial + manager-only", () => {
  // Konfirmasi ketik-serial sekarang hidup di komponen modal bersama.
  const confirmModal = readFileSync(
    join(here, "..", "src", "components", "onu", "modals", "ConfirmActionModal.tsx"), "utf8",
  );
  assert.ok(confirmModal.includes("typed === serial"), "konfirmasi ketik serial hilang");
  for (const kind of ["delete", "restore-factory"]) {
    assert.ok(confirmModal.includes(`"${kind}"`), kind);
  }
  assert.ok(/NEEDS_TYPED[^=]*=\s*\[\s*"delete",\s*"restore-factory"\s*\]/.test(confirmModal),
            "daftar aksi wajib ketik serial berubah");
  for (const action of ['setModal({ kind: "restore-factory" })', 'setModal({ kind: "delete" })']) {
    const i = page.indexOf(action);
    assert.notEqual(i, -1, action);
    assert.ok(page.slice(i - 260, i).includes("isManager"), action);
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

check("grid label/nilai: label rata kanan bold di lg+, menumpuk satu kolom di bawah lg", () => {
  const fn = page.slice(page.indexOf("function DRow"), page.indexOf("const THEAD"));
  // Ambang pindah dari `sm` ke `lg`: acuan menumpuk label di atas nilai sampai 1000px
  // (`@media (min-width:1000px)` pada `.dl-horizontal`), dan `lg` (1024px) adalah
  // breakpoint terdekat yang sudah ada di repo.
  assert.ok(fn.includes("lg:text-right"), "label rata kanan");
  assert.ok(fn.includes("font-semibold"), "label bold");
  // Grid 12-kolom diganti kolom label berlebar tetap seperti `dl-horizontal` acuan
  // (label 160px @15px -> 140px pada basis 13px Nexfiber).
  assert.ok(fn.includes("lg:grid-cols-[140px_1fr]"), "kolom label lebar tetap di lg+");
  assert.ok(fn.includes("grid w-full"), "satu kolom (menumpuk) di bawah lg");
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
  // Pemetaan `modalOnu` (data untuk modal aksi) bukan tampilan, jadi dikeluarkan dari hitungan.
  const render = page.slice(0, page.indexOf("const modalOnu")) +
    page.slice(page.indexOf("attached_vlans:", page.indexOf("const modalOnu")));
  assert.equal((render.match(/d\.slot/g) ?? []).length, 1, "slot dipakai di luar nama antarmuka");
  // IP hanya muncul sebagai TAUTAN (komponen IpLink) di baris Mgmt IP / WAN setup mode:
  // dua penjaga + dua props, tidak ada baris "IP" sendiri.
  assert.ok(page.includes("href={`http://${ip}`}"), "IP harus jadi tautan lewat IpLink");
  // 6 kemunculan ipLive: definisi (sumber tunggal, fallback d.ip_address) + 3 penjaga
  // (Mgmt IP pemisah/tautan + WAN) + 2 prop IpLink. Tanpa baris "IP" sendiri.
  assert.equal((render.match(/ipLive/g) ?? []).length, 6, "ipLive dipakai di luar tautan");
  assert.equal((render.match(/d\.ip_address/g) ?? []).length, 1, "sumber IP harus lewat ipLive");
  assert.ok(!/<DRow label="(IP|IP address|Alamat IP)"/.test(page), "ada baris IP sendiri");
});

check("mode setup WAN: 4 mode acuan dipetakan, nilai tak dikenal apa adanya", () => {
  // Label persis daftar aplikasi referensi; huruf kapital ada di TEKS, bukan CSS uppercase.
  const map = page.slice(page.indexOf("const WAN_MODE_LABEL"), page.indexOf("/** Mode yang menampilkan"));
  for (const [k, v] of [
    ["webpage", "Setup via ONU webpage"], ["dhcp", "DHCP"], ["static", "Static IP"], ["pppoe", "PPPoE"],
  ]) {
    assert.ok(map.includes(`${k}: "${v}"`), `${k} -> ${v}`);
  }
  // Nilai di luar peta tidak boleh error / dipaksa: ditampilkan apa adanya.
  assert.ok(page.includes("WAN_MODE_LABEL[mode.toLowerCase()] ?? mode"), "fallback apa adanya");
  assert.ok(!/className="[^"]*\buppercase\b[^"]*">\{(dash\()?d\.wan_mode/.test(page),
            "mode WAN masih di-uppercase lewat CSS");
  // IP WAN hanya untuk mode yang punya IP; `webpage` sengaja tanpa IP.
  assert.ok(page.includes('!== "webpage"'), "webpage masih menampilkan IP WAN");
  assert.ok(page.includes('target="_blank" rel="noopener noreferrer"'), "tautan IP aman");
});

check("baris PPPoE hanya untuk mode pppoe; kredensial dari backend (manager)", () => {
  // Username + kata sandi kini SATU baris dengan satu tombol mata.
  const i = page.lastIndexOf('label="Username PPPoE"');
  assert.notEqual(i, -1, "baris PPPoE hilang");
  assert.ok(page.slice(i - 600, i).includes("{isPppoe && ("), "baris PPPoE tanpa penjaga mode");
  assert.ok(page.includes(">Password PPPoE<"), "label Password PPPoE hilang dari baris gabungan");
  assert.ok(page.includes('const isPppoe = (d.wan_mode ?? "").toLowerCase() === "pppoe"'),
            "penjaga mode pppoe");
  assert.ok(page.includes("d.pppoe_password"), "kata sandi PPPoE tidak dirender");
  assert.ok(page.includes("Hanya untuk manager"), "keterangan kata sandi tanpa nilai hilang");
});

check("baris spesifikasi koneksi memakai label hasil rename (tabel pemilik)", () => {
  for (const l of [
    "Profil TR069", "Mgmt IP", "VLAN terpasang", "Mode ONU", "Setup WAN", "Username PPPoE",
  ]) {
    assert.ok(page.includes(`label="${l}"`), `baris hilang: ${l}`);
  }
  // Label Inggris lama tidak boleh tertinggal (termasuk dua baris PPPoE yang kini gabung).
  for (const l of ["TR069 Profile", "Attached VLANs", "ONU mode", "WAN setup mode",
                   "PPPoE username", "PPPoE password", "Mode setup WAN", "Akses remote WAN"]) {
    assert.ok(!page.includes(`label="${l}"`), `label lama masih ada: ${l}`);
  }
  // Tanpa data: TR069 `Inactive`, Mgmt IP belum terbaca, dan mode "—" redup; bukan fakta karangan.
  assert.ok(page.includes('label="Profil TR069" value={<>Inactive'), "Profil TR069 Inactive");
  assert.ok(page.includes('mgmtMode === null ? <span className="text-faint">— (belum terbaca)</span>'),
            "Mgmt IP belum terbaca");
  assert.ok(page.includes("wanMode === null ? DASH"), "Setup WAN kosong = — redup");
});

check("mode ONU/WAN dipakai apa adanya dari backend (default dihitung di sana)", () => {
  // Halaman TIDAK boleh menambal default sendiri: tidak ada literal "routing"/"webpage"
  // sebagai nilai cadangan (`??`/`||`) di sini. Default ada di backend
  // (app/schemas/onu.py: DEFAULT_ONU_MODE/DEFAULT_WAN_MODE) supaya satu sumber saja.
  assert.ok(!/\?\?\s*"(routing|webpage)"/.test(page), "halaman menambal default mode sendiri");
  // Label mode ONU lewat peta, nilai tak dikenal tampil apa adanya (bukan error).
  assert.ok(page.includes('const ONU_MODE_LABEL: Record<string, string> = { routing: "Routing", bridging: "Bridging" }'),
            "peta label ONU mode hilang");
  assert.ok(page.includes("ONU_MODE_LABEL[mode.toLowerCase()] ?? mode"), "fallback ONU mode apa adanya");
  assert.ok(page.includes("const onuMode = onuLabel(d.onu_mode)"), "ONU mode tidak lewat onuLabel");
  assert.ok(page.includes('onuMode === null'), "ONU mode kosong harus tetap punya cabang —");
});

check("blok Identitas memakai label hasil rename + `None` untuk nilai kosong", () => {
  const rows = [...page.matchAll(/<DRow label="([^"]+)"/g)].map((m) => m[1]);
  const left = rows.slice(0, rows.indexOf("Lokasi") + 1);
  assert.deepEqual(left, [
    "OLT", "ONU", "SN", "Tipe ONU", "Preset konfigurasi", "Nama pelanggan", "Alamat",
    "Kontak", "Zona", "Splitter", "Sektor", "ID eksternal", "Tanggal otorisasi", "Lokasi",
  ], left.join(","));
  // Board / Port / GPON channel sengaja dibuang pemilik: tidak boleh muncul lagi.
  for (const l of ["Board", "Port", "GPON channel"]) {
    assert.ok(!rows.includes(l), `baris yang dibuang muncul lagi: ${l}`);
  }
  assert.ok(page.includes('const NONE = <span className="italic text-faint">None</span>'),
            "`None` miring seperti acuan");
  assert.ok(page.includes("function fromMasterOrDescription"), "sumber nilai tetap data nyata");
});

check("panel LIVE hanya dirender saat LIVE aktif, Pps/Avg size '—' tanpa counter paket", () => {
  const i = page.indexOf('<CardHead title="LIVE traffic"');
  assert.notEqual(i, -1, "panel LIVE hilang");
  assert.ok(page.slice(i - 400, i).includes("{live && ("), "panel LIVE tanpa penjaga `live`");
  assert.ok(i < page.indexOf('label="Trafik/Sinyal"'), "panel harus sebelum kartu trafik");
  // Upload = out_octets (keluar dari ONU), download = in_octets — kontrak backend.
  assert.ok(page.includes('label="U Speed"') && page.includes("latest?.outMbps"), "U Speed = out");
  assert.ok(page.includes('label="D Speed"') && page.includes("latest?.inMbps"), "D Speed = in");
  // Max = puncak sejak LIVE dinyalakan, dihitung dari titik nyata.
  assert.ok(page.includes("Math.max(...traffic.points.map((p) => p.outMbps))"), "Max upload");
  // Pps / Avg size tidak punya sumber data: harus "—" literal, bukan rumus karangan.
  assert.ok(page.includes('cell("Pps", "—")'), "Pps harus —");
  assert.ok(page.includes('cell("Avg size", "—")'), "Avg size harus —");
});

check("kartu Traffic history menggambar sampel tersimpan, bukan angka karangan", () => {
  const i = page.indexOf("<ChartCard title={`Trafik ${RANGE_TITLE[range]}`}");
  assert.notEqual(i, -1, "kartu histori trafik hilang");
  const card = page.slice(i, i + 2200);
  assert.ok(card.includes("<TrafficHistoryChart points={trafficHistory.data ?? []}"),
            "grafik tidak dipasang ke data endpoint histori");
  // Pesan lama ("backend belum menyimpan") tidak boleh kembali: backend sudah menyimpan.
  assert.ok(!page.includes("backend belum menyimpan sampel counter"), "klaim lama kembali");
  // Data diambil dari endpoint histori, bukan dihitung ulang di halaman.
  assert.ok(page.includes("/traffic/history?range=${range}"), "endpoint histori tidak dipanggil");
  const chart = page.slice(page.indexOf("function TrafficHistoryChart"),
                           page.indexOf("function trafficStats"));
  // Sampel tanpa laju memutus garis; tidak pernah diganti 0.
  assert.ok(chart.includes("if (v === null)") && chart.includes("current = []"),
            "titik null tidak memutus garis");
  assert.ok(chart.includes("Belum ada sampel trafik") && chart.includes("Tunggu poll berikutnya"),
            "pesan kosong harus menyebut sebab dan satu aksi");
  assert.ok(!/in_bps\s*\?\?\s*0\s*\)\s*\/\s*1e6/.test(chart), "laju null diganti nol");
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
  for (const m of ['label="Layanan Tambahan"', 'label="Aksi ONU"', 'label="Layanan VoIP"', 'label="IPTV"', 'label="CATV"']) {
    assert.ok(page.includes(m), m);
  }
});

check("6 aksi yang dibuang pemilik tidak ada lagi (tombol, handler, maupun state modal)", () => {
  for (const label of ["Ubah data pelanggan", "Ubah lokasi", "Ubah speed", "Ubah VLAN",
                       "Move ONU", "Replace ONU / ganti SN"]) {
    assert.ok(!page.includes(`>${label}<`), `tombol masih ada: ${label}`);
  }
  // Handler + form "Ubah data pelanggan" ikut dibuang: tidak ada PATCH /info dari halaman ini.
  for (const sym of ["infoDialog", "infoPayload", "infoFrom", "InfoForm", "saveInfo",
                     "/info`", "setEditing"]) {
    assert.ok(!page.includes(sym), `sisa handler: ${sym}`);
  }
  // Move ONU jadi modal yatim -> dibuang; modal lain yang masih dipakai tetap ada.
  const modals = readFileSync(
    join(here, "..", "src", "components", "onu", "modals", "OnuActionModals.tsx"), "utf8",
  );
  assert.ok(!modals.includes("MoveOnuModal"), "modal Move ONU masih dirender");
  assert.ok(!/kind: "move"/.test(modals), 'state modal.kind "move" masih ada');
  const basic = readFileSync(
    join(here, "..", "src", "components", "onu", "modals", "BasicModals.tsx"), "utf8",
  );
  assert.ok(!basic.includes("MoveOnuModal"), "komponen MoveOnuModal masih ada");
  // Modal yang titik bukanya cuma dipindah (bukan dibuang) HARUS tetap hidup.
  for (const keep of ["SpeedProfileModal", "ReplaceSnModal", "LocationModal",
                      "AttachedVlansModal"]) {
    assert.ok(modals.includes(keep), `modal yang masih dipakai ikut terhapus: ${keep}`);
  }
});

check("Log aksi terakhir = POP UP dari tombol kepala blok Aksi ONU, entri menaut ke /logs?q=<serial>", () => {
  // Pemicunya di DALAM <Section label="Aksi ONU"> (tombol di kanan judul, acuan mock).
  const sec = page.indexOf('<Section label="Aksi ONU"');
  const trigger = page.indexOf("<LastLogPopover", sec);
  assert.notEqual(trigger, -1, "pemicu pop up log tidak ada di blok Aksi");
  assert.ok(trigger < page.indexOf("</Section>", sec), "pemicu di luar blok Aksi");
  // Pop up nyata (Popover radix), bukan tabel yang selalu terbuka di halaman.
  assert.ok(page.includes("<Popover.Root>") && page.includes("<Popover.Content"),
            "tidak memakai Popover");
  assert.ok(!page.includes('<Panel title="Log aksi terakhir"'), "tabel log lama masih dirender");
  // Entri = deskripsi aksi + tautan ke halaman Logs tersaring serial ONU ini.
  assert.ok(page.includes("`/logs?q=${encodeURIComponent(serial)}`"), "tautan /logs?q=<serial>");
  assert.ok(page.includes('"onu.update_info": "Update location details"'),
            "deskripsi aksi diturunkan dari action backend");
  // Isinya dari endpoint log ONU yang sudah ada, bukan endpoint baru.
  assert.ok(page.includes("/logs?limit="), "sumber log bukan endpoint ONU yang ada");
});

// --------------------------------------- centang awal "Update attached VLANs"

check("centang awal modal VLAN = VLAN terpasang dari backend, bukan daftar tampilan", () => {
  // Bug nyata: modal selalu terbuka tanpa centang karena backend tidak pernah mengirim
  // daftar VLAN terpasang. Sumbernya sekarang field `service_vlans` (kontrak backend).
  assert.ok(page.includes("attached_vlans: attachedVlanNumbers(d)"),
            "centang modal tidak diambil dari attachedVlanNumbers");
  const fn = page.slice(page.indexOf("function attachedVlanNumbers"),
                        page.indexOf("/** View diagnostik"));
  assert.ok(fn.includes("d.service_vlans"), "sumber centang bukan field service_vlans");
  // Tanpa data nyata jangan mengarang centang.
  assert.ok(fn.includes('if (!Array.isArray(d.service_vlans)) return [];'),
            "daftar belum dikirim backend harus jadi [] bukan tebakan");
  // KESELAMATAN TRAFIK: perintah backend menulis ULANG seluruh service-port dari nilai
  // yang dikirim, jadi VLAN management TIDAK boleh disaring dari centang awal — kalau
  // disaring, menambah satu VLAN ikut menghapus service-port management ONU.
  assert.ok(!fn.includes("isManagementVlan"),
            "VLAN management disaring dari centang: submit akan menghapus layanan itu");
});

check("daftar VLAN terpasang dipakai juga sebagai VLAN WAN 'Update ONU mode'", () => {
  // Satu sumber untuk dua modal: jangan ada daftar VLAN terpasang versi kedua.
  assert.ok(page.includes("const vlanList = serviceVlans(d)"),
            "daftar VLAN tampilan tidak lagi dari serviceVlans");
  const decl = (page.match(/d\.service_vlans/g) ?? []).length;
  assert.ok(decl >= 2, `service_vlans harus jadi sumber bersama, ditemukan ${decl}`);
});

check("kartu Signal & Status history tidak menyerah pada satu sampel", () => {
  const chart = page.slice(page.indexOf("function RxChart"), page.indexOf("function StatusStrip"));
  // BUG NYATA (2026-10-26): ambang `values.length < 2` membuat kartu menulis "Belum cukup
  // data histori sinyal" padahal ada 1 bacaan Rx — sampler optik hanya jalan tiap 15 menit,
  // jadi sesaat setelah worker restart titiknya memang baru satu.
  assert.ok(!chart.includes("values.length < 2"),
            "ambang 2 titik kembali: satu bacaan Rx akan dianggap 'belum cukup data'");
  assert.ok(chart.includes("all.length === 0"),
            "pesan kosong harus hanya untuk 0 bacaan Rx (dihitung dari semua garis)");
  assert.ok(chart.includes("s.values.length === 1") && chart.includes("<circle"),
            "satu titik harus digambar sebagai lingkaran (polyline 1 titik tidak terlihat)");
  assert.ok(chart.includes("dataMin - 1.5") && chart.includes("dataMax + 1.5"),
            "domain Rx harus rapat ke data");
  assert.ok(chart.includes("-27.25") && chart.includes("-24.75"),
            "domain Rx harus tetap memuat ambang -25 dan -27");
  assert.ok(!chart.includes("Math.min(...all, -30)") && !chart.includes("Math.max(...all, -8)"),
            "domain Rx lebar lama kembali");
  assert.ok(page.includes("<ChartCard title={`Sinyal ${RANGE_TITLE[srange]}`}"),
            "judul kartu sinyal harus mengikuti rentang terpilih");
  assert.ok((page.match(/<StatusStrip points=\{points\} \/>/g) ?? []).length >= 2,
            "pita Status history tidak dirender di kedua cabang RxChart");
  const strip = page.slice(page.indexOf("function StatusStrip"));
  assert.ok(strip.includes('p.status === "online"'),
            "pita status tidak memakai kolom status dari onu_signal_history");
});

console.log(`\n${passed} pemeriksaan lulus`);
