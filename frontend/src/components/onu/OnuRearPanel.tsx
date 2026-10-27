/** Panel Port Fisik ONU — versi padat gaya mock `onu-detail-mock.html` (baris port kecil:
 *  PON menyala, LAN1..N, Reset, Power) + chip "1 PON · N LAN" di judul.
 *
 *  Semua yang digambar diturunkan dari data NYATA:
 *  - jumlah port LAN dan telepon dari katalog ONU Types (`/api/onu-types`), bukan angka tetap
 *    (jumlah telepon hanya dibacakan di `aria-label`, jack telepon tidak digambar);
 *  - lampu PON hijau hanya saat status ONU benar-benar `online` (satu state nyata, tanpa
 *    animasi/pulse).
 *
 *  Panel tidak pernah dirender saat tipe ONU belum ada di katalog — lebih baik kosong daripada
 *  menggambar port yang belum tentu ada di perangkat.
 *  ponytail: jack Tel tidak digambar (tidak ada di daftar port mock); tambah bila pemilik minta. */
function Port({ label, children, bold }: { label: string; children: React.ReactNode; bold?: boolean }) {
  return (
    <div className="flex shrink-0 flex-col items-center gap-1">
      {children}
      <span className={`font-mono text-[9px] leading-none ${bold ? "font-bold text-fiber" : "font-medium text-muted"}`}>
        {label}
      </span>
    </div>
  );
}

export function OnuRearPanel(
  { ethPorts, voipPorts, online }: { ethPorts: number; voipPorts: number; online: boolean },
) {
  return (
    <div className="rounded-sm border bg-sunken px-3 py-2"
         role="img"
         aria-label={`Panel port fisik ONU: 1 port PON (${online ? "menyala" : "mati"}), ${voipPorts} port telepon, ${ethPorts} port LAN`}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-muted">Panel Port Fisik</span>
        <span className="rounded-sm border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-faint">
          1 PON · {ethPorts} LAN
        </span>
      </div>
      <div className="flex items-center justify-between gap-1 overflow-x-auto py-1">
        <Port label="PON" bold>
          <span className={`flex h-7 w-7 items-center justify-center rounded-sm border bg-surface ${online ? "border-up" : "border-line"}`}>
            <span aria-hidden className={`h-2 w-2 rounded-full ${online ? "bg-up" : "bg-idle"}`} />
          </span>
        </Port>
        {Array.from({ length: ethPorts }, (_, i) => (
          <Port key={`lan-${i}`} label={`LAN${ethPorts > 1 ? i + 1 : ""}`}>
            <span className="flex h-7 w-7 items-end justify-center rounded-sm border border-line bg-surface pb-1">
              <span aria-hidden className="h-2 w-2.5 rounded-sm border border-line bg-sunken" />
            </span>
          </Port>
        ))}
        <span aria-hidden className="h-6 w-px bg-line" />
        <div className="flex shrink-0 flex-col items-center gap-1">
          <span className="flex h-7 w-3 items-center justify-center">
            <span aria-hidden className="block h-5 w-2 rounded-full border border-line bg-sunken" />
          </span>
          <span className="font-mono text-[9px] font-medium leading-none text-faint">Reset</span>
        </div>
        <div className="flex shrink-0 flex-col items-center gap-1">
          <span className="flex h-7 w-4 items-center justify-center">
            <span aria-hidden className="block h-5 w-3 rounded-sm border border-line bg-surface" />
          </span>
          <span className="font-mono text-[9px] font-medium leading-none text-faint">Power</span>
        </div>
      </div>
    </div>
  );
}
