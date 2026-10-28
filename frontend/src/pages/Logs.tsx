/** Logs — PRD 3.4.15 (read-only; retensi otomatis, tanpa tombol hapus). Pola filter+paginasi
 *  sama dengan Configured.tsx: state tersimpan di URL. Klik baris = dialog detail dengan
 *  command/response mentah (password sudah dimask backend sebelum disimpan).
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { filterInput } from "../components/crud";
import { ModalShell } from "../components/onu/modals/ModalShell";
import { PageTitle, fmtAgo, nf } from "../components/data";
import { Button } from "../components/ui/button";
import { api, qs, type LogPage, type LogRow, type Olt, type User } from "../lib/api";

export const LOG_CATEGORIES: { value: string; label: string }[] = [
  { value: "", label: "Semua kategori" },
  { value: "authorize", label: "Otorisasi" },
  { value: "reboot", label: "Reboot" },
  { value: "service", label: "Ubah layanan" },
  { value: "delete", label: "Hapus" },
  { value: "olt", label: "OLT" },
  { value: "user", label: "User" },
  { value: "login", label: "Login" },
];
const CATEGORIES = LOG_CATEGORIES;
const SIZES = [25, 50, 100, 200];
const DEFAULT_SIZE = 50;

function Detail({ log, onClose }: { log: LogRow; onClose: () => void }) {
  return (
    <ModalShell title={log.action} onClose={onClose} closeLabel="Tutup">
      <dl className="mb-3 grid grid-cols-2 gap-1 text-sm">
        <dt className="text-muted">Waktu</dt><dd>{new Date(log.created_at).toLocaleString("id-ID")}</dd>
        <dt className="text-muted">User</dt><dd>{log.username ?? "sistem"}</dd>
        <dt className="text-muted">OLT</dt><dd>{log.olt_name ?? "—"}</dd>
        <dt className="text-muted">ONU</dt><dd>{log.onu_serial ?? "—"}</dd>
        <dt className="text-muted">Hasil</dt><dd>{log.success ? "Sukses" : "Gagal"}</dd>
      </dl>
      {log.raw_command && (
        <>
          <p className="mb-1 text-xs text-muted">Command dikirim</p>
          <pre className="mb-3 max-h-48 overflow-auto rounded-sm bg-surface p-2 text-xs">{log.raw_command}</pre>
        </>
      )}
      {log.raw_output && (
        <>
          <p className="mb-1 text-xs text-muted">Respons perangkat</p>
          <pre className="mb-3 max-h-48 overflow-auto rounded-sm bg-surface p-2 text-xs">{log.raw_output}</pre>
        </>
      )}
      {!log.raw_command && !log.raw_output && <p className="text-muted">Tidak ada command perangkat untuk aksi ini.</p>}
    </ModalShell>
  );
}

export function Logs() {
  const [params, setParams] = useSearchParams();
  const [detail, setDetail] = useState<LogRow | null>(null);
  const q = params.get("q") ?? "";
  const oltId = params.get("olt_id") ?? "";
  const category = params.get("category") ?? "";
  // Filter yang sudah didukung backend tapi belum diekspos UI: user_id, since,
  // until, size. Param URL lama (tanpa keempatnya) tetap jalan: nilainya kosong
  // dan tidak dikirim. Tanggal di URL memakai format YYYY-MM-DD; ke backend
  // dikirim sebagai rentang hari penuh WIB-agnostik (00:00:00 s.d. 23:59:59).
  const userId = params.get("user_id") ?? "";
  const since = params.get("since") ?? "";
  const until = params.get("until") ?? "";
  const rawSize = Number(params.get("size") ?? DEFAULT_SIZE);
  const size = SIZES.includes(rawSize) ? rawSize : DEFAULT_SIZE;
  // Validasi page di frontend: ?page=abc dulu jadi NaN dan dikirim ke backend
  // (422), ?page=0/-1 juga tidak masuk akal. NaN/negatif/nol -> 1.
  const rawPage = Number(params.get("page") ?? 1);
  const page = Number.isFinite(rawPage) && rawPage >= 1 ? Math.floor(rawPage) : 1;

  function patch(next: Record<string, string | number | undefined>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) v === undefined || v === "" ? p.delete(k) : p.set(k, String(v));
    if (!("page" in next)) p.delete("page");
    setParams(p, { replace: true });
  }

  const olts = useQuery({ queryKey: ["olts"], queryFn: () => api<Olt[]>("/api/olts") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/api/users") });
  const logs = useQuery({
    queryKey: ["logs", q, oltId, category, page, userId, since, until, size],
    queryFn: () => api<LogPage>(`/api/logs${qs({
      q, olt_id: oltId, category, page, size,
      user_id: userId,
      since: since ? `${since}T00:00:00` : "",
      until: until ? `${until}T23:59:59` : "",
    })}`),
  });

  const total = logs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / size));
  // Bila page di URL melebihi total (mis. total menyusut setelah URL disimpan),
  // kembalikan ke halaman terakhir, bukan menampilkan footer "451–20 dari 20"
  // dengan tabel kosong.
  useEffect(() => {
    if (logs.data && page > pages) patch({ page: pages });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logs.data, page, pages]);

  return (
    <>
      <PageTitle title="Logs" />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={category} onChange={(e) => patch({ category: e.target.value })}
                aria-label="Kategori" className={filterInput}>
          {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
        <select value={oltId} onChange={(e) => patch({ olt_id: e.target.value })}
                aria-label="OLT" className={filterInput}>
          <option value="">Semua OLT</option>
          {(olts.data ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        <input type="search" value={q} onChange={(e) => patch({ q: e.target.value })}
               placeholder="Cari aksi, user, serial ONU" className={`${filterInput} w-64`} />
        <select value={userId} onChange={(e) => patch({ user_id: e.target.value })}
                aria-label="User" className={filterInput}>
          <option value="">Semua user</option>
          {(users.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
        </select>
        <label className="flex items-center gap-1 text-xs text-muted">
          Dari
          <input type="date" value={since} onChange={(e) => patch({ since: e.target.value })}
                 aria-label="Dari tanggal" className={filterInput} />
        </label>
        <label className="flex items-center gap-1 text-xs text-muted">
          Sampai
          <input type="date" value={until} onChange={(e) => patch({ until: e.target.value })}
                 aria-label="Sampai tanggal" className={filterInput} />
        </label>
        <select value={size} onChange={(e) => patch({ size: e.target.value })}
                aria-label="Jumlah per halaman" className={filterInput}>
          {SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <section className="entrance rounded-md border bg-surface">
        {logs.isPending ? (
          <div className="p-4 text-muted" aria-busy>Memuat log ...</div>
        ) : logs.isError ? (
          <div className="flex items-center gap-3 p-4" role="alert">
            <p className="text-down">{logs.error.message}</p>
            <Button onClick={() => logs.refetch()}>Coba lagi</Button>
          </div>
        ) : (logs.data?.items.length ?? 0) === 0 ? (
          <p className="p-4 text-muted">Belum ada log yang cocok dengan filter ini.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b">
                  {["Waktu", "User", "Target OLT", "Target ONU", "Kategori", "Keterangan", "Hasil"]
                    .map((c) => <th key={c} className="px-3 py-2 text-left align-middle">{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {logs.data!.items.map((l) => (
                  <tr key={l.id} className="cursor-pointer border-b last:border-0 hover:bg-sunken"
                      onClick={() => setDetail(l)}>
                    <td className="px-3 py-2 font-mono">{fmtAgo(l.created_at)}</td>
                    <td className="px-3 py-2">{l.username ?? "sistem"}</td>
                    <td className="px-3 py-2">{l.olt_name ?? "—"}</td>
                    <td className="px-3 py-2 font-mono">{l.onu_serial ?? "—"}</td>
                    <td className="px-3 py-2">{CATEGORIES.find((c) => c.value === l.category)?.label ?? l.category}</td>
                    <td className="px-3 py-2">{l.action}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5">
                        <span className={`size-1.5 shrink-0 ${l.success ? "bg-up" : "bg-down"}`} aria-hidden />
                        {l.success ? "Sukses" : "Gagal"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-muted">
        <span>{total === 0 ? "0" : `${(page - 1) * size + 1}–${Math.min(page * size, total)}`} dari {nf.format(total)}</span>
        <div className="flex items-center gap-2">
          <Button size="sm" disabled={page <= 1} onClick={() => patch({ page: 1 })}>«</Button>
          <Button size="sm" disabled={page <= 1} onClick={() => patch({ page: page - 1 })}>‹</Button>
          <span className="font-mono">{page} / {pages}</span>
          <Button size="sm" disabled={page >= pages} onClick={() => patch({ page: page + 1 })}>›</Button>
          <Button size="sm" disabled={page >= pages} onClick={() => patch({ page: pages })}>»</Button>
        </div>
      </div>

      {detail && <Detail log={detail} onClose={() => setDetail(null)} />}
    </>
  );
}
