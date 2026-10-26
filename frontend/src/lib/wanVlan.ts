/** Pilihan "WAN VLAN-ID" di modal Update ONU mode.
 *
 *  File terpisah dari `onuActions.ts` supaya bisa diuji langsung dengan Node
 *  (`frontend/tests/onu-mode.check.mjs`) tanpa menarik react-query.
 */

export type VlanOption = { number: number; name: string; is_management: boolean };

/** Sumbernya HANYA VLAN terpasang ONU (yang dicentang di "Update attached VLANs"), bukan
 *  seluruh master VLAN OLT: WAN ONU tidak bisa memakai VLAN yang tidak terpasang padanya.
 *
 *  - VLAN management dibuang (penanda `is_management` dari master, bukan nomor hardcode);
 *  - `current` (VLAN WAN yang sedang berlaku di perangkat) selalu ikut walau tidak ada di
 *    daftar terpasang, supaya nilai nyata tidak hilang dari dropdown;
 *  - `name` null = VLAN ada di perangkat tapi belum terdaftar di master: tampilkan nomornya
 *    apa adanya, jangan dibuang dan jangan dikarang namanya.
 */
export function wanVlanChoices(
  vlans: VlanOption[] | undefined, attached: number[], current: number | null,
): { number: number; name: string | null }[] {
  const master = new Map((vlans ?? []).map((v) => [v.number, v]));
  const picked = new Set(attached.filter((n) => master.get(n)?.is_management !== true));
  if (current !== null) picked.add(current);
  return [...picked].sort((a, b) => a - b)
    .map((n) => ({ number: n, name: master.get(n)?.name ?? null }));
}
