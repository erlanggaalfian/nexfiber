/** Configured — PRD 3.4.5, wireframe DESIGN 12.5. Daftar ONU terkonfigurasi: cari, filter
 *  multi-pilih (tersimpan di URL), aksi massal, Export CSV yang mengikuti filter aktif.
 *
 *  Semua tabel/dropdown/konfirmasi memakai komponen bersama di components/crud.tsx dan
 *  data.tsx — jangan menulis markup tabel/drawer sendiri di sini (itu yang membuat halaman
 *  kehilangan animasi MOTION 2, lihat bug UserManagement sebelumnya).
 *
 *  Bucket sinyal TIDAK dihitung di halaman ini: nilai dBm dirender lewat SignalBar dan
 *  filternya dikirim ke backend (app/core/signal.py). Satu definisi bucket saja.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import {
  Confirm, FilterChip, MobileCard, MultiFilter, TableCard, cell, filterInput, input,
} from "../components/crud";
import { PageTitle, RX_BUCKETS, SignalBar, StatusBadge, fmtAgo, nf } from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, download, qsMulti,
  type BulkActionResult, type Olt, type OnuRow, type OnuType, type Page, type SpeedProfile,
  type Splitter, type Vlan, type Zone,
} from "../lib/api";
import { useAuth } from "../lib/auth";

const STATUS_OPTIONS = [
  { value: "online", label: "Online" },
  { value: "offline", label: "Offline" },
  { value: "los", label: "LOS" },
  { value: "dying_gasp", label: "Dying Gasp" },
  { value: "power_off", label: "Mati listrik" },
  { value: "unknown", label: "Belum diketahui" },
];

/** Label bucket diambil dari RX_BUCKETS supaya tidak ada daftar bucket kedua. */
const SIGNAL_OPTIONS = [
  ...(["good", "fair", "weak", "critical"] as const).map((b) => ({
    value: b, label: RX_BUCKETS[b].label,
  })),
  { value: "los", label: "LOS / tanpa bacaan" },
];

const SIZES = [25, 50, 100, 200];

/** Filter yang disimpan di URL; multi = daftar, single = satu nilai. */
const MULTI_KEYS = ["status", "signal", "olt_id", "vlan_id", "zone_id", "splitter_id",
                    "download_speed_profile_id", "upload_speed_profile_id", "onu_type"] as const;
type MultiKey = (typeof MULTI_KEYS)[number];

type BulkAction = "reboot_onu" | "resync_onu" | "set_state" | "delete_onu";

const BULK_LABELS: Record<BulkAction, string> = {
  reboot_onu: "Reboot",
  resync_onu: "Resync config",
  set_state: "Nonaktifkan",
  delete_onu: "Hapus",
};

