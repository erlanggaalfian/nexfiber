/** Regresi modal "Update ONU mode" — pilihan WAN VLAN:
 *
 *      node frontend/tests/onu-mode.check.mjs
 *
 *  Node mengurai `../src/lib/wanVlan.ts` langsung (type stripping bawaan), jadi yang diuji
 *  adalah fungsi yang dipakai modal — bukan salinan. Nomor VLAN di bawah SINTETIS
 *  (bukan data pelanggan), bentuknya meniru OLT ZTE: 15 layanan, 100 management.
 */
import assert from "node:assert/strict";
import { wanVlanChoices } from "../src/lib/wanVlan.ts";

let passed = 0;
const check = (name, fn) => {
  fn();
  passed += 1;
  console.log(`ok  ${name}`);
};

const master = [
  { number: 15, name: "Layanan", is_management: false },
  { number: 100, name: "Management", is_management: true },
  { number: 200, name: "Tidak terpasang", is_management: false },
];

check("hanya VLAN terpasang yang jadi pilihan, bukan seluruh master", () => {
  assert.deepEqual(wanVlanChoices(master, [15], 15), [{ number: 15, name: "Layanan" }]);
});

check("VLAN management dibuang walau terpasang", () => {
  assert.deepEqual(wanVlanChoices(master, [15, 100], 15), [{ number: 15, name: "Layanan" }]);
});

check("VLAN WAN yang sedang berlaku tetap muncul walau bukan attached", () => {
  assert.deepEqual(wanVlanChoices(master, [15], 200), [
    { number: 15, name: "Layanan" },
    { number: 200, name: "Tidak terpasang" },
  ]);
});

check("VLAN perangkat yang belum ada di master tampil dengan nomor saja", () => {
  assert.deepEqual(wanVlanChoices(master, [3045], 3045), [{ number: 3045, name: null }]);
});

check("tanpa master dan tanpa attached: kosong, bukan daftar karangan", () => {
  assert.deepEqual(wanVlanChoices(undefined, [], null), []);
  assert.deepEqual(wanVlanChoices(master, [], null), []);
});

check("tidak ada duplikat saat VLAN WAN juga attached", () => {
  assert.deepEqual(wanVlanChoices(master, [15, 15], 15), [{ number: 15, name: "Layanan" }]);
});

console.log(`\n${passed} pemeriksaan lulus`);
