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
};

export type TrafficPoint = { t: number; inMbps: number; outMbps: number };

const MODULUS: Record<number, bigint> = { 32: 2n ** 32n, 64: 2n ** 64n };

/** Delta satu counter dalam bit. `null` = tidak bisa dipercaya (counter di-reset / lompat). */
function deltaBits(from: string, to: string, modulus: bigint): bigint | null {
  let d = BigInt(to) - BigInt(from);
  if (d < 0n) d += modulus; // wrap biasa di counter unsigned
  // Lompatan > setengah ruang counter = reset/restart agen SNMP, bukan trafik nyata.
  if (d > modulus / 2n) return null;
  return d * 8n;
}

/** Dua sampel berurutan -> satu titik Mbps. `null` kalau sampel tidak bisa dibandingkan
 *  (waktu tidak maju, lebar counter berubah, atau counter di-reset). Tidak pernah menebak. */
export function deltaMbps(prev: TrafficSample, next: TrafficSample): TrafficPoint | null {
  if (prev.counter_bits !== next.counter_bits) return null;
  const modulus = MODULUS[next.counter_bits];
  if (modulus === undefined) return null;
  const t0 = Date.parse(prev.sampled_at);
  const t1 = Date.parse(next.sampled_at);
  if (!Number.isFinite(t0) || !Number.isFinite(t1)) return null;
  const seconds = (t1 - t0) / 1000;
  if (seconds <= 0) return null;
  const inBits = deltaBits(prev.in_octets, next.in_octets, modulus);
  const outBits = deltaBits(prev.out_octets, next.out_octets, modulus);
  if (inBits === null || outBits === null) return null;
  const mbps = (bits: bigint) => Number(bits) / seconds / 1e6;
  return { t: t1, inMbps: mbps(inBits), outMbps: mbps(outBits) };
}