export function Configured() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isManager } = useAuth();
  const [picked, setPicked] = useState<string[]>([]);
  const [showMoreFilters, setShowMoreFilters] = useState(false);
  const [bulk, setBulk] = useState<BulkAction | null>(null);
  const [note, setNote] = useState("");
  const [downloadError, setDownloadError] = useState("");

  const q = params.get("q") ?? "";
  // Sanitasi page/size seperti Logs: NaN/nol/negatif -> 1, size di luar SIZES -> 50.
  // Tanpa ini ?page=abc dulu jadi NaN dan dikirim ke backend (422), dan ?size=7
  // membuat footer "1–7 dari N" padahal backend tetap memotong sesuai size-nya.
  const rawPage = Number(params.get("page") ?? 1);
  const page = Number.isFinite(rawPage) && rawPage >= 1 ? Math.floor(rawPage) : 1;
  const rawSize = Number(params.get("size") ?? 50);
  const size = SIZES.includes(rawSize) ? rawSize : 50;
  // Kotak cari controlled + debounce 300ms: sebelumnya input uncontrolled
  // (defaultValue) sehingga Reset (setParams kosong) tidak mengosongkan kotak,
  // dan tiap ketikan langsung memicu query baru.
  const [searchText, setSearchText] = useState(q);
  useEffect(() => { setSearchText(q); }, [q]);
  useEffect(() => {
    if (searchText === q) return;
    const t = setTimeout(() => patch({ q: searchText }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText]);
  const multi = useMemo(() => {
    const out = {} as Record<MultiKey, string[]>;
    for (const k of MULTI_KEYS) out[k] = params.getAll(k);
    return out;
  }, [params]);

  function patch(next: Record<string, string | string[] | number | undefined>, resetPage = true) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      p.delete(k);
      if (Array.isArray(v)) v.forEach((item) => p.append(k, item));
      else if (v !== undefined && v !== "") p.set(k, String(v));
    }
    if (resetPage) p.delete("page");
    setParams(p, { replace: true });
    setPicked([]);
  }

  const filterQuery = { q, page, size, ...multi };
  const onus = useQuery({
    queryKey: ["onus", filterQuery],
    queryFn: () => api<Page<OnuRow>>(`/api/onus${qsMulti({ ...filterQuery, sort: "serial" })}`),
    refetchInterval: 60_000,  // DESIGN 13: auto-refresh 60 detik
  });
  const olts = useQuery({ queryKey: ["olts"], queryFn: () => api<Olt[]>("/api/olts") });
  const vlans = useQuery({ queryKey: ["vlans"], queryFn: () => api<Vlan[]>("/api/vlans") });
  const zones = useQuery({ queryKey: ["zones"], queryFn: () => api<Zone[]>("/api/zones") });
  const splitters = useQuery({
    queryKey: ["splitters"], queryFn: () => api<Splitter[]>("/api/splitters"),
  });
  const profiles = useQuery({
    queryKey: ["speed-profiles"], queryFn: () => api<SpeedProfile[]>("/api/speed-profiles"),
  });
  const onuTypeCatalog = useQuery({
    queryKey: ["onu-types"], queryFn: () => api<OnuType[]>("/api/onu-types"),
  });

  const exportCsv = useMutation({
    mutationFn: () => download(
      `/api/onus/export.csv${qsMulti({ ...filterQuery, page: undefined, size: undefined, sort: "serial" })}`,
      "onu.csv",
    ),
    onSuccess: () => setDownloadError(""),
    onError: (e: Error) => setDownloadError(e.message),
  });

  const syncCustomers = useMutation({
    mutationFn: (oltId: string) =>
      api<{ job_id: number }>(`/api/onus/sync${qsMulti({ olt_id: oltId })}`, { method: "POST" }),
    onSuccess: (r) => setNote(`Job sync pelanggan #${r.job_id} dibuat.`),
    onError: (e: Error) => setNote(e.message),
  });

  const runBulk = useMutation({
    mutationFn: (action: BulkAction) =>
      api<BulkActionResult>("/api/onus/bulk", {
        method: "POST",
        json: { serials: picked, action, ...(action === "set_state" ? { enabled: false } : {}) },
      }),
    onSuccess: (r) => {
      // Tanpa optimistic update (AGENTS.md): baris baru berubah setelah job selesai.
      setNote(`${r.queued} job dibuat${r.failed ? `, ${r.failed} gagal: ${
        r.items.filter((i) => i.error).map((i) => `${i.serial_number} (${i.error})`).join("; ")}` : "."}`);
      setBulk(null);
      setPicked([]);
      qc.invalidateQueries({ queryKey: ["onus"] });
    },
    onError: (e: Error) => setNote(e.message),
  });

  const rows = onus.data?.items ?? [];
  const total = onus.data?.total ?? 0;
  const pages = Math.max(Math.ceil(total / size), 1);
  // Clamp page ke halaman terakhir bila total menyusut (pola yang sama dengan Logs).
  useEffect(() => {
    if (onus.data && page > pages) patch({ page: pages }, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onus.data, page, pages]);
  const allPicked = rows.length > 0 && picked.length === rows.length;

  const labelFor = (key: MultiKey, value: string) => {
    const find = <T extends { id: number }>(list: T[] | undefined, name: (t: T) => string) =>
      name(list?.find((x) => String(x.id) === value) ?? ({} as T)) || value;
    switch (key) {
      case "status": return STATUS_OPTIONS.find((o) => o.value === value)?.label ?? value;
      case "signal": return SIGNAL_OPTIONS.find((o) => o.value === value)?.label ?? value;
      case "olt_id": return find(olts.data, (o) => o.name);
      case "vlan_id": return find(vlans.data, (v) => `VLAN ${v.vlan_id}`);
      case "zone_id": return find(zones.data, (z) => z.name);
      case "splitter_id": return find(splitters.data, (s) => s.name);
      case "download_speed_profile_id": return find(profiles.data, (p) => p.name);
      case "upload_speed_profile_id": return find(profiles.data, (p) => p.name);
      default: return value;
    }
  };
  const chipTitle: Record<MultiKey, string> = {
    status: "Status", signal: "Sinyal", olt_id: "OLT", vlan_id: "VLAN", zone_id: "Zone",
    splitter_id: "Splitter", download_speed_profile_id: "Profile DN", upload_speed_profile_id: "Profile UP",
    onu_type: "Tipe",
  };
  const activeChips = MULTI_KEYS.flatMap((k) => multi[k].map((v) => ({ key: k, value: v })));
  // Opsi tipe = gabungan katalog + nilai yang muncul di baris. Mengganti opsi
  // sepenuhnya dengan katalog TIDAK aman: Onu.onu_type adalah string bebas
  // (nama katalog saat authorize, tapi bisa juga tipe pending/legacy seperti
  // "ALL-ONT"), sehingga tipe di luar katalog akan hilang dari filter dan
  // tidak bisa dipilih lagi. Gabungan ini memperbaiki keterbatasan lama
  // (opsi hanya dari halaman aktif) tanpa menghilangkan tipe yang sudah ada.
  const onuTypes = useMemo(
    () => [...new Set([
      ...(onuTypeCatalog.data ?? []).map((t) => t.name),
      ...rows.map((r) => r.onu_type).filter((t): t is string => !!t),
    ])].map((t) => ({ value: t, label: t })),
    [onuTypeCatalog.data, rows],
  );

  return (
    <>
      <PageTitle title="Configured">
        <span className="text-muted">{nf.format(total)} ONU</span>
        {isManager && (
          <select
            aria-label="Sync pelanggan dari OLT"
            className={filterInput}
            value=""
            onChange={(e) => e.target.value && syncCustomers.mutate(e.target.value)}
          >
            <option value="">Sync pelanggan ...</option>
            {(olts.data ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        )}
        <Button onClick={() => exportCsv.mutate()} disabled={exportCsv.isPending}>
          {exportCsv.isPending ? "Menyiapkan ..." : "Export CSV"}
        </Button>
      </PageTitle>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <input
          className={`${input} max-w-xs`}
          placeholder="Nama, SN, alamat, PPPoE, external ID ..."
          value={searchText}
          aria-label="Cari ONU"
          onChange={(e) => setSearchText(e.target.value)}
        />
        <MultiFilter label="OLT" value={multi.olt_id} onChange={(v) => patch({ olt_id: v })}
          options={(olts.data ?? []).map((o) => ({ value: String(o.id), label: o.name }))} />
        <MultiFilter label="Status" value={multi.status} onChange={(v) => patch({ status: v })}
          options={STATUS_OPTIONS} />
        <Button size="sm" onClick={() => setShowMoreFilters((v) => !v)} aria-expanded={showMoreFilters}>
          {showMoreFilters ? "Sembunyikan filter" : "Filter lainnya"}
        </Button>
        {showMoreFilters && (
          <>
            <MultiFilter label="Sinyal" value={multi.signal} onChange={(v) => patch({ signal: v })}
              options={SIGNAL_OPTIONS} />
            <MultiFilter label="Tipe" value={multi.onu_type} onChange={(v) => patch({ onu_type: v })}
              options={onuTypes} />
            <MultiFilter label="Profile download" value={multi.download_speed_profile_id}
              onChange={(v) => patch({ download_speed_profile_id: v })}
              options={(profiles.data ?? []).filter((p) => p.direction === "download")
                .map((p) => ({ value: String(p.id), label: p.name }))} />
            <MultiFilter label="Profile upload" value={multi.upload_speed_profile_id}
              onChange={(v) => patch({ upload_speed_profile_id: v })}
              options={(profiles.data ?? []).filter((p) => p.direction === "upload")
                .map((p) => ({ value: String(p.id), label: p.name }))} />
            <MultiFilter label="VLAN" value={multi.vlan_id} onChange={(v) => patch({ vlan_id: v })}
              options={(vlans.data ?? []).map((v) => ({ value: String(v.id), label: `VLAN ${v.vlan_id} · ${v.name}` }))} />
            <MultiFilter label="Zone" value={multi.zone_id} onChange={(v) => patch({ zone_id: v })}
              options={(zones.data ?? []).map((z) => ({ value: String(z.id), label: z.name }))} />
            <MultiFilter label="Splitter" value={multi.splitter_id}
              onChange={(v) => patch({ splitter_id: v })}
              options={(splitters.data ?? []).map((s) => ({ value: String(s.id), label: s.name }))} />
          </>
        )}
        {(activeChips.length > 0 || q) && (
          <Button variant="quiet" size="sm" onClick={() => { setSearchText(""); setParams(new URLSearchParams(), { replace: true }); }}>
            Reset
          </Button>
        )}
      </div>

      {activeChips.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1">
          {activeChips.map(({ key, value }) => (
            <FilterChip
              key={`${key}:${value}`}
              label={`${chipTitle[key]}: ${labelFor(key, value)}`}
              onRemove={() => patch({ [key]: multi[key].filter((v) => v !== value) })}
            />
          ))}
        </div>
      )}

      {(note || downloadError) && (
        <p className="mb-2 text-muted" role="status">{note || downloadError}</p>
      )}
      {total > 50000 && (
        <p className="mb-2 text-amber" role="status">
          Export CSV hanya mengekspor 50.000 dari {nf.format(total)} baris (batas backend).
        </p>
      )}

      <TableCard
        query={{ ...onus, data: rows }}
        loadingText="Memuat ONU terkonfigurasi ..."
        empty="Tidak ada ONU yang cocok dengan filter ini."
        columns={[
          { label: "", header: (
            <input type="checkbox" aria-label="Pilih semua di halaman ini" checked={allPicked}
                   onChange={(e) => setPicked(e.target.checked ? rows.map((r) => r.serial_number) : [])} />
          )},
          "Status", "Nama pelanggan", "Serial number ↑", "OLT · PON", "VLAN",
          { label: "Splitter", className: "hidden lg:table-cell" },
          { label: "Zone", className: "hidden lg:table-cell" },
          "Rx ONU",
          { label: "Rx OLT", className: "hidden lg:table-cell" },
          "Terlihat"]}
        card={(o: OnuRow) => (
          <MobileCard key={o.id} onClick={() => navigate(`/onu/${o.id}`)}>
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate font-medium">{o.customer_name ?? o.name ?? "—"}</span>
              <span className="flex shrink-0 items-center gap-2" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  aria-label={`Pilih ${o.serial_number}`}
                  checked={picked.includes(o.serial_number)}
                  onChange={(e) => setPicked(e.target.checked
                    ? [...picked, o.serial_number]
                    : picked.filter((s) => s !== o.serial_number))}
                />
                <StatusBadge status={o.admin_state === "disabled" ? "disabled" : o.status}
                             reason={o.last_down_reason} withLabel />
              </span>
            </div>
            <p className="truncate font-mono text-xs text-muted">
              {o.serial_number} · {o.olt_name} · {o.slot}/{o.port}{o.onu_index === null ? "" : `:${o.onu_index}`}
            </p>
            <p className="flex flex-wrap items-center gap-2 text-xs">
              <SignalBar dbm={o.rx_power_dbm} />
              <span className="font-mono text-muted">VLAN {o.vlan_number ?? "—"}</span>
              <span className="text-muted">Terlihat {fmtAgo(o.last_seen_at)}</span>
            </p>
          </MobileCard>
        )}
        row={(o: OnuRow) => (
          <tr
            key={o.id}
            className="cursor-pointer border-b last:border-0 hover:bg-sunken"
            onClick={() => navigate(`/onu/${o.id}`)}
          >
            <td className={cell} onClick={(e) => e.stopPropagation()}>
              <input
                type="checkbox"
                aria-label={`Pilih ${o.serial_number}`}
                checked={picked.includes(o.serial_number)}
                onChange={(e) => setPicked(e.target.checked
                  ? [...picked, o.serial_number]
                  : picked.filter((s) => s !== o.serial_number))}
              />
            </td>
            <td className={cell}>
              <StatusBadge status={o.admin_state === "disabled" ? "disabled" : o.status}
                           reason={o.last_down_reason} withLabel />
            </td>
            <td className={cell}>{o.customer_name ?? o.name ?? "—"}</td>
            <td className={`${cell} font-mono`}>{o.serial_number}</td>
            <td className={`${cell} font-mono`}>
              {o.olt_name} · {o.slot}/{o.port}{o.onu_index === null ? "" : `:${o.onu_index}`}
            </td>
            <td className={`${cell} font-mono`}>{o.vlan_number ?? "—"}</td>
            <td className={`${cell} hidden lg:table-cell`}>{o.splitter_name ?? "—"}</td>
            <td className={`${cell} hidden lg:table-cell`}>{o.zone_name ?? "—"}</td>
            <td className={cell}><SignalBar dbm={o.rx_power_dbm} /></td>
            <td className={`${cell} font-mono hidden lg:table-cell`}>
              {o.olt_rx_power_dbm === null ? "—" : Number(o.olt_rx_power_dbm).toFixed(1)}
            </td>
            <td className={`${cell} font-mono`}>{fmtAgo(o.last_seen_at)}</td>
          </tr>
        )}
      />

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-muted">
        <span>
          {total === 0 ? "0" : `${(page - 1) * size + 1}–${Math.min(page * size, total)}`} dari {nf.format(total)}
        </span>
        <div className="flex items-center gap-2">
          <Button size="sm" disabled={page <= 1} onClick={() => patch({ page: page - 1 }, false)}>‹ Sebelumnya</Button>
          <span className="font-mono">{page} / {pages}</span>
          <Button size="sm" disabled={page >= pages} onClick={() => patch({ page: page + 1 }, false)}>Berikutnya ›</Button>
          <select aria-label="Jumlah per halaman" className={filterInput} value={size}
                  onChange={(e) => patch({ size: e.target.value })}>
            {SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {picked.length > 0 && (
        <div className="sticky bottom-[calc(4rem+env(safe-area-inset-bottom))] z-30 mt-2 flex flex-wrap items-center gap-2 rounded-md border bg-surface p-2 shadow-modal lg:bottom-0">
          <span className="font-semibold">{picked.length} dipilih</span>
          <Button size="sm" onClick={() => setBulk("reboot_onu")}>Reboot</Button>
          <Button size="sm" onClick={() => setBulk("resync_onu")}>Resync config</Button>
          <Button size="sm" onClick={() => setBulk("set_state")}>Nonaktifkan</Button>
          {isManager && (
            <Button size="sm" variant="danger" onClick={() => setBulk("delete_onu")}>Hapus</Button>
          )}
          <Button size="sm" variant="quiet" onClick={() => setPicked([])}>Batal pilih</Button>
        </div>
      )}

      {bulk && (
        <Confirm
          title={`${BULK_LABELS[bulk]} ${picked.length} ONU?`}
          body={`Satu job dibuat per ONU dan dijalankan oleh worker. ${
            bulk === "delete_onu"
              ? "ONU dihapus dari OLT dan di-soft-delete di Nexfiber."
              : "Perubahan baru terlihat setelah job selesai."
          }`}
          action={BULK_LABELS[bulk]}
          busy={runBulk.isPending}
          error={runBulk.error?.message}
          onConfirm={() => runBulk.mutate(bulk)}
          onClose={() => setBulk(null)}
        />
      )}

      {/* ponytail: pilih-semua di header kolom pertama, hanya untuk halaman yang
          tampil, bukan seluruh hasil filter — aksi massal dibatasi 200 ONU di backend.
          skipped: "pilih semua hasil filter", tambah kalau operator memang butuh
          aksi >200 ONU sekaligus. */}
    </>
  );
}
