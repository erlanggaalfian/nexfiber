/** Trafik LIVE per ONU: sampel counter mentah dari backend -> Mbps.
 *
 *  Backend (`GET /api/onus/{serial}/traffic`) mengirim satu snapshot counter apa adanya:
 *  `in_octets`/`out_octets` sebagai string desimal (bisa > 2^53, jadi JANGAN di-Number),
 *  `counter_bits` 32 atau 64, dan `sampled_at` ISO. Arah (`in`/`out` relatif ke apa)
 *  didokumentasikan backend — halaman hanya meneruskan labelnya, tidak menebak.
 *
 *  Perhitungan delta dipisah ke modul ini supaya bisa diuji tanpa DOM
 *  (`frontend/tests/traffic.check.mjs`) dan tidak ada salinan kedua di komponen.
 */

export type TrafficSample = {
  sampled_at: string;
  in_octets: string;
  out_octets: string;
  counter_bits: 32 | 64;
  /** Lebar per arah, bila backend mengirimkannya di masa depan (skema saat ini hanya
   *  punya satu counter_bits). Bila ada, dipakai per arah; bila tidak, fallback ke
   *  counter_bits bersama seperti sebelumnya. */
  in_counter_bits?: 32 | 64;
  out_counter_bits?: 32 | 64;
};

export type TrafficPoint = { t: number; inMbps: number; outMbps: number };

const MODULUS: Record<number, bigint> = { 32: 2n ** 32n, 64: 2n ** 64n };

/** Ambang delta live yang masih masuk akal: interval live 5 detik, jadi delta di atas
 *  60 detik (mis. tab lama tersembunyi lalu kembali) tidak boleh dihitung sebagai laju
 *  — baseline-nya sudah basi. Batas ini juga melindungi dari wrap Counter32 berulang
 *  yang ter-alias menjadi Mbps arbitrer. */
export const MAX_LIVE_DELTA_S = 60;

/** Delta satu counter dalam bit. `null` = tidak bisa dipercaya (counter di-reset / lompat). */
function deltaBits(from: string, to: string, modulus: bigint): bigint | null {
  let d = BigInt(to) - BigInt(from);
  if (d < 0n) d += modulus; // wrap biasa di counter unsigned
  // Lompatan > setengah ruang counter = reset/restart agen SNMP, bukan trafik nyata.
  if (d > modulus / 2n) return null;
  return d * 8n;
}

/** Dua sampel berurutan -> satu titik Mbps. `null` kalau sampel tidak bisa dibandingkan
 *  (waktu tidak maju, lebar counter berubah, delta melebihi ambang, atau counter
 *  di-reset). Tidak pernah menebak. */
export function deltaMbps(prev: TrafficSample, next: TrafficSample): TrafficPoint | null {
  const inBitsWidth = prev.in_counter_bits ?? prev.counter_bits;
  const outBitsWidth = prev.out_counter_bits ?? prev.counter_bits;
  const inBitsWidthNext = next.in_counter_bits ?? next.counter_bits;
  const outBitsWidthNext = next.out_counter_bits ?? next.counter_bits;
  if (inBitsWidth !== inBitsWidthNext || outBitsWidth !== outBitsWidthNext) return null;
  const inModulus = MODULUS[inBitsWidth];
  const outModulus = MODULUS[outBitsWidth];
  if (inModulus === undefined || outModulus === undefined) return null;
  const t0 = Date.parse(prev.sampled_at);
  const t1 = Date.parse(next.sampled_at);
  if (!Number.isFinite(t0) || !Number.isFinite(t1)) return null;
  const seconds = (t1 - t0) / 1000;
  if (seconds <= 0 || seconds > MAX_LIVE_DELTA_S) return null;
  const inBits = deltaBits(prev.in_octets, next.in_octets, inModulus);
  const outBits = deltaBits(prev.out_octets, next.out_octets, outModulus);
  if (inBits === null || outBits === null) return null;
  const mbps = (bits: bigint) => Number(bits) / seconds / 1e6;
  return { t: t1, inMbps: mbps(inBits), outMbps: mbps(outBits) };
}
