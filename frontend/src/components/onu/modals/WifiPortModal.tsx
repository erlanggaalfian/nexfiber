/** Configure WiFi port wifi_0/N — acuan `configureWifiPort`.
 *  Encryption AES tetap (satu-satunya nilai pada acuan), password lewat tombol mata dan
 *  hanya di state lokal, "Clear WiFi port settings" memakai kind `wifi-clear`.
 *  Tidak ada field DHCP: tidak ada sintaks DHCP WiFi yang terbukti di repo, jadi field
 *  itu hanya akan dibuang diam-diam oleh backend kalau tetap ditampilkan. */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { Help, ModalShell, PasswordInput, Radios, Row, Select, VlanMulti, field } from "./ModalShell";
import { Button } from "../../ui/button";

export type WifiPortBody = {
  port: number; enabled: boolean; mode: string; vlan_id: number | null;
  allowed_vlans: number[]; ssid: string | null; auth_mode: string;
  password: string | null;
};

const MODES = [
  { value: "lan", label: "LAN" }, { value: "access", label: "Access" },
  { value: "hybrid", label: "Hybrid" }, { value: "trunk", label: "Trunk" },
];
const AUTH = [
  { value: "wpa2", label: "WPA2" }, { value: "auto", label: "Auto" }, { value: "open", label: "Open" },
];

/** Lihat EthPortCurrent: backend saat ini tidak mengirim konfigurasi port,
 *  jadi `current` opsional dan ringkasan "belum dibaca" dipakai bila tidak ada.
 *  Sandi tidak pernah di-prefill (tidak tersimpan di Nexfiber). */
export type WifiPortCurrent = {
  enabled?: boolean; mode?: string | null; vlan_id?: number | null;
  allowed_vlans?: number[]; ssid?: string | null; auth_mode?: string;
};

