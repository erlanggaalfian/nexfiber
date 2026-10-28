/** Settings -> ONU Types (PRD 3.4.10). Katalog global: Superadmin kelola, peran lain baca saja. */
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import * as z from "zod";
import { Confirm, Drawer, Field, MobileCard, TableCard, cell, filterInput, input } from "../../components/crud";
import { PageTitle } from "../../components/data";
import { Button } from "../../components/ui/button";
import { api, qs, type OnuType } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const PON_TYPES = [
  ["gpon", "GPON"], ["epon", "EPON"], ["xgpon", "XG-PON"], ["xgspon", "XGS-PON"],
] as const;
const CAPABILITIES = [
  ["bridging", "Bridging"], ["bridging_routing", "Bridging + Routing"],
] as const;
const label = (pairs: readonly (readonly [string, string])[], v: string) =>
  pairs.find(([k]) => k === v)?.[1] ?? v;

const schema = z.object({
  pon_type: z.enum(["gpon", "epon", "xgpon", "xgspon"]),
  name: z.string().min(1, "Wajib diisi").max(100),
  eth_ports: z.coerce.number().int().min(0).max(32),
  wifi_ssids: z.coerce.number().int().min(0).max(32),
  voip_ports: z.coerce.number().int().min(0).max(32),
  catv: z.boolean(),
  capability: z.enum(["bridging", "bridging_routing"]),
  allow_custom_profiles: z.boolean(),
  is_active: z.boolean(),
});
type Form = z.input<typeof schema>;

function OnuTypeDrawer({ edit, onClose }: { edit: OnuType | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { register, handleSubmit, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      pon_type: (edit?.pon_type ?? "gpon") as Form["pon_type"],
      name: edit?.name ?? "",
      eth_ports: edit?.eth_ports ?? 1,
      wifi_ssids: edit?.wifi_ssids ?? 0,
      voip_ports: edit?.voip_ports ?? 0,
      catv: edit?.catv ?? false,
      capability: (edit?.capability ?? "bridging") as Form["capability"],
      allow_custom_profiles: edit?.allow_custom_profiles ?? false,
      is_active: edit?.is_active ?? true,
    },
  });
  const save = useMutation({
    mutationFn: (f: Form) =>
      edit
        ? api<OnuType>(`/api/onu-types/${edit.id}`, { method: "PATCH", json: schema.parse(f) })
        : api<OnuType>("/api/onu-types", { method: "POST", json: schema.parse(f) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["onu-types"] }); onClose(); },
  });

  return (
    <Drawer
      title={edit ? `Edit ${edit.name}` : "Tambah tipe ONU"}
      onClose={onClose}
      dirty={formState.isDirty}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending}
      error={save.error?.message}
    >
      <Field label="PON type">
        <select className={input} {...register("pon_type")}>
          {PON_TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      </Field>
      <Field label="Nama tipe ONU (sama dengan nama di OLT)" error={formState.errors.name?.message}>
        <input className={input} autoFocus autoComplete="off" {...register("name")} />
      </Field>
      <div className="grid grid-cols-3 gap-2">
        <Field label="Port Ethernet"><input className={input} type="number" min={0} {...register("eth_ports")} /></Field>
        <Field label="SSID WiFi"><input className={input} type="number" min={0} {...register("wifi_ssids")} /></Field>
        <Field label="Port VoIP"><input className={input} type="number" min={0} {...register("voip_ports")} /></Field>
      </div>
      <Field label="Capability">
        <select className={input} {...register("capability")}>
          {CAPABILITIES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      </Field>
      <label className="mb-2 flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 hover:bg-sunken max-md:py-3"><input type="checkbox" {...register("catv")} />CATV</label>
      <label className="mb-2 flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 hover:bg-sunken max-md:py-3"><input type="checkbox" {...register("allow_custom_profiles")} />Izinkan custom profile</label>
      <label className="mb-2 flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 hover:bg-sunken max-md:py-3"><input type="checkbox" {...register("is_active")} />Aktif</label>
    </Drawer>
  );
}

