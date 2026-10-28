import { Database, Pulse } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Confirm, Field, input } from "../../components/crud";
import { ErrorState, PageTitle, Skeleton } from "../../components/data";
import { Button } from "../../components/ui/button";
import { api, type Olt } from "../../lib/api";
import { useAuth } from "../../lib/auth";

type Kind = "traffic" | "signal";
type Retention = { traffic: number; signal: number };
type Stat = { kind: Kind; rows: number; oldest_at: string | null; newest_at: string | null; size_bytes: number | null };
type DeleteResult = { deleted: Record<string, number>; total: number };
type DeleteForm = { date_from: string; date_to: string; olt_id: string; deleted_olt_id: string };

const DAYS = [0, 7, 14, 30, 60, 90, 180];
const META = {
  traffic: { title: "Traffic history", icon: Pulse },
  signal: { title: "Signal history", icon: Database },
} as const;
const number = new Intl.NumberFormat("id-ID");
const date = (value: string | null) => value
  ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Jakarta" }).format(new Date(value))
  : "—";
const bytes = (value: number | null) => {
  if (value === null) return "—";
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let n = value / 1024;
  let unit = units[0];
  for (let i = 1; i < units.length && n >= 1024; i += 1) { n /= 1024; unit = units[i]; }
  return `${n.toFixed(n >= 10 ? 0 : 1)} ${unit}`;
};
const todayWib = () => new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Jakarta", year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date());

