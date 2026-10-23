import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import { Button } from "../components/ui/button";
import { api, setToken } from "../lib/api";
import { AuthCard, Field, useSetupNeeded } from "./Login";

/** PRD 3.4.1: creates the first Superadmin; the backend answers 404 once any user exists. */
export function Setup() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const setup = useSetupNeeded();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    if (f.password !== f.password_confirm) return setError("Password tidak sama");
    setBusy(true);
    setError("");
    try {
      const r = await api<{ access_token: string }>("/api/auth/setup", { method: "POST", json: f });
      setToken(r.access_token);
      qc.setQueryData(["setup"], { needed: false });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup gagal");
      setBusy(false);
    }
  }

  if (setup.isPending) return null;
  if (!setup.data?.needed) return <Navigate to="/login" replace />;
  return (
    <AuthCard onSubmit={submit}>
      <Field label="Username" name="username" autoFocus autoComplete="username" pattern="[A-Za-z0-9_.\-]{3,64}" />
      <Field label="Nama" name="full_name" autoComplete="name" />
      <Field label="Password" name="password" type="password" minLength={12} autoComplete="new-password" />
      <Field label="Ulangi password" name="password_confirm" type="password" minLength={12} autoComplete="new-password" />
      {error && <p className="mb-3 text-down" role="alert">{error}</p>}
      <Button type="submit" variant="fiber" size="lg" className="w-full" disabled={busy}>
        {busy ? "Membuat ..." : "Buat Superadmin"}
      </Button>
    </AuthCard>
  );
}
