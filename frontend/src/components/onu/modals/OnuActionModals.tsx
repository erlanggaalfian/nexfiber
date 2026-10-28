/** Satu tempat yang merender modal aksi ONU mana pun + memanggil API-nya.
 *
 *  Halaman Detail ONU hanya menyimpan `state` modal (`setModal({ kind: ... })`) dan merender
 *  komponen ini sekali — tidak ada 20 blok `{open && <Modal .../>}` di halaman.
 *
 *  Semua aksi tulis perangkat lewat `useOnuAction().run` (POST .../actions/{kind} + confirm:true).
 *  `Update location details` lewat `PUT .../location` karena hanya menyentuh database.
 *  Pesan 501/4xx dari server ditampilkan apa adanya sebagai pesan error modal.
 */
import { useState } from "react";
import { ApiError, type OnuDetail } from "../../../lib/api";
import { JobTrace } from "../../crud";
import {
  useOnuAction, type ActionKind, type ActionResult, type LocationBody,
} from "../../../lib/onuActions";
import { AttachedVlansModal } from "./AttachedVlansModal";
import {
  ExternalIdModal, OnuTypeModal, ReplaceSnModal, SpeedProfileModal,
} from "./BasicModals";
import { ConfirmActionModal, type ConfirmKind } from "./ConfirmActionModal";
import { EthPortModal } from "./EthPortModal";
import { LocationModal } from "./LocationModal";
import { ModalShell } from "./ModalShell";
import { MoveModal } from "./MoveModal";
import { OnuModeModal } from "./OnuModeModal";
import { IptvModal, MgmtIpModal, VoipEnableModal } from "./ServiceModals";
import { WifiPortModal } from "./WifiPortModal";

export type OnuModalState =
  | { kind: "attached-vlans" }
  | { kind: "onu-mode" }
  | { kind: "location" }
  | { kind: "eth-port"; port: number; link?: string | null }
  | { kind: "wifi-port"; port: number }
  | { kind: "onu-type" }
  | { kind: "external-id" }
  | { kind: "speed-profile" }
  | { kind: "replace-sn" }
  | { kind: "mgmt-ip" }
  | { kind: "move" }
  | { kind: "voip-enable"; port: number }
  | { kind: "voip-disable"; port: number }
  | { kind: "iptv" }
  | { kind: ConfirmKind };

/** Data ONU yang dibutuhkan modal — subset detail halaman, bukan tipe penuh, supaya kontrak
 *  halaman tidak ikut berubah tiap field baru datang. */
export type ModalOnu = {
  id: number;
  serial_number: string;
  onu_type_id: number | null;
  external_id: string | null;
  olt_id: number;
  olt_name: string;
  slot: number;
  port: number;
  onu_mode: string | null;
  wan_mode: string | null;
  /** VLAN WAN nyata perangkat (kolom `wan_vlan`), bukan diambil dari daftar VLAN terpasang. */
  wan_vlan?: number | null;
  pppoe_username?: string | null;
  /** Hanya dikirim backend untuk role manager; undefined/null = tidak boleh/tidak ada. */
  pppoe_password?: string | null;
  mgmt_ip_mode: string | null;
  ip_address: string | null;
  download_profile_name: string | null;
  upload_profile_name: string | null;
  download_speed_profile_id: number | null;
  upload_speed_profile_id: number | null;
  zone_id: number | null;
  splitter_id: number | null;
  splitter_port: number | null;
  name: string | null;
  customer_name: string | null;
  address: string | null;
  contact: string | null;
  latitude: number | null;
  longitude: number | null;
  attached_vlans: number[];
  /** Konfigurasi port terakhir ditulis Nexfiber (lihat OnuDetail.port_configs);
   *  diteruskan apa adanya ke modal Eth/WiFi sebagai `current`. */
  port_configs?: OnuDetail["port_configs"];
};

