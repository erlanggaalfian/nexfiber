/** Pita progres sinkron otomatis satu OLT (kontrak GET /api/olts/{id}/sync-status).
 *  Dipakai di baris tabel OLT Management dan di kepala Detail OLT — tidak ada halaman
 *  baru, tidak ada tombol untuk memulai: status dipoll sendiri dan daftar ONU/OLT
 *  dimuat ulang sendiri saat selesai.
 *
 *  `showIdle` false (tabel) = diam saat tidak ada sinkron berjalan, supaya baris tidak penuh.
 */
import { useOltSync, useSyncAll, isSyncActive, syncSummary } from "../lib/oltSync";
import { useAuth } from "../lib/auth";
import { Button } from "./ui/button";
import { Bar, nf } from "./data";

export function OltSyncProgress({ oltId, showIdle = false }: { oltId: number; showIdle?: boolean }) {
  const { isManager } = useAuth();
  const q = useOltSync(oltId);
  const retry = useSyncAll(oltId);

  if (q.unavailable) {
    return showIdle ? <p className="text-xs text-muted">Progres sinkron belum tersedia.</p> : null;
  }
  if (!q.data) return null;

  const s = q.data;
  const { done, total, pct, running, failed, onu } = syncSummary(s);
  const active = isSyncActive(s);
  if (!active && s.state === "success" && !showIdle) return null;

  const head = active
    ? `Sinkron ${done}/${total}${running ? `: ${running.label}` : ""}`
    : s.state === "failed"
      ? `Sinkron gagal ${done}/${total}`
      : `Sinkron selesai ${total}/${total}`;
  const tone = s.state === "failed" ? "bg-down" : "bg-fiber";

  return (
    <div className="flex w-full min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className={s.state === "failed" ? "text-down" : ""}>
        {head}
        {onu !== null && <span className="ml-1 font-mono">ONU {nf.format(onu)}</span>}
      </span>
      <Bar pct={pct} tone={tone} className="w-24 shrink-0" />
      <span className="font-mono">{Math.round(pct)}%</span>
      {failed.length > 0 && (
        <span className="min-w-0 truncate text-down">
          {failed[0].label}: {failed[0].error ?? "gagal tanpa pesan"}
        </span>
      )}
      {/* sync-all butuh admin di backend; peran User hanya melihat progresnya. */}
      {s.state === "failed" && isManager && (
        <Button size="sm" onClick={() => retry.mutate()} disabled={retry.isPending}>
          {retry.isPending ? "Mengantre ..." : "Coba lagi"}
        </Button>
      )}
      {retry.isError && <span className="text-down">{retry.error.message}</span>}
    </div>
  );
}

/** Varian untuk baris tabel: tidak merender <tr> sama sekali kalau tidak ada progres,
 *  supaya tabel tidak kebagian baris kosong + garis pemisah percuma. */
export function OltSyncProgressRow({ oltId, colSpan }: { oltId: number; colSpan: number }) {
  const q = useOltSync(oltId);
  if (q.unavailable || !q.data) return null;
  if (q.data.state === "success") return null;
  return (
    <tr className="border-b last:border-0">
      <td className="px-3 pb-2 align-top" colSpan={colSpan}>
        <OltSyncProgress oltId={oltId} />
      </td>
    </tr>
  );
}