function GraphCard({ kind, stat, retention, olts, isSuperadmin }: {
  kind: Kind; stat: Stat | undefined; retention: Retention; olts: Olt[]; isSuperadmin: boolean;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<DeleteForm>({ date_from: "", date_to: "", olt_id: "", deleted_olt_id: "" });
  const [preview, setPreview] = useState<DeleteResult | null>(null);
  const [deleted, setDeleted] = useState<DeleteResult | null>(null);
  const [confirm, setConfirm] = useState(false);
  const meta = META[kind];
  const Icon = meta.icon;
  // ID OLT terhapus (Superadmin) mengalahkan dropdown: dropdown tidak pernah
  // menampilkan OLT yang sudah dihapus, jadi tanpa ini historinya tidak bisa
  // dibersihkan manual.
  const payload = {
    kinds: [kind], date_from: form.date_from, date_to: form.date_to,
    olt_id: form.deleted_olt_id ? Number(form.deleted_olt_id)
      : form.olt_id ? Number(form.olt_id) : null,
  };
  const saveRetention = useMutation({
    mutationFn: (days: number) => api<Retention>("/api/settings/graph-data/retention", {
      method: "PUT", json: { ...retention, [kind]: days },
    }),
    onSuccess: (data) => qc.setQueryData(["graph-data", "retention"], data),
  });
  const previewDelete = useMutation({
    mutationFn: () => api<DeleteResult>("/api/settings/graph-data/preview-delete", {
      method: "POST", json: payload,
    }),
    onSuccess: setPreview,
  });
  const remove = useMutation({
    mutationFn: () => api<DeleteResult>("/api/settings/graph-data/delete", {
      method: "POST", json: payload,
    }),
    onSuccess: (result) => {
      setConfirm(false);
      // Pratinjau dikosongkan dan angka HASIL tampil: kalau pratinjau lama
      // dipertahankan, halaman terlihat seperti data masih ada (dan tombol Hapus
      // masih aktif padahal data sudah terhapus).
      setPreview(null);
      setDeleted(result);
      qc.invalidateQueries({ queryKey: ["graph-data", "stats"] });
    },
  });
  const change = (key: keyof DeleteForm, value: string) => {
    setForm((old) => ({ ...old, [key]: value }));
    setPreview(null);
    setDeleted(null);
  };

  return (
    <section data-graph-kind={kind} className="entrance rounded-md border bg-surface p-4">
      <div className="mb-4 flex items-center gap-2">
        <Icon size={20} className="text-fiber" aria-hidden />
        <h2 className="font-medium">{meta.title}</h2>
      </div>

      <dl className="mb-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <div><dt className="text-xs text-muted">Baris</dt><dd className="font-mono">{number.format(stat?.rows ?? 0)}</dd></div>
        <div><dt className="text-xs text-muted">Ukuran tabel (semua OLT)</dt><dd className="font-mono">{bytes(stat?.size_bytes ?? null)}</dd></div>
        <div><dt className="text-xs text-muted">Tertua</dt><dd>{date(stat?.oldest_at ?? null)}</dd></div>
        <div><dt className="text-xs text-muted">Terbaru</dt><dd>{date(stat?.newest_at ?? null)}</dd></div>
      </dl>

      <div className="mb-5 rounded-sm bg-sunken p-3">
        <Field label="Retensi auto-delete">
          <select
            aria-label={`Retensi ${meta.title}`}
            className={input}
            value={retention[kind]}
            disabled={saveRetention.isPending}
            onChange={(e) => saveRetention.mutate(Number(e.target.value))}
          >
            {DAYS.map((days) => <option key={days} value={days}>{days === 0 ? "Nonaktif" : `${days} hari`}</option>)}
          </select>
        </Field>
        {saveRetention.error && <p role="alert" className="mt-2 text-xs text-down">{saveRetention.error.message}</p>}
      </div>

      <h3 className="mb-3 text-sm font-medium">Hapus manual</h3>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Dari tanggal">
          <input aria-label={`Dari tanggal ${meta.title}`} className={input} type="date" max={todayWib()}
                 value={form.date_from} onChange={(e) => change("date_from", e.target.value)} />
        </Field>
        <Field label="Sampai tanggal">
          <input aria-label={`Sampai tanggal ${meta.title}`} className={input} type="date" max={todayWib()}
                 value={form.date_to} onChange={(e) => change("date_to", e.target.value)} />
        </Field>
        <div className="col-span-2">
          <Field label="OLT (opsional)">
            <select aria-label={`OLT ${meta.title}`} className={input} value={form.olt_id}
                    onChange={(e) => change("olt_id", e.target.value)}>
              <option value="">Semua OLT dalam scope</option>
              {olts.map((olt) => <option key={olt.id} value={olt.id}>{olt.name}</option>)}
            </select>
          </Field>
        </div>
        {isSuperadmin && (
          <div className="col-span-2">
            <Field label="ID OLT terhapus (opsional, Superadmin)">
              <input aria-label={`ID OLT terhapus ${meta.title}`} className={input} inputMode="numeric"
                     value={form.deleted_olt_id}
                     onChange={(e) => change("deleted_olt_id", e.target.value.replace(/\D/g, ""))} />
            </Field>
          </div>
        )}
      </div>
      <div className="mt-3 flex min-h-8 items-center justify-between gap-3">
        <p aria-live="polite" className="text-sm text-muted">
          {preview && `${number.format(preview.total)} baris ditemukan`}
          {deleted && `${number.format(deleted.total)} baris dihapus.`}
        </p>
        <div className="flex gap-2">
          <Button size="sm" disabled={!form.date_from || !form.date_to || previewDelete.isPending}
                  onClick={() => previewDelete.mutate()}>Pratinjau</Button>
          {preview && preview.total > 0 && (
            <Button size="sm" variant="danger" onClick={() => setConfirm(true)}>Hapus</Button>
          )}
        </div>
      </div>
      {(previewDelete.error || remove.error) && (
        <p role="alert" className="mt-2 text-xs text-down">{(previewDelete.error ?? remove.error)?.message}</p>
      )}

      {confirm && preview && (
        <Confirm
          title={`Hapus ${meta.title}`}
          body={`${number.format(preview.total)} baris akan dihapus permanen.`}
          action="Hapus data"
          busy={remove.isPending}
          error={remove.error?.message}
          onClose={() => setConfirm(false)}
          onConfirm={() => remove.mutate()}
        />
      )}
    </section>
  );
}

export function GraphData() {
  const { me } = useAuth();
  const stats = useQuery({
    queryKey: ["graph-data", "stats"],
    queryFn: () => api<Stat[]>("/api/settings/graph-data/stats"),
  });
  const retention = useQuery({
    queryKey: ["graph-data", "retention"],
    queryFn: () => api<Retention>("/api/settings/graph-data/retention"),
  });
  const olts = useQuery({ queryKey: ["olts"], queryFn: () => api<Olt[]>("/api/olts") });
  const failed = stats.error ?? retention.error ?? olts.error;

  return (
    <>
      <PageTitle title="Graph Data" />
      {stats.isPending || retention.isPending || olts.isPending ? (
        <Skeleton text="Memuat data graph…" rows={6} />
      ) : failed || !retention.data ? (
        <ErrorState message={failed?.message ?? "Gagal memuat"} onRetry={() => {
          stats.refetch(); retention.refetch(); olts.refetch();
        }} />
      ) : (
        <div data-graph-grid className="grid gap-4 lg:grid-cols-2">
          {(["traffic", "signal"] as Kind[]).map((kind) => (
            <GraphCard key={kind} kind={kind} retention={retention.data}
                       stat={stats.data?.find((row) => row.kind === kind)} olts={olts.data ?? []}
                       isSuperadmin={me.role === "superadmin"} />
          ))}
        </div>
      )}
    </>
  );
}
