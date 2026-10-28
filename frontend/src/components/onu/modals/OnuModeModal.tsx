/** Update ONU mode — acuan `updateMode`.
 *
 *  Field kondisional sama seperti acuan:
 *  - `Bridging` tidak punya WAN mode/IP/PPPoE (seluruh blok routing disembunyikan);
 *  - `Setup via ONU webpage` tidak punya sumber IP maupun PPPoE;
 *  - `Static IP` memunculkan sumber IP (pool/manual) + alamat IP;
 *  - `PPPoE` memunculkan username + password (tombol mata) saja.
 *  Username/password PPPoE terisi dari data ONU hasil sinkron running-config (password
 *  plaintext hanya dikirim backend ke role manager); keduanya tetap hanya di state lokal
 *  modal ini dan hilang saat modal ditutup.
 */
import { useState } from "react";
import { type OnuConfigOptions } from "../../../lib/onuActions";
import { wanVlanChoices } from "../../../lib/wanVlan";
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
    current: {
      /** VLAN WAN nyata perangkat (`onus.wan_vlan`). */
      wan_vlan: number | null;
      /** VLAN yang DICENTANG di "Update attached VLANs" = satu-satunya pilihan WAN VLAN. */
      attached_vlans: number[];
      onu_mode: string | null;
      wan_mode: string | null;
      pppoe_username?: string | null;
      /** Plaintext dari backend (manager saja); diisi ke field supaya bisa dilihat/diubah. */
      pppoe_password?: string | null;
      /** Field ini saat ini TIDAK dikirim backend — bila suatu saat dikirim,
       *  nilai awalnya dipakai, bukan di-reset ke default di bawah. */
      config_method?: string | null;
      wan_ip_source?: string | null;
      wan_ip?: string | null;
      wan_remote_access?: string | null;
    };
    supported: boolean | null;
    note?: string | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (body: OnuModeBody) => void;
  },
) {
  const init = {
    wanVlan: current.wan_vlan === null ? "" : String(current.wan_vlan),
    mode: (current.onu_mode ?? "").toLowerCase() === "bridging" ? "bridging" : "routing",
    wanMode: (() => {
      const v = (current.wan_mode ?? "").toLowerCase();
      return WAN_MODES.some((m) => m.value === v) ? (v as OnuModeBody["wan_mode"]) : "webpage";
    })(),
    // Jangan reset ke default bila nilai awal sudah ada di state/prop.
    cfg: (current.config_method ?? "").toLowerCase() === "tr069" ? "tr069" : "omci",
    ipSource: (current.wan_ip_source ?? "").toLowerCase() === "manual" ? "manual" : "pool",
    ip: current.wan_ip ?? "",
    user: current.pppoe_username ?? "",
    pass: current.pppoe_password ?? "",
    remote: (() => {
      const v = (current.wan_remote_access ?? "").toLowerCase();
      return REMOTE.some((r) => r.value === v) ? v : "disabled";
    })(),
  } as const;
  const [wanVlan, setWanVlan] = useState(init.wanVlan);
  const [mode, setMode] = useState<"routing" | "bridging">(init.mode);
  const [wanMode, setWanMode] = useState<OnuModeBody["wan_mode"]>(init.wanMode);
  const [cfg, setCfg] = useState<"omci" | "tr069">(init.cfg);
  const [ipSource, setIpSource] = useState<"pool" | "manual">(init.ipSource);
  const [ip, setIp] = useState(init.ip);
  const [user, setUser] = useState(init.user);
  const [pass, setPass] = useState(init.pass);
  const [remote, setRemote] = useState(init.remote);
  const dirty = wanVlan !== init.wanVlan || mode !== init.mode || wanMode !== init.wanMode
    || cfg !== init.cfg || ipSource !== init.ipSource || ip !== init.ip || user !== init.user
    || pass !== init.pass || remote !== init.remote;
  const unread = current.config_method == null && current.wan_ip_source == null
    && current.wan_ip == null && current.wan_remote_access == null;

  const routing = mode === "routing";
  const isStatic = routing && wanMode === "static";
  const isPppoe = routing && wanMode === "pppoe";
  /** `wan_modes` dari backend = mode yang didukung perangkat; kosong = semua ditawarkan. */
  const allowed = options?.wan_modes ?? [];
  const text = (v: string) => (v.trim() === "" ? null : v.trim());
  /** Pilihan WAN VLAN = HANYA VLAN terpasang ONU + VLAN WAN yang sedang berlaku
   *  (lihat `wanVlanChoices`; diuji di `frontend/tests/onu-mode.check.mjs`). */
  const vlanChoices = wanVlanChoices(options?.vlans, current.attached_vlans, current.wan_vlan);

  return (
    <ModalShell title="Perbarui mode ONU" action="Simpan" supported={supported} note={note}
                busy={busy} error={error} onClose={onClose} dirty={dirty}
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
      <div className="mb-3.5">
        <Help>Konfigurasi saat ini: <span className="font-mono">{init.mode} · {init.wanMode} · WAN VLAN {init.wanVlan === "" ? "—" : init.wanVlan}</span>{unread && ". Config method / sumber IP / akses remote belum dibaca dari perangkat, diisi nilai baru."}</Help>
      </div>
      <Row label="WAN VLAN-ID"
           hint={<Help warn>
             Setelah WAN VLAN-ID diubah, periksa setelan port Ethernet dan perbarui VLAN sesuai kebutuhan.
           </Help>}>
        <Select value={wanVlan} onChange={setWanVlan} placeholder="Tanpa VLAN" label="WAN VLAN-ID" autoFocus>
          {vlanChoices.map((v) => (
            <option key={v.number} value={v.number}>
              {v.name === null ? v.number : `${v.number} - ${v.name}`}
            </option>
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
