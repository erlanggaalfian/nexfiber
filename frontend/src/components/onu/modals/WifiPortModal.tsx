/** Configure WiFi port wifi_0/N — acuan `configureWifiPort`.
 *  Encryption AES tetap (satu-satunya nilai pada acuan), password lewat tombol mata dan
 *  hanya di state lokal, "Clear WiFi port settings" memakai kind `wifi-clear`. */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { ModalShell, PasswordInput, Radios, Row, Select, VlanMulti, field } from "./ModalShell";
import { Button } from "../../ui/button";

export type WifiPortBody = {
  port: number; enabled: boolean; mode: string; vlan_id: number | null;
  allowed_vlans: number[]; ssid: string | null; auth_mode: string;
  password: string | null; dhcp: string;
};

const MODES = [
  { value: "lan", label: "LAN" }, { value: "access", label: "Access" },
  { value: "hybrid", label: "Hybrid" }, { value: "trunk", label: "Trunk" },
];
const AUTH = [
  { value: "wpa2", label: "WPA2" }, { value: "auto", label: "Auto" }, { value: "open", label: "Open" },
];
const DHCP = [
  { value: "none", label: "No control" }, { value: "isp", label: "From ISP" },
  { value: "onu", label: "From ONU" }, { value: "forbidden", label: "Forbidden" },
];

export function WifiPortModal(
  { port, options, supported, note, clearSupported, busy, error, onClose, onSubmit, onClear }:
  {
    port: number;
    options: OnuConfigOptions | undefined;
    supported: boolean | null;
    note?: string | null;
    clearSupported: boolean | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (body: WifiPortBody) => void;
    onClear: (port: number) => void;
  },
) {
  const [enabled, setEnabled] = useState<"on" | "off">("on");
  const [mode, setMode] = useState("lan");
  const [vlan, setVlan] = useState("");
  const [allowed, setAllowed] = useState<number[]>([]);
  const [ssid, setSsid] = useState("");
  const [auth, setAuth] = useState("wpa2");
  const [pass, setPass] = useState("");
  const [dhcp, setDhcp] = useState("none");
  const vlanList = serviceVlanOptions(options);
  const showAllowed = mode === "trunk" || mode === "hybrid";
  const text = (v: string) => (v.trim() === "" ? null : v.trim());

  return (
    <ModalShell title={`Configure WiFi port wifi_0/${port}`} action="Simpan"
                supported={supported} note={note} busy={busy} error={error} onClose={onClose}
                extra={
                  <Button size="sm" variant="danger" disabled={clearSupported === false}
                          onClick={() => onClear(port)}>
                    Bersihkan setelan WiFi
                  </Button>
                }
                onSubmit={() => onSubmit({
                  port, enabled: enabled === "on", mode,
                  vlan_id: vlan === "" ? null : Number(vlan),
                  allowed_vlans: showAllowed ? allowed : [],
                  ssid: text(ssid), auth_mode: auth,
                  password: auth === "open" ? null : text(pass),
                  dhcp,
                })}>
      <Row label="Status">
        <Radios name={`wifi-${port}-status`} value={enabled} onChange={setEnabled}
                options={[{ value: "on", label: "Enabled" }, { value: "off", label: "Port shutdown" }]} />
      </Row>
      <Row label="Mode">
        <Select value={mode} onChange={setMode} label="Mode">
          {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </Select>
      </Row>
      <Row label="VLAN-ID">
        <Select value={vlan} onChange={setVlan} placeholder="Tanpa VLAN" label="VLAN-ID">
          {vlanList.map((v) => <option key={v.number} value={v.number}>{v.number} - {v.name}</option>)}
        </Select>
      </Row>
      {showAllowed && (
        <Row label="Allowed VLANs">
          <VlanMulti label="Allowed VLANs" options={vlanList} value={allowed} onChange={setAllowed} />
        </Row>
      )}
      <Row label="SSID">
        <input className={field} value={ssid} aria-label="SSID" autoComplete="off"
               onChange={(e) => setSsid(e.target.value)} />
      </Row>
      <Row label="Auth mode">
        <Select value={auth} onChange={setAuth} label="Auth mode">
          {AUTH.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </Select>
      </Row>
      {auth !== "open" && (
        <>
          <Row label="Encryption">
            <span className="font-mono text-xs text-muted">AES</span>
          </Row>
          <Row label="Password" hint="Kosongkan bila tidak diganti.">
            <PasswordInput label="Password WiFi" value={pass} onChange={setPass} />
          </Row>
        </>
      )}
      <Row label="DHCP">
        <Select value={dhcp} onChange={setDhcp} label="DHCP">
          {DHCP.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </Select>
      </Row>
    </ModalShell>
  );
}
