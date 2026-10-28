/** Kontrak aksi ONU (modal halaman Detail ONU). Satu sumber untuk tipe + pemanggil API
 *  supaya tiap modal tidak menulis ulang path/invalidate-nya sendiri.
 *
 *    GET  /api/onus/{id}/actions         -> daftar aksi + dukungan driver
 *    GET  /api/onus/{id}/config-options  -> pilihan select (VLAN, zone, splitter, ...)
 *    PUT  /api/onus/{id}/location        -> kolom database saja (langsung berlaku)
 *    POST /api/onus/{id}/actions/{kind}  -> aksi tulis perangkat, selalu dengan confirm:true
 *
 *  `confirm:true` ditambahkan di SINI dan hanya dipanggil setelah pengguna menekan tombol
 *  konfirmasi di modal — tidak ada aksi perangkat yang terkirim dari satu klik saja.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type ActionKind =
  | "attached-vlans" | "onu-mode" | "eth-port" | "wifi-port" | "wifi-clear"
  | "external-id" | "onu-type" | "speed-profile" | "move" | "replace-sn"
  | "mgmt-ip" | "voip-enable" | "voip-disable" | "iptv"
  | "reboot" | "disable" | "enable" | "restore-factory" | "resync-config" | "delete";

export type OnuActionInfo = {
  kind: string;
  supported: boolean;
  writes_device: boolean;
  note?: string | null;
};

export type ActionResult = {
  ok: boolean;
  executed: boolean;
  detail?: string | null;
  commands?: string[] | null;
  /** Diisi backend untuk kind job (reboot/resync/speed/state/delete/restore);
   *  null/undefined untuk aksi langsung yang dieksekusi sinkron. */
  job_id?: number | null;
};

export type OptionVlan = { number: number; name: string; is_management: boolean };
export type OnuConfigOptions = {
  vlans: OptionVlan[];
  zones: { id: number; name: string }[];
  splitters: { id: number; name: string; zone_id: number | null; ports: number | null }[];
  sectors: { id: number; name: string }[];
  speed_profiles: { id: number; name: string; direction?: string | null }[];
  onu_types: { id: number; name: string }[];
  wan_modes: string[];
};

export type LocationBody = {
  zone_id: number | null; splitter_id: number | null; splitter_port: number | null;
  customer_name: string | null; address: string | null; contact: string | null;
  latitude: number | null; longitude: number | null;
};

/** VLAN management disembunyikan dari semua pilihan modal (aturan pemilik: cakupan OLT). */
export const serviceVlanOptions = (o: OnuConfigOptions | undefined) =>
  (o?.vlans ?? []).filter((v) => !v.is_management);

export function useOnuAction(onuId: number) {
  const qc = useQueryClient();
  const actions = useQuery({
    queryKey: ["onu", onuId, "actions"],
    queryFn: () => api<{ actions: OnuActionInfo[] }>(`/api/onus/${onuId}/actions`),
  });
  const options = useQuery({
    queryKey: ["onu", onuId, "config-options"],
    queryFn: () => api<OnuConfigOptions>(`/api/onus/${onuId}/config-options`),
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["onu"] });
    qc.invalidateQueries({ queryKey: ["onus"] });
  };
  const run = useMutation({
    mutationFn: ({ kind, body }: { kind: ActionKind; body?: Record<string, unknown> }) =>
      api<ActionResult>(`/api/onus/${onuId}/actions/${kind}`, {
        method: "POST",
        json: { ...(body ?? {}), confirm: true },
      }),
    onSuccess: invalidate,
  });
  const location = useMutation({
    mutationFn: (body: LocationBody) =>
      api<unknown>(`/api/onus/${onuId}/location`, { method: "PUT", json: body }),
    onSuccess: invalidate,
  });
  /** `null` = daftar aksi belum dimuat (bukan "tidak didukung"). */
  const support = (kind: ActionKind): OnuActionInfo | null =>
    actions.data?.actions.find((a) => a.kind === kind) ?? null;
  return { actions, options, run, location, support };
}
