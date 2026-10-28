import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, Fragment, useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate } from "react-router";
import * as z from "zod";
import { PageTitle, StatusBadge, fmtDateTime } from "../../components/data";
import { Drawer, Field, TableCard, cell, filterInput, input } from "../../components/crud";
import { ConfirmShell } from "../../components/onu/modals/ModalShell";
import { OltSyncProgressRow } from "../../components/OltSyncProgress";
import { Button, buttonClass } from "../../components/ui/button";
import { api, qs, type Olt, type OltRow } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const inRange = (min: number, max: number) =>
  z.string().refine(
    (v) => /^\d+$/.test(v) && Number(v) >= min && Number(v) <= max, `Angka ${min}-${max}`);
const schema = z.object({
  name: z.string().min(1).max(100),
  // Regex saja tidak cukup: "999.1.1.1" lolos regex tapi ditolak backend (IPv4Address).
  host: z.string().refine(
    (v) => /^(\d{1,3}\.){3}\d{1,3}$/.test(v) && v.split(".").every((o) => Number(o) <= 255),
    "Format IPv4 tidak valid"),
  model: z.string().min(1).max(50),
  cli_protocol: z.enum(["ssh", "telnet"]),
  cli_port: inRange(1, 65535),
  cli_username: z.string().min(1).max(100),
  cli_password: z.string().max(128),
  snmp_port: inRange(1, 65535),
  snmp_community: z.string().max(128),
  snmp_community_rw: z.string().max(128),
  pon_port_count: inRange(1, 128),
  max_onu_per_port: inRange(1, 256),
  location: z.string().max(255),
  is_active: z.boolean(),
});
type Form = z.infer<typeof schema>;

/** Kredensial tidak pernah dikirim balik, jadi field rahasia selalu mulai kosong (PRD 3.4.8). */
const defaults = (edit: OltRow | null): Form => ({
  name: edit?.name ?? "",
  host: edit?.host ?? "",
  model: edit?.model ?? "C320",
  cli_protocol: (edit?.cli_protocol === "telnet" ? "telnet" : "ssh") as "ssh" | "telnet",
  cli_port: String(edit?.cli_port ?? 22),
  cli_username: edit?.cli_username ?? "",
  cli_password: "",
  snmp_port: String(edit?.snmp_port ?? 161),
  snmp_community: "",
  snmp_community_rw: "",
  pon_port_count: String(edit?.pon_port_count ?? 16),
  max_onu_per_port: String(edit?.max_onu_per_port ?? 128),
  location: edit?.location ?? "",
  is_active: edit?.is_active ?? true,
});

