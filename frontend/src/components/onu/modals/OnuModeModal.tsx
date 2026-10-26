/** Update ONU mode — acuan `updateMode`.
 *
 *  Field kondisional sama seperti acuan:
 *  - `Bridging` tidak punya WAN mode/IP/PPPoE (seluruh blok routing disembunyikan);
 *  - `Setup via ONU webpage` tidak punya sumber IP maupun PPPoE;
 *  - `Static IP` memunculkan sumber IP (pool/manual) + alamat IP;
 *  - `PPPoE` memunculkan username + password (tombol mata) saja.
 *  Kata sandi hanya di state lokal modal ini dan hilang saat modal ditutup.
 */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { Help, ModalShell, PasswordInput, Radios, Row, Select, field } from "./ModalShell";

export type OnuModeBody = {
  wan_vlan: number | null;
  onu_mode: "routing" | "bridging";
  wan_mode: "webpage" | "dhcp" | "static" | "pppoe";
  config_method: "omci" | "tr069";
  wan_ip_source: "pool" | "manual" | null;
  wan_ip: string | null;
  pppoe_username: string | null;
  pppoe_password: string | null;
  wan_remote_access: string;
};

const WAN_MODES = [
  { value: "webpage", label: "Setup via ONU webpage" },
  { value: "dhcp", label: "DHCP" },
  { value: "static", label: "Static IP" },
  { value: "pppoe", label: "PPPoE" },
] as const;

const REMOTE = [
  { value: "disabled", label: "Mati / tidak diatur" },
  { value: "acl", label: "Hanya dari IP di Remote ACL" },
  { value: "any", label: "Dari mana saja di internet" },
];

export function OnuModeModal(
  { options, current, supported, note, busy, error, onClose, onSubmit }:
  {
    options: OnuConfigOptions | undefined;
    current: { wan_vlan: number | null; onu_mode: string | null; wan_mode: string | null; pppoe_username?: string | null };
    supported: boolean | null;
    note?: string | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (body: OnuModeBody) => void;
  },
) {
  const [wanVlan, setWanVlan] = useState(current.wan_vlan === null ? "" : String(current.wan_vlan));
  const [mode, setMode] = useState<"routing" | "bridging">(
    (current.onu_mode ?? "").toLowerCase() === "bridging" ? "bridging" : "routing",
  );
  const [wanMode, setWanMode] = useState<OnuModeBody["wan_mode"]>(() => {
    const v = (current.wan_mode ?? "").toLowerCase();
    return WAN_MODES.some((m) => m.value === v) ? (v as OnuModeBody["wan_mode"]) : "webpage";
  });
  const [cfg, setCfg] = useState<"omci" | "tr069">("omci");
  const [ipSource, setIpSource] = useState<"pool" | "manual">("pool");
  const [ip, setIp] = useState("");
  const [user, setUser] = useState(current.pppoe_username ?? "");
  const [pass, setPass] = useState("");
  const [remote, setRemote] = useState("disabled");

  const routing = mode === "routing";
  const isStatic = routing && wanMode === "static";
  const isPppoe = routing && wanMode === "pppoe";
  /** `wan_modes` dari backend = mode yang didukung perangkat; kosong = semua ditawarkan. */
  const allowed = options?.wan_modes ?? [];
  const text = (v: string) => (v.trim() === "" ? null : v.trim());

  return (
    <ModalShell title="Update ONU mode" action="Update" supported={supported} note={note}
                busy={busy} error={error} onClose={onClose}
                onSubmit={() => onSubmit({
                  wan_vlan: wanVlan === "" ? null : Number(wanVlan),
                  onu_mode: mode,
                  wan_mode: routing ? wanMode : "webpage",
                  config_method: cfg,
                  wan_ip_source: isStatic ? ipSource : null,
                  wan_ip: isStatic && ipSource === "manual" ? text(ip) : null,
                  pppoe_username: isPppoe ? text(user) : null,
                  pppoe_password: isPppoe ? text(pass) : null,
                  wan_remote_access: remote,
                })}>
      <Row label="WAN VLAN-ID"
           hint={<Help warn>
             Setelah WAN VLAN-ID diubah, periksa setelan port Ethernet dan perbarui VLAN sesuai kebutuhan.
           </Help>}>
        <Select value={wanVlan} onChange={setWanVlan} placeholder="Tanpa VLAN" label="WAN VLAN-ID">
          {serviceVlanOptions(options).map((v) => (
            <option key={v.number} value={v.number}>{v.number} - {v.name}</option>
          ))}
        </Select>
      </Row>
      <Row label="ONU mode">
        <Radios name="onu-mode" value={mode} onChange={setMode}
                options={[{ value: "routing", label: "Routing" }, { value: "bridging", label: "Bridging" }]} />
      </Row>
      {routing && (
        <>
          <Row label="WAN mode">
            <Radios name="wan-mode" value={wanMode} onChange={setWanMode}
                    options={WAN_MODES.map((m) => ({
                      value: m.value,
                      label: m.label,
                      disabled: allowed.length > 0 && !allowed.includes(m.value),
                    }))} />
          </Row>
          <Row label="Config method">
            <Radios name="config-method" value={cfg} onChange={setCfg}
                    options={[
                      { value: "omci", label: "OMCI" },
                      { value: "tr069", label: "TR069", disabled: true },
                    ]} />
          </Row>
          {isStatic && (
            <>
              <Row label="WAN IP source">
                <Radios name="wan-ip-source" value={ipSource} onChange={setIpSource}
                        options={[{ value: "pool", label: "From IP pool" }, { value: "manual", label: "Manual IP" }]} />
              </Row>
              {ipSource === "manual" && (
                <Row label="WAN IP address">
                  <input className={field} value={ip} inputMode="numeric" autoComplete="off"
                         aria-label="WAN IP address" placeholder="10.0.0.2"
                         onChange={(e) => setIp(e.target.value.trim())} />
                </Row>
              )}
            </>
          )}
          {isPppoe && (
            <>
              <Row label="Username">
                <input className={field} value={user} autoComplete="off" aria-label="PPPoE username"
                       onChange={(e) => setUser(e.target.value.trim())} />
              </Row>
              <Row label="Password">
                <PasswordInput label="PPPoE password" value={pass} onChange={setPass} />
              </Row>
            </>
          )}
          <Row label="WAN remote access">
            <Select value={remote} onChange={setRemote} label="WAN remote access">
              {REMOTE.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </Select>
          </Row>
        </>
      )}
    </ModalShell>
  );
}
