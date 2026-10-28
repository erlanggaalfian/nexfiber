/** Configure ethernet port eth_0/N — acuan `configureNetworkPort`.
 *  `Allowed VLANs` hanya untuk mode Trunk/Hybrid (persis acuan). */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { Help, ModalShell, Radios, Row, Select, VlanMulti } from "./ModalShell";

export type EthPortBody = {
  port: number; enabled: boolean; mode: string; vlan_id: number | null;
  allowed_vlans: number[]; dhcp: string;
};

const MODES = [
  { value: "lan", label: "LAN" }, { value: "access", label: "Access" },
  { value: "hybrid", label: "Hybrid" }, { value: "trunk", label: "Trunk" },
  { value: "transparent", label: "Transparent" },
];
const DHCP = [
  { value: "none", label: "No control" }, { value: "isp", label: "From ISP" },
  { value: "onu", label: "From ONU" }, { value: "forbidden", label: "Forbidden" },
];

export function EthPortModal(
  { port, options, supported, note, busy, error, onClose, onSubmit }:
  {
    port: number;
    link?: string | null; // Dipertahankan untuk kompatibilitas pemanggil; tidak ada
    // sumber status link di halaman ini, jadi baris Link dihapus (selalu "—").
    options: OnuConfigOptions | undefined;
    supported: boolean | null;
    note?: string | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (body: EthPortBody) => void;
  },
) {
  const [enabled, setEnabled] = useState<"on" | "off">("on");
  const [mode, setMode] = useState("lan");
  const [vlan, setVlan] = useState("");
  const [allowed, setAllowed] = useState<number[]>([]);
  const [dhcp, setDhcp] = useState("none");
  const vlanList = serviceVlanOptions(options);
  const showAllowed = mode === "trunk" || mode === "hybrid";
  // Mode tag (LAN/Access) dan hybrid wajib VLAN di backend; matikan Save sampai
  // dipilih, supaya submit tidak selalu ditolak backend. Modal ini menulis ulang
  // konfigurasi port dari nilai di bawah (konfigurasi saat ini tidak dibaca dari
  // perangkat), jadi Save mati sampai ada perubahan — klik tanpa sengaja tidak boleh
  // membuka port dan mengubahnya ke tag/LAN. VLAN-ID hanya untuk mode yang
  // memakainya; trunk/transparent mengabaikannya di backend, jadi disembunyikan dan
  // tidak dikirim. Trunk/hybrid dengan allowed kosong juga ditolak backend (tidak
  // ada perintah hapus daftar lama yang terbukti), jadi wajib minimal satu.
  const vlanRequired = mode === "lan" || mode === "access" || mode === "hybrid";
  const usesVlan = vlanRequired;
  const changed = enabled !== "on" || mode !== "lan" || vlan !== "" || allowed.length > 0
    || dhcp !== "none";
  const disabled = !changed || (vlanRequired && vlan === "")
    || (showAllowed && allowed.length === 0);

  return (
    <ModalShell title={`Configure ethernet port eth_0/${port}`} action="Save" wide
                supported={supported} note={note} busy={busy} error={error} onClose={onClose}
                disabled={disabled}
                onSubmit={() => onSubmit({
                  port, enabled: enabled === "on", mode,
                  vlan_id: usesVlan && vlan !== "" ? Number(vlan) : null,
                  allowed_vlans: showAllowed ? allowed : [],
                  dhcp,
                })}>
      <div className="mb-3.5">
        <Help>Modal ini menulis ulang konfigurasi port dari nilai di bawah. Save aktif setelah ada perubahan.</Help>
      </div>
      <Row label="Status">
        <Radios name={`eth-${port}-status`} value={enabled} onChange={setEnabled}
                options={[{ value: "on", label: "Enabled" }, { value: "off", label: "Port shutdown" }]} />
      </Row>
      {/* Acuan memakai radio sebaris untuk 5 mode (bukan select). */}
      <Row label="Mode">
        <Radios name={`eth-${port}-mode`} value={mode} onChange={setMode} options={MODES} />
      </Row>
      {usesVlan && (
        <Row label="VLAN-ID">
          <Select value={vlan} onChange={setVlan} placeholder="Tanpa VLAN" label="VLAN-ID">
            {vlanList.map((v) => <option key={v.number} value={v.number}>{v.number} - {v.name}</option>)}
          </Select>
        </Row>
      )}
      {showAllowed && (
        <Row label="Allowed VLANs list">
          <VlanMulti label="Allowed VLANs list" options={vlanList} value={allowed} onChange={setAllowed} />
        </Row>
      )}
      <Row label="DHCP">
        <Select value={dhcp} onChange={setDhcp} label="DHCP">
          {DHCP.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </Select>
      </Row>
    </ModalShell>
  );
}
