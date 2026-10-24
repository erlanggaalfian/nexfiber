/** Regresi pembersih nama speed profile:
 *
 *      node frontend/tests/profile-name.check.mjs
 *
 *  Node mengurai `../src/lib/profileName.ts` langsung (type stripping bawaan), jadi yang
 *  diuji adalah fungsi yang dipakai halaman — bukan salinan. Varian nama di bawah diambil
 *  dari OLT yang pernah dikelola SmartOLT; harus sama dengan backend
 *  (`backend/tests/test_profile_name.py`).
 */
import assert from "node:assert/strict";
import { cleanProfileName } from "../src/lib/profileName.ts";

let passed = 0;
const check = (name, fn) => {
  fn();
  passed += 1;
  console.log(`ok  ${name}`);
};

check("token SmartOLT dibuang, pemisah sisa dirapikan", () => {
  assert.equal(cleanProfileName("SMARTOLT-5Mbps"), "5Mbps");
  assert.equal(cleanProfileName("5Mbps_SmartOLT"), "5Mbps");
  assert.equal(cleanProfileName("SmartOLT 10M"), "10M");
  assert.equal(cleanProfileName("smartolt_20Mbps"), "20Mbps");
  assert.equal(cleanProfileName("SMARTOLT-HFA_Lite"), "HFA_Lite");
  assert.equal(cleanProfileName("SMARTOLT-VOIPMNG-10M"), "VOIPMNG-10M");
});

check("bagian lain nama tidak dirusak", () => {
  for (const name of ["KhanzaNet", "PAKET20", "SmartOLTX", "XSmartOLT", "Smart OLT 10M"]) {
    assert.equal(cleanProfileName(name), name);
  }
});

check("hasil kosong jatuh kembali ke nama asli, bukan string kosong", () => {
  assert.equal(cleanProfileName("SMARTOLT"), "SMARTOLT");
  assert.equal(cleanProfileName("-smartolt_"), "-smartolt_");
  assert.equal(cleanProfileName(null), null);
  assert.equal(cleanProfileName(undefined), null);
});

console.log(`\n${passed} pemeriksaan lulus`);
