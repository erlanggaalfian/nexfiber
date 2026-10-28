import { WaveSine } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { Button } from "../components/ui/button";
import { api, setToken } from "../lib/api";
import { login } from "../lib/auth";

export const input = "h-10 w-full rounded-sm border border-line-strong bg-surface px-2 text-base";

/** DESIGN 12.1: one card for Login and Setup. */
export function AuthCard({ onSubmit, children }: { onSubmit: (e: FormEvent<HTMLFormElement>) => void; children: ReactNode }) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-4">
      <p className="flex items-center gap-2 text-[15px] font-semibold">
        <WaveSine size={20} className="text-fiber" /> Nexfiber
      </p>
      <form onSubmit={onSubmit} className="w-full max-w-[360px] rounded-md border bg-surface p-4">
        {children}
      </form>
    </main>
  );
}

export function Field({ label, ...rest }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="mb-4 block">
      <span className="mb-1 block text-muted">{label}</span>
      <input required className={input} {...rest} />
    </label>
  );
}

export const useSetupNeeded = () =>
  useQuery({ queryKey: ["setup"], queryFn: () => api<{ needed: boolean }>("/api/auth/setup"), staleTime: Infinity });

export function Login() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const setup = useSetupNeeded();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await login(String(f.get("username")), String(f.get("password")));
      const next = params.get("next");
      // Validasi next yang ketat: hanya path internal absolut, bukan
      // //evil.com (redirect protokol-relatif), bukan /\evil.com, dan bukan
      // /login atau /setup (akan meloop kembali ke halaman auth).
      const safeNext =
        next !== null &&
        next.startsWith("/") &&
        !next.startsWith("//") &&
        !next.startsWith("/\\") &&
        next !== "/login" &&
        next !== "/setup" &&
        !next.startsWith("/login?") &&
        !next.startsWith("/login#") &&
        !next.startsWith("/setup?") &&
        !next.startsWith("/setup#");
      navigate(safeNext ? next! : "/", { replace: true });
    } catch (err) {
      setToken(null);
      setError(err instanceof Error ? err.message : "Login gagal");
      setBusy(false);
    }
  }

  if (setup.data?.needed) return <Navigate to="/setup" replace />;
  return (
    <AuthCard onSubmit={submit}>
      <Field label="Username" name="username" autoFocus autoComplete="username" />
      <Field label="Password" name="password" type="password" autoComplete="current-password" />
      {error && <p className="mb-3 text-down" role="alert">{error}</p>}
      <Button type="submit" variant="fiber" size="lg" className="w-full" disabled={busy}>
        {busy ? "Masuk ..." : "Masuk"}
      </Button>
    </AuthCard>
  );
}
