/** Ilustrasi panel belakang ONU — blok kanan-atas pada desain acuan (`design/onu-detail-stitch.html`).
 *
 *  Semua yang digambar diturunkan dari data NYATA:
 *  - jumlah port LAN dan telepon dari katalog ONU Types (`/api/onu-types`), bukan angka tetap;
 *  - lampu PON hijau hanya saat status ONU benar-benar `online` (satu state nyata, tanpa
 *    animasi/pulse).
 *
 *  Panel tidak pernah dirender saat tipe ONU belum ada di katalog — lebih baik kosong daripada
 *  menggambar port yang belum tentu ada di perangkat.
 */
function Jack({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex shrink-0 flex-col items-center gap-1">
      {children}
      <span className="font-mono text-[10px] uppercase leading-none text-faint">{label}</span>
    </div>
  );
}

export function OnuRearPanel(
  { ethPorts, voipPorts, online }: { ethPorts: number; voipPorts: number; online: boolean },
) {
  return (
    <div className="overflow-x-auto rounded-md border bg-sunken px-3 py-2.5"
         role="img"
         aria-label={`Panel belakang ONU: 1 port PON (${online ? "menyala" : "mati"}), ${voipPorts} port telepon, ${ethPorts} port LAN`}>
      <div className="flex w-max items-end gap-2.5">
        <Jack label="PON">
          <span className="flex h-6 w-6 items-center justify-center rounded-sm border border-line-strong bg-surface">
            <span aria-hidden className={`h-2 w-2 rounded-sm ${online ? "bg-up" : "bg-idle"}`} />
          </span>
        </Jack>
        {Array.from({ length: voipPorts }, (_, i) => (
          <Jack key={`tel-${i}`} label={`Tel${voipPorts > 1 ? i + 1 : ""}`}>
            <span className="block h-5 w-4 rounded-sm border border-line-strong bg-app" />
          </Jack>
        ))}
        {Array.from({ length: ethPorts }, (_, i) => (
          <Jack key={`lan-${i}`} label={`LAN${ethPorts > 1 ? i + 1 : ""}`}>
            <span className="flex h-6 w-6 items-end justify-center rounded-sm border border-line-strong bg-surface">
              <span aria-hidden className="mb-1 h-2 w-3.5 rounded-sm bg-app" />
            </span>
          </Jack>
        ))}
        <Jack label="Reset">
          <span className="block h-5 w-2.5 rounded-sm border border-line-strong bg-app" />
        </Jack>
        <Jack label="Power">
          <span className="block h-5 w-4 rounded-sm border border-line-strong bg-app" />
        </Jack>
      </div>
    </div>
  );
}
