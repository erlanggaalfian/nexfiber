/** Unconfigured — PRD 3.4.3, wireframe DESIGN 12.3. Daftar ONU belum terdaftar hasil job
 *  `sync_unconfigured` (jalan tiap 1 menit di worker); tombol Scan ulang hanya memaksa satu
 *  scan lebih awal untuk OLT terpilih.
 *
 *  ponytail: kolom "Rx saat terdeteksi" tidak ditampilkan — tabel unconfigured_onus memang
 *  tidak menyimpan Rx (ONU belum diotorisasi, belum ada entri optical). skipped: kolom Rx,
 *  tambah kalau sync_unconfigured mulai merekam Rx.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { MobileCard, TableCard, filterInput } from "../components/crud";
import { PageTitle, fmtAgo, fmtDateTime, nf } from "../components/data";
import { Button } from "../components/ui/button";
import { api, qs, type Olt, type PendingOnu } from "../lib/api";

const ALL = "";

export function Unconfigured() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [oltId, setOltId] = useState(ALL);
  const [note, setNote] = useState("");

  const olts = useQuery({ queryKey: ["olts"], queryFn: () => api<Olt[]>("/api/olts") });
  const pending = useQuery({
    queryKey: ["pending", oltId],
    queryFn: () => api<PendingOnu[]>(`/api/onus/pending${qs({ olt_id: oltId })}`),
    refetchInterval: 60_000,
  });
  const rescan = useMutation({
    mutationFn: () =>
      api<{ job_id: number }>(`/api/onus/pending/rescan${qs({ olt_id: oltId })}`, { method: "POST" }),
    onSuccess: (r) => {
      setNote(`Job scan ulang #${r.job_id} dibuat.`);
      qc.invalidateQueries({ queryKey: ["pending"] });
    },
    onError: (e: Error) => setNote(e.message),
  });

  const lastSeen = (pending.data ?? []).map((p) => p.last_seen_at).sort().at(-1) ?? null;

  return (
    <>
      <PageTitle title="Unconfigured">
        <span className="text-muted">{nf.format((pending.data ?? []).length)} ONU</span>
        <span className="text-muted">Scan terakhir {fmtDateTime(lastSeen)}</span>
        <Button onClick={() => rescan.mutate()} disabled={!oltId || rescan.isPending}>
          {rescan.isPending ? "Meminta scan ..." : "Scan ulang"}
        </Button>
      </PageTitle>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={oltId} onChange={(e) => { setOltId(e.target.value); setNote(""); }}
                aria-label="Tampilkan per OLT" className={filterInput}>
          <option value={ALL}>Semua OLT</option>
          {(olts.data ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        {note && <span className="text-muted" role="status">{note}</span>}
      </div>

      <TableCard
        query={pending}
        loadingText="Memuat ONU belum terdaftar ..."
        empty={`Tidak ada ONU baru. Scan terakhir ${fmtDateTime(lastSeen)}.`}
        emptyAction={(
          <Button onClick={() => rescan.mutate()} disabled={!oltId || rescan.isPending}>
            {rescan.isPending ? "Meminta scan ..." : "Scan ulang"}
          </Button>
        )}
        columns={["OLT", { label: "Slot", className: "text-right" },
          { label: "Port PON", className: "text-right" },
          "Nomor seri", "Tipe deteksi", "Pertama terlihat", "Terlihat", "Aksi"]}
        card={(p: PendingOnu) => (
          <MobileCard key={p.id}>
            <p className="truncate font-mono font-semibold">{p.serial_number}</p>
            <p className="truncate text-xs text-muted">
              {p.olt_name} · {p.slot}/{p.port}{p.onu_type ? ` · ${p.onu_type}` : ""}
            </p>
            <p className="text-xs text-muted">
              Pertama {fmtAgo(p.first_seen_at)} · Terlihat {fmtAgo(p.last_seen_at)}
            </p>
            {/* Aksi baris = teks tautan tenang warna fiber (bahasa kartu),
                bukan tombol isi — sesuai varian Tenang DESIGN §8. */}
            <button type="button" className="mt-1 flex min-h-11 w-full items-center text-sm font-medium text-fiber hover:underline"
                    onClick={() => navigate(`/unconfigured/authorize/${p.olt_id}/${p.serial_number}`)}>
              Otorisasi
            </button>
          </MobileCard>
        )}
        row={(p: PendingOnu) => (
          <tr key={p.id}>
            <td>
              <span className="block max-w-44 truncate" title={p.olt_name}>{p.olt_name}</span>
            </td>
            <td className="font-mono text-right">{p.slot}</td>
            <td className="font-mono text-right">{p.port}</td>
            <td className="font-mono font-semibold">{p.serial_number}</td>
            <td>
              <span className="block max-w-40 truncate" title={p.onu_type ?? undefined}>
                {p.onu_type ?? "—"}
              </span>
            </td>
            <td className="whitespace-nowrap">{fmtDateTime(p.first_seen_at)}</td>
            <td className="font-mono whitespace-nowrap">{fmtAgo(p.last_seen_at)}</td>
            <td>
              <button type="button" className="text-sm text-fiber hover:underline"
                      onClick={() => navigate(`/unconfigured/authorize/${p.olt_id}/${p.serial_number}`)}>
                Otorisasi
              </button>
            </td>
          </tr>
        )}
      />
    </>
  );
}