export function WifiPortModal(
  { port, options, current, supported, note, clearSupported, busy, error, onClose, onSubmit, onClear }:
  {
    port: number;
    options: OnuConfigOptions | undefined;
    current?: WifiPortCurrent;
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
  const init = {
    enabled: current?.enabled ?? true,
    mode: current?.mode ?? "lan",
    vlan: current?.vlan_id != null ? String(current.vlan_id) : "",
    allowed: [...(current?.allowed_vlans ?? [])].sort((a, b) => a - b),
    ssid: current?.ssid ?? "",
    auth: current?.auth_mode ?? "wpa2",
  };
  const [enabled, setEnabled] = useState<"on" | "off">(init.enabled ? "on" : "off");
  const [mode, setMode] = useState(init.mode);
  const [vlan, setVlan] = useState(init.vlan);
  const [allowed, setAllowed] = useState<number[]>(init.allowed);
  const [ssid, setSsid] = useState(init.ssid);
  const [auth, setAuth] = useState(init.auth);
  const [pass, setPass] = useState("");
  // Konfirmasi dua klik untuk Clear (tanpa modal baru): klik pertama meminta
  // konfirmasi, klik kedua menjalankan. Tombol juga mati saat aksi lain berjalan.
  const [confirmClear, setConfirmClear] = useState(false);
  const vlanList = serviceVlanOptions(options);
  const showAllowed = mode === "trunk" || mode === "hybrid";
  const text = (v: string) => (v.trim() === "" ? null : v.trim());
  // Sama seperti Eth: mode tag/hybrid wajib VLAN, dan password wajib untuk WPA2/Auto
  // (backend menolak password kosong — tidak ada "pertahankan sandi lama" karena sandi
  // lama tidak tersimpan di Nexfiber). Modal ini juga menulis ulang konfigurasi port
  // dari nilai di bawah, bukan hanya field yang diubah, jadi Save mati sampai ada
  // perubahan. Validasi disamakan dengan backend: SSID 1-32 karakter tanpa " dan ?,
  // sandi 8-63 tanpa spasi dan ?. SSID kosong = SSID lama dipertahankan (builder hanya
  // mengirim perintah SSID bila ada), bukan dihapus — jadi jangan diklaim berubah.
  const vlanRequired = mode === "lan" || mode === "access" || mode === "hybrid";
  const ssidBad = ssid !== "" && (ssid.length > 32 || /["?]/.test(ssid) || /\s/.test(ssid.replace(/ /g, "")));
  const passBad = auth !== "open" && pass !== ""
    && (pass.length < 8 || pass.length > 63 || /\s/.test(pass) || pass.includes("?"));
  const changed = (enabled === "on") !== init.enabled || mode !== init.mode || vlan !== init.vlan
    || allowed.join(",") !== init.allowed.join(",") || ssid !== init.ssid || auth !== init.auth
    || pass !== "";
  const disabled = !changed || ssidBad || passBad
    || (vlanRequired && vlan === "") || (showAllowed && allowed.length === 0)
    || (auth !== "open" && pass.trim() === "");
  const modeLabel = MODES.find((m) => m.value === init.mode)?.label ?? init.mode;

  return (
    <ModalShell title={`Konfigurasi port WiFi wifi_0/${port}`} action="Simpan"
                supported={supported} note={note} busy={busy} error={error} onClose={onClose}
                dirty={changed}
                disabled={disabled}
                extra={
                  <Button size="md" variant="dangerSolid"
                          disabled={clearSupported === false || busy}
                          onClick={() => {
                            if (confirmClear) onClear(port);
                            else setConfirmClear(true);
                          }}>
                    {confirmClear ? "Klik lagi untuk menghapus" : "Hapus setelan WiFi"}
                  </Button>
                }
                onSubmit={() => onSubmit({
                  port, enabled: enabled === "on", mode,
                  vlan_id: vlanRequired && vlan !== "" ? Number(vlan) : null,
                  allowed_vlans: showAllowed ? allowed : [],
                  ssid: text(ssid), auth_mode: auth,
                  password: auth === "open" ? null : text(pass),
                })}>
      <div className="mb-3.5">
        {current ? (
          <Help>Terakhir ditulis Nexfiber: <span className="font-mono">{init.enabled ? "Aktif" : "Nonaktif"} · {modeLabel} · VLAN {init.vlan === "" ? "—" : init.vlan} · SSID {init.ssid === "" ? "—" : init.ssid}</span>. Modal ini menulis ulang konfigurasi port dari nilai di bawah.</Help>
        ) : (
          <Help>Konfigurasi saat ini belum dibaca dari perangkat — nilai di bawah adalah nilai baru yang akan ditulis, bukan konfigurasi saat ini. Simpan aktif setelah ada perubahan.</Help>
        )}
      </div>
      <Row label="Status">
        <Radios name={`wifi-${port}-status`} value={enabled} onChange={setEnabled} autoFocus
                options={[{ value: "on", label: "Aktif" }, { value: "off", label: "Port shutdown" }]} />
      </Row>
      {/* Acuan memakai radio sebaris untuk 4 mode WiFi (bukan select). */}
      <Row label="Mode">
        <Radios name={`wifi-${port}-mode`} value={mode} onChange={setMode} options={MODES} />
      </Row>
      {vlanRequired && (
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
      <Row label="SSID" hint="Kosong = SSID lama dipertahankan, bukan dihapus.">
        <input className={field} value={ssid} aria-label="SSID" autoComplete="off" maxLength={32}
               onChange={(e) => setSsid(e.target.value)} />
      </Row>
      {ssid.includes(" ") && (
        <div className="mb-3.5">
          <Help warn>SSID berspasi bisa terpotong di CLI OLT (perintah dipisah spasi).</Help>
        </div>
      )}
      <Row label="Auth mode"
           hint={<Help>Kemampuan autentikasi belum dilaporkan oleh ONU.</Help>}>
        <Select value={auth} onChange={setAuth} label="Auth mode">
          {AUTH.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </Select>
      </Row>
      {auth === "open" && (
        <div className="mb-3.5">
          <Help warn>Auth lama di perangkat tidak bisa dihapus (batas firmware); memilih Open tidak menghapus kunci WPA lama.</Help>
        </div>
      )}
      {auth !== "open" && (
        <>
          <Row label="Encryption">
            <span className="font-mono text-sm text-muted">AES</span>
          </Row>
          <Row label="New password" hint="Wajib diisi untuk WPA2/Auto.">
            <PasswordInput label="Password WiFi" value={pass} onChange={setPass} />
          </Row>
        </>
      )}
    </ModalShell>
  );
}
