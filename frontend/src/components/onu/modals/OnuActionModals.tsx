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
import { ApiError } from "../../../lib/api";
import {
  useOnuAction, type ActionKind, type ActionResult, type LocationBody,
} from "../../../lib/onuActions";
import { AttachedVlansModal } from "./AttachedVlansModal";
import {
  ExternalIdModal, MoveOnuModal, OnuTypeModal, ReplaceSnModal, SpeedProfileModal,
} from "./BasicModals";
import { ConfirmActionModal, type ConfirmKind } from "./ConfirmActionModal";
import { EthPortModal } from "./EthPortModal";
import { LocationModal } from "./LocationModal";
import { ModalShell } from "./ModalShell";
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
  | { kind: "move" }
  | { kind: "replace-sn" }
  | { kind: "mgmt-ip" }
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
  mgmt_ip_mode: string | null;
  vlan_id: number | null;
  ip_address: string | null;
  download_profile_name: string | null;
  upload_profile_name: string | null;
  zone_id: number | null;
  splitter_id: number | null;
  splitter_port: number | null;
  sector_id?: number | null;
  name: string | null;
  customer_name: string | null;
  address: string | null;
  contact: string | null;
  latitude: number | null;
  longitude: number | null;
  attached_vlans: number[];
};

export function OnuActionModals(
  { state, onu, olts, onClose, onDone }:
  {
    state: OnuModalState | null;
    onu: ModalOnu;
    /** Pilihan OLT untuk Move ONU; default hanya OLT saat ini. */
    olts?: { id: number; name: string }[];
    onClose: () => void;
    /** Dipanggil setelah aksi sukses — halaman memakai ini untuk pesan status. */
    onDone?: (kind: string, r: ActionResult | null) => void;
  },
) {
  const { options, run, location, support } = useOnuAction(onu.id);
  const [err, setErr] = useState<string | null>(null);
  if (state === null) return null;

  const close = () => { setErr(null); onClose(); };
  const fail = (e: unknown) =>
    setErr(e instanceof ApiError || e instanceof Error ? e.message : "Aksi gagal");

  const act = (kind: ActionKind, body?: Record<string, unknown>) => {
    setErr(null);
    run.mutate({ kind, body }, {
      onSuccess: (r) => { onDone?.(kind, r); close(); },
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

  switch (state.kind) {
    case "attached-vlans":
      return (
        <AttachedVlansModal {...common("attached-vlans")} options={options.data}
          current={onu.attached_vlans}
          onSubmit={(vlans) => act("attached-vlans", { vlans })} />
      );
    case "onu-mode":
      return (
        <OnuModeModal {...common("onu-mode")} options={options.data}
          current={{
            wan_vlan: onu.attached_vlans[0] ?? null,
            onu_mode: onu.onu_mode,
            wan_mode: onu.wan_mode,
            pppoe_username: onu.pppoe_username,
          }}
          onSubmit={(body) => act("onu-mode", { ...body })} />
      );
    case "location":
      return (
        <LocationModal options={options.data} busy={location.isPending} error={err} onClose={close}
          current={{
            zone_id: onu.zone_id, splitter_id: onu.splitter_id, splitter_port: onu.splitter_port,
            sector_id: onu.sector_id ?? null, name: onu.customer_name ?? onu.name,
            address: onu.address, contact: onu.contact,
            latitude: onu.latitude, longitude: onu.longitude,
          }}
          onSubmit={saveLocation} />
      );
    case "eth-port":
      return (
        <EthPortModal {...common("eth-port")} options={options.data}
          port={state.port} link={state.link}
          onSubmit={(body) => act("eth-port", { ...body })} />
      );
    case "wifi-port":
      return (
        <WifiPortModal {...common("wifi-port")} options={options.data} port={state.port}
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
          current={{ download: onu.download_profile_name, upload: onu.upload_profile_name }}
          onSubmit={(body) => act("speed-profile", { ...body })} />
      );
    case "move":
      return (
        <MoveOnuModal {...common("move")}
          olts={olts ?? [{ id: onu.olt_id, name: onu.olt_name }]}
          current={{ olt_id: onu.olt_id, board: onu.slot, port: onu.port }}
          onSubmit={(body) => act("move", { ...body })} />
      );
    case "replace-sn":
      return (
        <ReplaceSnModal {...common("replace-sn")} currentSn={onu.serial_number}
          onSubmit={(body) => act("replace-sn", { ...body })} />
      );
    case "mgmt-ip":
      return (
        <MgmtIpModal {...common("mgmt-ip")} options={options.data}
          current={{ mode: onu.mgmt_ip_mode, vlan: onu.vlan_id, ip: onu.ip_address }}
          onSubmit={(body) => act("mgmt-ip", { ...body })} />
      );
    case "voip-enable":
      return (
        <VoipEnableModal {...common("voip-enable")} port={state.port}
          onSubmit={(body) => act("voip-enable", { ...body })} />
      );
    case "voip-disable":
      return (
        <ModalShell title="Disable VoIP" action="Ya, matikan" danger {...common("voip-disable")}
          onSubmit={() => act("voip-disable", { port: state.port })}>
          <p className="text-sm text-down">Layanan VoIP pada port ini dimatikan.</p>
        </ModalShell>
      );
    case "iptv":
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
