/** Configure ethernet port eth_0/N — acuan `configureNetworkPort`.
 *  `Allowed VLANs` hanya untuk mode Trunk/Hybrid (persis acuan). */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { ModalShell, Radios, Row, Select, VlanMulti } from "./ModalShell";

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
  { port, link, options, supported, note, busy, error, onClose, onSubmit }:
  {
    port: number;
    link?: string | null;
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

  return (
    <ModalShell title={`Configure ethernet port eth_0/${port}`} action="Save" wide
                supported={supported} note={note} busy={busy} error={error} onClose={onClose}
                onSubmit={() => onSubmit({
                  port, enabled: enabled === "on", mode,
                  vlan_id: vlan === "" ? null : Number(vlan),
                  allowed_vlans: showAllowed ? allowed : [],
                  dhcp,
                })}>
      <Row label="Link">
        <span className="font-mono text-sm text-muted">{link ?? "—"}</span>
      </Row>
      <Row label="Status">
        <Radios name={`eth-${port}-status`} value={enabled} onChange={setEnabled}
                options={[{ value: "on", label: "Enabled" }, { value: "off", label: "Port shutdown" }]} />
      </Row>
      {/* Acuan memakai radio sebaris untuk 5 mode (bukan select). */}
      <Row label="Mode">
        <Radios name={`eth-${port}-mode`} value={mode} onChange={setMode} options={MODES} />
      </Row>
      <Row label="VLAN-ID">
        <Select value={vlan} onChange={setVlan} placeholder="Tanpa VLAN" label="VLAN-ID">
          {vlanList.map((v) => <option key={v.number} value={v.number}>{v.number} - {v.name}</option>)}
        </Select>
      </Row>
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
