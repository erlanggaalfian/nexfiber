/** Update location details — acuan `updateLocationDetails`. Hanya kolom database
 *  (`PUT /api/onus/{id}/location`), jadi perubahannya langsung berlaku tanpa job perangkat.
 *
 *  `Splitter port` mengikuti kapasitas splitter terpilih (`ports`), bukan angka bebas, dan
 *  daftar splitter disaring ke zone terpilih bila splitter-nya memang punya zone. */
import { useState } from "react";
import type { LocationBody, OnuConfigOptions } from "../../../lib/onuActions";
import { ModalShell, Row, Select, field } from "./ModalShell";
import { Button } from "../../ui/button";

type Form = {
  zone_id: string; splitter_id: string; splitter_port: string;
  customer_name: string; address: string; contact: string; latitude: string; longitude: string;
};

const str = (v: unknown) => (v === null || v === undefined ? "" : String(v));

export function LocationModal(
  { options, current, busy, error, onClose, onSubmit }:
  {
    options: OnuConfigOptions | undefined;
    current: Partial<Record<keyof Form, unknown>>;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (body: LocationBody) => void;
  },
) {
  const [f, setF] = useState<Form>({
    zone_id: str(current.zone_id), splitter_id: str(current.splitter_id),
    splitter_port: str(current.splitter_port),
    customer_name: str(current.customer_name), address: str(current.address),
    contact: str(current.contact),
    latitude: str(current.latitude), longitude: str(current.longitude),
  });
  const [geoMsg, setGeoMsg] = useState("");
  const set = (k: keyof Form, v: string) => setF((p) => ({ ...p, [k]: v }));

  const splitters = (options?.splitters ?? []).filter(
    (s) => f.zone_id === "" || s.zone_id === null || String(s.zone_id) === f.zone_id,
  );
  const picked = splitters.find((s) => String(s.id) === f.splitter_id);
  const portCount = picked?.ports ?? 0;

  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const text = (v: string) => (v.trim() === "" ? null : v.trim());
  const hasCoords = f.latitude.trim() !== "" && f.longitude.trim() !== "";
  // Koordinat tidak valid tidak boleh diam-diam jadi null saat submit: matikan Save
  // sampai diperbaiki. Sama untuk splitter port di bawah 1.
  const coordOk = (v: string, min: number, max: number) =>
    v.trim() === "" || (!Number.isNaN(Number(v)) && Number(v) >= min && Number(v) <= max);
  // Pasangan wajib lengkap: latitude tanpa longitude (atau sebaliknya) bisa tersimpan
  // dan tautan peta tidak bisa dipakai — keduanya terisi atau keduanya kosong.
  const coordsValid = coordOk(f.latitude, -90, 90) && coordOk(f.longitude, -180, 180)
    && (f.latitude.trim() === "") === (f.longitude.trim() === "");
  const portValid = f.splitter_port.trim() === "" || Number(f.splitter_port) >= 1;

  const locate = () => {
    if (!navigator.geolocation) {
      setGeoMsg("Peramban tidak mendukung lokasi.");
      return;
    }
    setGeoMsg("Mengambil lokasi ...");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setF((prev) => ({
          ...prev,
          latitude: p.coords.latitude.toFixed(6),
          longitude: p.coords.longitude.toFixed(6),
        }));
        setGeoMsg("");
      },
      (e) => setGeoMsg(e.message || "Lokasi tidak bisa diambil."),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  return (
    <ModalShell title="Update location details" action="Update" busy={busy} error={error}
                onClose={onClose} disabled={!coordsValid || !portValid}
                onSubmit={() => onSubmit({
                  zone_id: num(f.zone_id), splitter_id: num(f.splitter_id),
                  splitter_port: num(f.splitter_port),
                  customer_name: text(f.customer_name), address: text(f.address),
                  contact: text(f.contact),
                  latitude: num(f.latitude), longitude: num(f.longitude),
                })}>
      <Row label="Zone">
        <Select value={f.zone_id} placeholder="Tanpa zone" label="Zone"
                onChange={(v) => setF((p) => ({ ...p, zone_id: v, splitter_id: "", splitter_port: "" }))}>
          {(options?.zones ?? []).map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
        </Select>
      </Row>
      <Row label="Splitter">
        <Select value={f.splitter_id} placeholder="Tanpa splitter" label="Splitter"
                onChange={(v) => setF((p) => ({ ...p, splitter_id: v, splitter_port: "" }))}>
          {splitters.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
      </Row>
      <Row label="Splitter port">
        {portCount > 0 ? (
          <Select value={f.splitter_port} placeholder="Tanpa port" label="Splitter port"
                  onChange={(v) => set("splitter_port", v)}>
            {Array.from({ length: portCount }, (_, i) => (
              <option key={i + 1} value={i + 1}>{i + 1}</option>
            ))}
          </Select>
        ) : (
          <input className={field} type="number" min={1} value={f.splitter_port}
                 aria-label="Splitter port" onChange={(e) => set("splitter_port", e.target.value)} />
        )}
      </Row>
      <Row label="Name">
        <input className={field} value={f.customer_name} aria-label="Name"
               onChange={(e) => set("customer_name", e.target.value)} />
      </Row>
      <Row label="Address or comment">
        <input className={field} value={f.address} aria-label="Address or comment"
               onChange={(e) => set("address", e.target.value)} />
      </Row>
      <Row label="Contact">
        <input className={field} value={f.contact} aria-label="Contact"
               onChange={(e) => set("contact", e.target.value)} />
      </Row>
      <Row label="Latitude">
        <input className={field} value={f.latitude} placeholder="-6.200000" aria-label="Latitude"
               onChange={(e) => set("latitude", e.target.value)} />
      </Row>
      <Row label="Longitude">
        <input className={field} value={f.longitude} placeholder="106.816660" aria-label="Longitude"
               onChange={(e) => set("longitude", e.target.value)} />
      </Row>
      {/* Acuan: tombol lokasi + tautan peta sebaris di bawah Longitude. */}
      <div className="flex flex-wrap items-center gap-3 sm:pl-[25%]">
        <Button size="md" onClick={locate}>Get current location</Button>
        {hasCoords && (
          <a className="text-sm text-fiber hover:underline" target="_blank" rel="noreferrer"
             href={`https://www.openstreetmap.org/?mlat=${f.latitude}&mlon=${f.longitude}#map=17/${f.latitude}/${f.longitude}`}>
            Open in Maps
          </a>
        )}
        {geoMsg && <span className="text-xs text-muted">{geoMsg}</span>}
      </div>
    </ModalShell>
  );
}