export function OnuActionModals(
  { state, onu, onClose, onDone }:
  {
    state: OnuModalState | null;
    onu: ModalOnu;
    onClose: () => void;
    /** Dipanggil setelah aksi sukses — halaman memakai ini untuk pesan status. */
    onDone?: (kind: string, r: ActionResult | null) => void;
  },
) {
  const { options, run, location, support } = useOnuAction(onu.id);
  const [err, setErr] = useState<string | null>(null);
  /** Job yang baru dibuat dari kind job — modal tidak ditutup sampai pengguna
   *  menutup dialog status job ini, supaya sukses/gagal job benar-benar terlihat
   *  (sebelumnya modal menutup saat job dibuat dan hasilnya tidak terlihat). */
  const [job, setJob] = useState<{ kind: string; r: ActionResult } | null>(null);
  if (state === null) return null;

  const close = () => { setErr(null); setJob(null); onClose(); };
  const fail = (e: unknown) =>
    setErr(e instanceof ApiError || e instanceof Error ? e.message : "Aksi gagal");

  const act = (kind: ActionKind, body?: Record<string, unknown>) => {
    setErr(null);
    run.mutate({ kind, body }, {
      onSuccess: (r) => {
        // ok:false = HTTP 200 dengan hasil gagal (OLT menolak perintah): modal
        // TETAP terbuka dengan error menonjol, bukan ditutup sebagai sukses.
        if (!r.ok) { setErr(r.detail ?? "OLT menolak perintah"); return; }
        // Kind job: tampilkan status job dulu, onDone baru dipanggil saat dialog
        // status ditutup (termasuk untuk delete, supaya navigasi tidak terjadi
        // sebelum pengguna melihat hasil job).
        if (r.job_id != null) { setJob({ kind, r }); return; }
        onDone?.(kind, r); close();
      },
      onError: fail,
    });
  };
  const saveLocation = (body: LocationBody) => {
    setErr(null);
    location.mutate(body, {
      onSuccess: () => { onDone?.("location", null); close(); },
      onError: fail,
    });
  };

  const sup = (kind: ActionKind) => support(kind)?.supported ?? null;
  const note = (kind: ActionKind) => support(kind)?.note ?? null;
  const common = (kind: ActionKind) => ({
    supported: sup(kind), note: note(kind), busy: run.isPending, error: err, onClose: close,
  });

  if (job !== null) {
    return (
      <ModalShell title={`Job ${job.kind} #${job.r.job_id}`}
                  onClose={() => { onDone?.(job.kind, job.r); close(); }}
                  closeLabel="Tutup">
        <p className="text-xs text-muted">{job.r.detail ?? `Job ${job.kind} dibuat.`}</p>
        <JobTrace jobId={job.r.job_id ?? null} />
      </ModalShell>
    );
  }

  switch (state.kind) {
    case "attached-vlans":
      return (
        <AttachedVlansModal {...common("attached-vlans")} options={options.data}
          current={onu.attached_vlans}
          onSubmit={(vlans) => act("attached-vlans", { vlans })} />
      );
    case "onu-mode":
      // 501 adalah pengaman yang benar, bukan bug — tapi form yang bisa diisi
      // penuh lalu tidak bisa disimpan itu menyesatkan. Bila backend sudah
      // menyatakan kind ini tidak didukung, tampilkan dialog "Segera" saja
      // (tanpa form), bukan form yang submit-nya mati.
      if (sup("onu-mode") === false) {
        return (
          <ModalShell title="Mode ONU — Segera" onClose={close} closeLabel="Tutup">
            <p className="text-sm text-muted">{note("onu-mode") ?? "Fitur ini belum tersedia."}</p>
          </ModalShell>
        );
      }
      return (
        <OnuModeModal {...common("onu-mode")} options={options.data}
          current={{
            wan_vlan: onu.wan_vlan ?? null,
            attached_vlans: onu.attached_vlans,
            onu_mode: onu.onu_mode,
            wan_mode: onu.wan_mode,
            pppoe_username: onu.pppoe_username,
            pppoe_password: onu.pppoe_password,
          }}
          onSubmit={(body) => act("onu-mode", { ...body })} />
      );
    case "location":
      return (
        <LocationModal options={options.data} busy={location.isPending} error={err} onClose={close}
          current={{
            zone_id: onu.zone_id, splitter_id: onu.splitter_id, splitter_port: onu.splitter_port,
            customer_name: onu.customer_name,
            address: onu.address, contact: onu.contact,
            latitude: onu.latitude, longitude: onu.longitude,
          }}
          onSubmit={saveLocation} />
      );
    case "eth-port":
      return (
        <EthPortModal {...common("eth-port")} options={options.data}
          port={state.port} link={state.link}
          current={onu.port_configs?.eth?.[String(state.port)] ?? undefined}
          onSubmit={(body) => act("eth-port", { ...body })} />
      );
    case "wifi-port":
      return (
        <WifiPortModal {...common("wifi-port")} options={options.data} port={state.port}
          current={onu.port_configs?.wifi?.[String(state.port)] ?? undefined}
          clearSupported={sup("wifi-clear")}
          onClear={(port) => act("wifi-clear", { port })}
          onSubmit={(body) => act("wifi-port", { ...body })} />
      );
    case "onu-type":
      return (
        <OnuTypeModal {...common("onu-type")} options={options.data} current={onu.onu_type_id}
          onSubmit={(body) => act("onu-type", { ...body })} />
      );
    case "external-id":
      return (
        <ExternalIdModal {...common("external-id")} current={onu.external_id}
          onSubmit={(body) => act("external-id", { ...body })} />
      );
    case "speed-profile":
      return (
        <SpeedProfileModal {...common("speed-profile")} options={options.data}
          current={{ download: onu.download_speed_profile_id, upload: onu.upload_speed_profile_id }}
          currentName={{ download: onu.download_profile_name, upload: onu.upload_profile_name }}
          onSubmit={(body) => act("speed-profile", { ...body })} />
      );
    case "replace-sn":
      return (
        <ReplaceSnModal {...common("replace-sn")} currentSn={onu.serial_number}
          onSubmit={(body) => act("replace-sn", { ...body })} />
      );
    case "mgmt-ip":
      return (
        <MgmtIpModal {...common("mgmt-ip")}
          current={{ mode: onu.mgmt_ip_mode, ip: onu.ip_address }}
          onSubmit={(body) => act("mgmt-ip", { ...body })} />
      );
    case "voip-enable":
      return (
        <VoipEnableModal {...common("voip-enable")} port={state.port}
          onSubmit={(body) => act("voip-enable", { ...body })} />
      );
    case "voip-disable":
      return (
        <ModalShell title="Nonaktifkan VoIP" action="Ya, matikan" danger {...common("voip-disable")}
          onSubmit={() => act("voip-disable", { port: state.port })}>
          <p className="text-sm text-down">Layanan VoIP pada port ini dimatikan.</p>
        </ModalShell>
      );
    case "move":
      return (
        <MoveModal {...common("move")} oltId={onu.olt_id}
          currentSlot={onu.slot} currentPort={onu.port}
          onSubmit={(body) => act("move", { ...body })} />
      );
    case "iptv":
      if (sup("iptv") === false) {
        return (
          <ModalShell title="IPTV — Segera" onClose={close} closeLabel="Tutup">
            <p className="text-sm text-muted">{note("iptv") ?? "Fitur ini belum tersedia."}</p>
          </ModalShell>
        );
      }
      return (
        <IptvModal {...common("iptv")} current={false}
          onSubmit={(body) => act("iptv", { ...body })} />
      );
    default:
      return (
        <ConfirmActionModal kind={state.kind} serial={onu.serial_number}
          {...common(state.kind)} onConfirm={(kind) => act(kind)} />
      );
  }
}
