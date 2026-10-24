/** Update Management and VoIP IP, Enable/Disable VoIP, Update IPTV.
 *
 *  Body `mgmt-ip` {mode,vlan,ip} dan `iptv` {enabled} persis kontrak. Kontrak tidak mengunci
 *  body `voip-enable`, jadi field acuan (port, nomor, sandi) dikirim apa adanya dan backend
 *  boleh mengabaikan yang belum dipakai — tidak ada field karangan di luar acuan SmartOLT.
 */
import { useState } from "react";
import type { OnuConfigOptions } from "../../../lib/onuActions";
import { ModalShell, PasswordInput, Radios, Row, Select, field } from "./ModalShell";

type Common = {
  supported: boolean | null;
  note?: string | null;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
};

export function MgmtIpModal(
  { options, current, onSubmit, ...c }:
  Common & {
    options: OnuConfigOptions | undefined;
    current: { mode: string | null; vlan: number | null; ip: string | null };
    onSubmit: (body: { mode: string; vlan: number | null; ip: string | null }) => void;
  },
) {
  const [mode, setMode] = useState<"inactive" | "static" | "dhcp">(() => {
    const v = (current.mode ?? "").toLowerCase();
    return v === "static" || v === "dhcp" ? v : "inactive";
  });
  const [vlan, setVlan] = useState(current.vlan === null ? "" : String(current.vlan));
  const [ip, setIp] = useState(current.ip ?? "");
  return (
    <ModalShell title="Update Management and VoIP IP" action="Update" {...c}
                onSubmit={() => onSubmit({
                  mode,
                  vlan: mode === "inactive" || vlan === "" ? null : Number(vlan),
                  ip: mode === "static" && ip.trim() !== "" ? ip.trim() : null,
                })}>
      <Row label="Mgmt IP mode">
        <Radios name="mgmt-mode" value={mode} onChange={setMode}
                options={[
                  { value: "inactive", label: "Inactive" },
                  { value: "static", label: "Static IP" },
                  { value: "dhcp", label: "DHCP" },
                ]} />
      </Row>
      {mode !== "inactive" && (
        <Row label="Mgmt VLAN-ID">
          <Select value={vlan} onChange={setVlan} placeholder="Tanpa VLAN" label="Mgmt VLAN-ID">
            {(options?.vlans ?? []).map((v) => (
              <option key={v.number} value={v.number}>{v.number} - {v.name}</option>
            ))}
          </Select>
        </Row>
      )}
      {mode === "static" && (
        <Row label="Management IP address">
          <input className={field} value={ip} autoComplete="off" aria-label="Management IP address"
                 onChange={(e) => setIp(e.target.value.trim())} />
        </Row>
      )}
    </ModalShell>
  );
}

export function VoipEnableModal(
  { port, onSubmit, ...c }:
  Common & {
    port: number;
    onSubmit: (body: { port: number; phone_number: string | null; password: string | null }) => void;
  },
) {
  const [phone, setPhone] = useState("");
  const [pass, setPass] = useState("");
  const text = (v: string) => (v.trim() === "" ? null : v.trim());
  return (
    <ModalShell title="Enable VoIP" action="Aktifkan" {...c}
                onSubmit={() => onSubmit({ port, phone_number: text(phone), password: text(pass) })}>
      <Row label="Port">
        <span className="font-mono text-xs text-muted">pots_0/{port}</span>
      </Row>
      <Row label="Phone number">
        <input className={field} value={phone} autoComplete="off" aria-label="Phone number"
               onChange={(e) => setPhone(e.target.value.trim())} />
      </Row>
      <Row label="Password">
        <PasswordInput label="Password VoIP" value={pass} onChange={setPass} />
      </Row>
    </ModalShell>
  );
}

export function IptvModal(
  { current, onSubmit, ...c }:
  Common & { current: boolean; onSubmit: (body: { enabled: boolean }) => void },
) {
  const [on, setOn] = useState<"on" | "off">(current ? "on" : "off");
  return (
    <ModalShell title="Update IPTV" action="Update" {...c}
                onSubmit={() => onSubmit({ enabled: on === "on" })}>
      <Row label="IPTV status">
        <Radios name="iptv-status" value={on} onChange={setOn}
                options={[{ value: "off", label: "Inactive" }, { value: "on", label: "Active" }]} />
      </Row>
    </ModalShell>
  );
}
