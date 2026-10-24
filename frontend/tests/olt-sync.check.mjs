/** Regresi progres sinkron OLT. Tanpa framework:
 *
 *      node frontend/tests/olt-sync.check.mjs
 *
 *  Node mengurai `../src/lib/oltSyncStages.ts` langsung (type stripping bawaan Node >= 22.18),
 *  jadi `syncSummary`/`isSyncActive` yang diuji adalah fungsi yang dipakai komponen.
 *  Bagian UI diperiksa sebagai teks karena repo ini tidak punya renderer DOM.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { isSyncActive, syncSummary } from "../src/lib/oltSyncStages.ts";

const here = dirname(fileURLToPath(import.meta.url));
const src = (...p) => readFileSync(join(here, "..", "src", ...p), "utf8");
const hook = src("lib", "oltSync.ts");
const comp = src("components", "OltSyncProgress.tsx");

let passed = 0;
const check = (name, fn) => {
  fn();
  passed += 1;
  console.log(`ok  ${name}`);
};

const stage = (key, status, count = null, error = null) =>
  ({ key, label: key, status, started_at: null, finished_at: null, error, count, job_id: null });
const status = (state, stages) => ({ olt_id: 1, state, trigger: null, updated_at: null, stages });

// ------------------------------------------------------------------ ringkasan

check("ringkasan: tahap selesai dihitung, tahap berjalan dan jumlah ONU diambil", () => {
  const s = syncSummary(status("running", [
    stage("test_connection", "success"),
    stage("olt_metrics", "success"),
    stage("speed_profiles", "skipped"),
    stage("onu_status", "success", 246),
    stage("onu_unconfigured", "running"),
    stage("onu_metadata", "pending"),
  ]));
  assert.equal(s.total, 6);
  assert.equal(s.done, 4, "success + skipped dianggap sudah lewat");
  assert.equal(s.pct, 67);
  assert.equal(s.running.key, "onu_unconfigured");
  assert.equal(s.onu, 246);
  assert.equal(s.failed.length, 0);
});

check("ringkasan: tahap gagal terbaca beserta alasannya", () => {
  const s = syncSummary(status("failed", [
    stage("onu_status", "success", 12),
    stage("olt_metrics", "failed", null, "SNMP timeout"),
  ]));
  assert.equal(s.failed.length, 1);
  assert.equal(s.failed[0].error, "SNMP timeout");
  assert.equal(s.done, 2);
});

check("ringkasan: nol tahap tidak membagi nol", () => {
  const s = syncSummary(status("pending", []));
  assert.equal(s.pct, 0);
  assert.equal(s.onu, null);
});

check("jumlah ONU hanya dari tahap onu_status, bukan tahap onu_* lain", () => {
  const s = syncSummary(status("running", [
    stage("onu_unconfigured", "success", 9),
    stage("onu_metadata", "success", 4),
    stage("onu_status", "running", null),
  ]));
  assert.equal(s.onu, null, "hitungan tahap lain tidak boleh dipakai sebagai jumlah ONU");
});

check("state aktif hanya pending/running", () => {
  for (const state of ["pending", "running"]) {
    assert.equal(isSyncActive(status(state, [])), true, state);
  }
  for (const state of ["success", "failed"]) {
    assert.equal(isSyncActive(status(state, [])), false, state);
  }
});

// ------------------------------------------------------------------- perilaku

check("polling 3 s hanya selama sinkron berjalan, lalu berhenti", () => {
  assert.match(hook, /refetchInterval:\s*\(query\)\s*=>\s*\(query\.state\.data && isSyncActive\(query\.state\.data\) \? 3000 : false\)/);
});

check("selesai sinkron mengundang ulang daftar OLT, ONU, dan dashboard", () => {
  const keys = hook.match(/for \(const key of \[.*?\]\) \{/s)?.[0] ?? "";
  for (const k of ["olts", "onus", "onu", "pending", "dashboard"]) {
    assert.ok(keys.includes(`"${k}"`), `queryKey ${k} tidak diinvalidasi saat sinkron selesai`);
  }
});

check("endpoint 404/403 tidak diulang dan tidak jadi data palsu", () => {
  assert.match(hook, /e\.status === 404 \|\| e\.status === 403/);
  assert.match(comp, /Progres sinkron belum tersedia/);
  assert.ok(!/\bMath\.random\b/.test(comp) && !/\bMath\.random\b/.test(hook), "tidak ada angka acak");
});

check("gagal menampilkan alasan singkat + tombol Coba lagi memanggil sync-all", () => {
  assert.match(comp, /Coba lagi/);
  assert.match(comp, /failed\[0\]\.error/);
  assert.match(hook, /`\/api\/olts\/\$\{oltId\}\/sync-all`, \{ method: "POST" \}/);
  // Jawaban sync-all adalah OltSyncStatus; dipasang ke cache supaya polling lanjut.
  assert.match(hook, /onSuccess: \(s\) => qc\.setQueryData\(key\(oltId\), s\)/);
});

check("tombol Coba lagi hanya untuk manager (backend sync-all butuh admin)", () => {
  assert.match(comp, /s\.state === "failed" && isManager/);
});

check("tidak ada tombol untuk memulai: progres muncul sendiri tanpa klik", () => {
  const buttons = comp.match(/<Button[\s\S]*?<\/Button>/g) ?? [];
  assert.equal(buttons.length, 1, "hanya tombol Coba lagi yang boleh ada");
});

check("baris tabel hilang total saat tidak ada sinkron (tanpa garis pemisah percuma)", () => {
  assert.match(comp, /OltSyncProgressRow[\s\S]*?if \(q\.unavailable \|\| !q\.data\) return null;/);
  assert.match(comp, /if \(q\.data\.state === "success"\) return null;/);
});

check("dipasang di halaman OLT yang ada, bukan halaman baru", () => {
  assert.match(src("pages", "settings", "OltManagement.tsx"), /<OltSyncProgressRow oltId=\{o\.id\} colSpan=\{columns\.length\}/);
  assert.match(src("pages", "OltDetail.tsx"), /<OltSyncProgress oltId=\{oltId\} showIdle/);
});

check("satu markup untuk dua ukuran: pita membungkus, teks panjang terpotong", () => {
  assert.match(comp, /flex-wrap/);
  assert.match(comp, /truncate/);
  assert.match(comp, /shrink-0/);
});

check("tipe mengikuti kontrak backend OltSyncStage/OltSyncStatus apa adanya", () => {
  const schema = readFileSync(join(here, "..", "..", "backend", "app", "schemas", "olt.py"), "utf8");
  const types = src("lib", "oltSyncStages.ts");
  const fields = (cls) =>
    (schema.split(`class ${cls}(BaseModel):`)[1] ?? "").split("\nclass ")[0]
      .split("\n").map((l) => /^ {4}(\w+):/.exec(l.replace(/#.*/, ""))?.[1]).filter(Boolean);
  for (const cls of ["OltSyncStage", "OltSyncStatus"]) {
    const got = fields(cls);
    assert.ok(got.length > 0, `tidak bisa membaca field ${cls} dari schema backend`);
    for (const f of got) {
      assert.match(types, new RegExp(`^\\s{2}${f}:`, "m"), `${cls}.${f} belum ada di tipe frontend`);
    }
  }
});

check("tahap onu_status yang jadi sumber jumlah ONU benar-benar ada di rantai backend", () => {
  const chain = readFileSync(
    join(here, "..", "..", "backend", "app", "services", "olt_onboarding.py"), "utf8");
  assert.match(chain, /\("onu_status",/, "key onu_status hilang dari STAGES backend");
});

console.log(`\n${passed} pemeriksaan lulus`);