function OltDrawer({ edit, onClose }: { edit: OltRow | null; onClose: () => void }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { register, handleSubmit, getValues, watch, setValue, setError, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: defaults(edit),
  });
  // Port CLI mengikuti protokol HANYA bila port saat ini masih bernilai
  // default protokol sebelumnya (22 SSH / 23 Telnet). Mengubah protokol
  // setelah operator mengisi port non-standar (mis. SSH di 2222) tidak boleh
  // menimpa angka itu. Heuristik ini tidak bisa membedakan "port 22 yang
  // diisi manual saat SSH" dari default — tapi dalam kasus itu menimpa ke 23
  // saat pindah ke Telnet adalah perilaku yang memang diharapkan.
  const protocol = watch("cli_protocol");
  const prevProtocol = useRef(protocol);
  useEffect(() => {
    if (prevProtocol.current !== protocol) {
      const currentPort = getValues("cli_port");
      const prevDefault = prevProtocol.current === "ssh" ? "22" : "23";
      if (currentPort === prevDefault) {
        setValue("cli_port", protocol === "ssh" ? "22" : "23");
      }
      prevProtocol.current = protocol;
    }
  }, [protocol]); // eslint-disable-line react-hooks/exhaustive-deps

  const body = (f: Form) => {
    const out: Record<string, unknown> = {
      name: f.name, host: f.host, model: f.model, cli_protocol: f.cli_protocol,
      cli_port: Number(f.cli_port), cli_username: f.cli_username, snmp_port: Number(f.snmp_port),
      pon_port_count: Number(f.pon_port_count), max_onu_per_port: Number(f.max_onu_per_port),
      location: f.location || null,
    };
    // Rahasia hanya dikirim bila diisi; kosong saat edit = kredensial lama dipertahankan.
    for (const k of ["cli_password", "snmp_community", "snmp_community_rw"] as const) {
      if (f[k]) out[k] = f[k];
    }
    // Aktif hanya dikirim saat edit (OLT baru selalu aktif); menonaktifkan menghentikan
    // sinkron, mengaktifkan kembali memulai ulang rantai sinkron di backend.
    if (edit) out.is_active = f.is_active;
    return out;
  };

  const save = useMutation({
    mutationFn: (f: Form) =>
      edit
        ? api<Olt>(`/api/olts/${edit.id}`, { method: "PATCH", json: body(f) })
        : api<Olt>("/api/olts", { method: "POST", json: body(f) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["olts"] });
      onClose();
    },
  });

  const test = useMutation({
    mutationFn: () => {
      const f = getValues();
      return api<{ success: boolean; message: string }>("/api/olts/test", {
        method: "POST",
        json: { host: f.host, snmp_community: f.snmp_community, snmp_port: Number(f.snmp_port) },
      });
    },
  });

  return (
    <Drawer
      title={edit ? `Edit ${edit.name}` : "Tambah OLT"}
      onClose={onClose}
      onSubmit={handleSubmit((f) => {
        // Secret wajib saat create (backend min 1), opsional saat edit
        // (kosong = kredensial lama dipertahankan) — Zod tidak tahu mode edit.
        if (!edit && !f.cli_password) {
          setError("cli_password", { message: "Wajib diisi" }); return;
        }
        if (!edit && !f.snmp_community) {
          setError("snmp_community", { message: "Wajib diisi" }); return;
        }
        save.mutate(f);
      })}
      busy={save.isPending}
      error={save.error?.message}
    >
      <Field label="Nama" error={formState.errors.name?.message}>
        <input className={input} autoFocus autoComplete="off" {...register("name")} />
      </Field>
      <Field label="Lokasi">
        <input className={input} autoComplete="off" {...register("location")} />
      </Field>
      {edit && (
        <Field label="Status">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...register("is_active")} />
            Aktif (sinkron berjalan)
          </label>
        </Field>
      )}
      <Field label="Alamat IP" error={formState.errors.host?.message}>
        <input className={`${input} font-mono`} autoComplete="off" {...register("host")} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Tipe OLT">
          <input className={input} autoComplete="off" {...register("model")} />
        </Field>
        <Field label="Jumlah port PON" error={formState.errors.pon_port_count?.message}>
          <input className={input} type="number" min={1} max={128} {...register("pon_port_count")} />
        </Field>
        <Field label="Maks ONU per port" error={formState.errors.max_onu_per_port?.message}>
          <input className={input} type="number" min={1} max={256} {...register("max_onu_per_port")} />
        </Field>
        <Field label="Protokol CLI">
          <select className={input} {...register("cli_protocol")}>
            <option value="ssh">SSH</option>
            <option value="telnet">Telnet</option>
          </select>
        </Field>
        <Field label="Port CLI" error={formState.errors.cli_port?.message}>
          <input className={input} type="number" min={1} max={65535} {...register("cli_port")} />
        </Field>
      </div>
      {watch("cli_protocol") === "telnet" && (
        <p className="text-xs text-down">
          Telnet mengirim kredensial CLI tanpa enkripsi (plaintext). Pakai hanya
          di jaringan lokal tepercaya; bila memungkinkan, pakai SSH.
        </p>
      )}
      <Field label="Username CLI" error={formState.errors.cli_username?.message}>
        <input className={input} autoComplete="off" {...register("cli_username")} />
      </Field>
      <Field label={edit ? "Password CLI (kosong = tidak diubah)" : "Password CLI"}
             error={formState.errors.cli_password?.message}>
        <input className={input} type="password" autoComplete="new-password" {...register("cli_password")} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Port SNMP" error={formState.errors.snmp_port?.message}>
          <input className={input} type="number" min={1} max={65535} {...register("snmp_port")} />
        </Field>
        <Field label={edit ? "Community RO (kosong = tetap)" : "Community RO"}
               error={formState.errors.snmp_community?.message}>
          <input className={input} type="password" autoComplete="new-password" {...register("snmp_community")} />
        </Field>
      </div>
      <Field label={edit ? "Community RW (kosong = tetap)" : "Community RW"}>
        <input className={input} type="password" autoComplete="new-password" {...register("snmp_community_rw")} />
      </Field>
      {/* Pemilik utama hanya ditampilkan. Akses OLT per user diatur Superadmin di
          Settings > User Management (checklist OLT), satu tempat untuk olt_access. */}
      <Field label="Pemilik utama">
        <p className="text-muted">{edit ? edit.owner_name : me.full_name}</p>
      </Field>
      <div className="flex items-center gap-2">
        <Button onClick={() => test.mutate()} disabled={test.isPending || !watch("snmp_community")}>
          {test.isPending ? "Mengecek ..." : "Cek koneksi"}
        </Button>
        {!watch("snmp_community") && (
          <span className="text-muted">Isi community RO untuk cek koneksi</span>
        )}
        {test.data && (
          <span className={test.data.success ? "text-up" : "text-down"}>{test.data.message}</span>
        )}
        {test.isError && <span className="text-down">{test.error.message}</span>}
      </div>
    </Drawer>
  );
}