export function OnuTypes() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const canWrite = me.role === "superadmin";
  const [q, setQ] = useState("");
  const [pon, setPon] = useState("");
  const [drawer, setDrawer] = useState<{ edit: OnuType | null } | null>(null);
  const [del, setDel] = useState<OnuType | null>(null);

  const types = useQuery({
    queryKey: ["onu-types", q],
    queryFn: () => api<OnuType[]>(`/api/onu-types${qs({ q })}`),
  });
  const remove = useMutation({
    mutationFn: (t: OnuType) => api<void>(`/api/onu-types/${t.id}`, { method: "DELETE" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["onu-types"] }); setDel(null); },
  });

  const rows = (types.data ?? []).filter((t) => !pon || t.pon_type === pon);

  return (
    <>
      <PageTitle title="ONU Types">
        {canWrite && <Button variant="fiber" onClick={() => setDrawer({ edit: null })}>Tambah tipe</Button>}
      </PageTitle>

      <div className="mb-3 flex flex-wrap gap-2">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="Cari tipe ONU" className={`${filterInput} w-60`} />
        <select value={pon} onChange={(e) => setPon(e.target.value)} aria-label="Filter PON type"
                className={filterInput}>
          <option value="">Semua PON type</option>
          {PON_TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      </div>

      <TableCard
        query={{ ...types, data: rows }}
        loadingText="Memuat tipe ONU ..."
        empty="Belum ada tipe ONU."
        columns={["PON type", "ONU type", "ONU", "Ethernet", "WiFi", "VoIP", "CATV", "Capability", "Status", "Aksi"]}
        card={(t: OnuType) => (
          <MobileCard key={t.id}>
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate font-medium">{t.name}</span>
              <span className="inline-flex shrink-0 items-center gap-1.5 text-xs">
                <span className={`size-1.5 shrink-0 ${t.is_active ? "bg-up" : "bg-idle"}`} aria-hidden />
                {t.is_active ? "Aktif" : "Nonaktif"}
              </span>
            </div>
            <p className="font-mono text-xs text-muted">
              {label(PON_TYPES, t.pon_type)} · ONU {t.onu_count} · Eth {t.eth_ports} · WiFi {t.wifi_ssids}
            </p>
            <p className="text-xs text-muted">{label(CAPABILITIES, t.capability)}</p>
            {canWrite && (
              <div className="mt-1 flex flex-wrap gap-2">
                <Button size="sm" onClick={() => setDrawer({ edit: t })}>Edit</Button>
                <Button size="sm" variant="danger" onClick={() => setDel(t)}>Hapus</Button>
              </div>
            )}
          </MobileCard>
        )}
        row={(t: OnuType) => (
          <tr key={t.id} className="border-b last:border-0">
            <td className={cell}>{label(PON_TYPES, t.pon_type)}</td>
            <td className={cell}>{t.name}</td>
            <td className={`${cell} font-mono`}>{t.onu_count}</td>
            <td className={`${cell} font-mono`}>{t.eth_ports}</td>
            <td className={`${cell} font-mono`}>{t.wifi_ssids}</td>
            <td className={`${cell} font-mono`}>{t.voip_ports}</td>
            <td className={cell}>{t.catv ? "Ya" : "—"}</td>
            <td className={cell}>{label(CAPABILITIES, t.capability)}</td>
            <td className={cell}>
              <span className="inline-flex items-center gap-1.5">
                <span className={`size-1.5 shrink-0 ${t.is_active ? "bg-up" : "bg-idle"}`} aria-hidden />
                {t.is_active ? "Aktif" : "Nonaktif"}
              </span>
            </td>
            <td className={cell}>
              {canWrite ? (
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => setDrawer({ edit: t })}>Edit</Button>
                  <Button size="sm" variant="danger" onClick={() => setDel(t)}>Hapus</Button>
                </div>
              ) : "—"}
            </td>
          </tr>
        )}
      />

      {drawer && <OnuTypeDrawer edit={drawer.edit} onClose={() => setDrawer(null)} />}
      {del && (
        <Confirm
          title={`Hapus ${del.name}?`}
          body={del.onu_count > 0
            ? `Tipe ini dipakai ${del.onu_count} ONU, penghapusan akan ditolak.`
            : "Tipe ONU dihapus permanen. Penghapusan juga ditolak bila tipe masih dipakai preset."}
          action="Hapus"
          busy={remove.isPending}
          error={remove.error?.message}
          onConfirm={() => remove.mutate(del)}
          onClose={() => { remove.reset(); setDel(null); }}
        />
      )}
    </>
  );
}