/** Hapus: diblok bila masih ada ONU kecuali nama OLT diketik ulang (PRD 3.4.8). */
function DeleteDialog({ olt, onClose }: { olt: OltRow; onClose: () => void }) {
  const qc = useQueryClient();
  const [typed, setTyped] = useState("");
  const needsName = olt.onu_count > 0;
  const del = useMutation({
    mutationFn: () =>
      api<void>(`/api/olts/${olt.id}${qs({ confirm_name: needsName ? typed : undefined })}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["olts"] });
      onClose();
    },
  });
  return (
    <ConfirmShell
      title={`Hapus ${olt.name}?`}
      body={needsName
        ? `${olt.onu_count} ONU ikut dinonaktifkan di aplikasi; perangkat tidak disentuh.`
        : "OLT dihapus dari aplikasi; perangkat tidak disentuh."}
      action="Hapus"
      onConfirm={() => del.mutate()}
      onClose={onClose}
      error={del.isError ? del.error.message : undefined}
      busy={del.isPending}
      disabled={needsName && typed !== olt.name}
    >
      {needsName && (
        <div className="mt-3">
          <Field label="Ketik nama OLT">
            <input
              className={`${input} font-mono`}
              autoFocus
              autoComplete="off"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
            />
          </Field>
        </div>
      )}
    </ConfirmShell>
  );
}

export function OltManagement() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [drawer, setDrawer] = useState<{ edit: OltRow | null } | null>(null);
  const [remove, setRemove] = useState<OltRow | null>(null);
  const isSuper = me.role === "superadmin";
  const allowed = me.role !== "user";
  const olts = useQuery({
    queryKey: ["olts", "rows", q.trim()],
    queryFn: () => api<OltRow[]>(`/api/olts/rows${qs({ search: q.trim() })}`),
    enabled: allowed,
  });
  // Cek koneksi per baris = job ke worker (DESIGN 13: aksi ke OLT tidak pernah sinkron).
  const recheck = useMutation({
    mutationFn: (olt: OltRow) => api<{ job_id: number }>(`/api/olts/${olt.id}/test`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["olts"] }),
  });
  const columns = ["Nama OLT", "Alamat IP", "Tipe",
    ...(isSuper ? ["Pemilik"] : []),
    "Status koneksi", "ONU", "Sinkron terakhir", "Aksi"];

  // Peran User tidak punya halaman ini (PRD 3.7); backend juga menolak 403.
  if (!allowed) return <Navigate to="/" replace />;

  return (
    <>
      <PageTitle title="OLT Management">
        <Button variant="fiber" onClick={() => setDrawer({ edit: null })}>Tambah OLT</Button>
      </PageTitle>

      <div className="mb-3 flex flex-wrap gap-2">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Cari nama, IP, tipe"
          className={`${filterInput} w-60`}
        />
      </div>

      <TableCard
        query={olts}
        columns={columns}
        empty="Belum ada OLT."
        loadingText="Memuat OLT ..."
        row={(o: OltRow) => (
          <Fragment key={o.id}>
          <tr className="border-b last:border-0">
            <td className={cell}>
              <Link to={`/olt/${o.id}`} className="text-fiber hover:underline">{o.name}</Link>
            </td>
            <td className={`${cell} font-mono`}>{o.host}</td>
            <td className={cell}>{o.model}</td>
            {isSuper && <td className={cell}>{o.owner_name}</td>}
            <td className={cell}>
              <StatusBadge status={o.status} withLabel />
              {o.last_error && <span className="ml-2 text-xs text-muted">{o.last_error}</span>}
            </td>
            <td className={`${cell} font-mono`}>{o.onu_count}</td>
            <td className={cell}>{fmtDateTime(o.last_sync_at)}</td>
            <td className={cell}>
              <div className="flex gap-2">
                <Link to={`/olt/${o.id}`} className={buttonClass("secondary", "sm")}>OLT Detail</Link>
                <Button size="sm" onClick={() => setDrawer({ edit: o })}>Edit</Button>
                <Button size="sm" onClick={() => recheck.mutate(o)} disabled={recheck.isPending}>
                  Cek koneksi
                </Button>
                <Button size="sm" variant="danger" onClick={() => setRemove(o)}>Hapus</Button>
              </div>
            </td>
          </tr>
          {/* Progres sinkron otomatis: baris ini hilang sendiri kalau tidak ada yang jalan. */}
          <OltSyncProgressRow oltId={o.id} colSpan={columns.length} />
          </Fragment>
        )}
      />

      {recheck.isError && (
        <p className="mt-3 text-sm text-down">Cek koneksi gagal: {recheck.error.message}</p>
      )}
      {drawer && <OltDrawer edit={drawer.edit} onClose={() => setDrawer(null)} />}
      {remove && <DeleteDialog olt={remove} onClose={() => setRemove(null)} />}
    </>
  );
}
