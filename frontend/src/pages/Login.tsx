import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Button } from "../components/ui/button";
import { login } from "../lib/auth";

const input = "h-10 w-full rounded-sm border border-line-strong bg-surface px-2 text-base";

export function Login() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
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
      navigate(next?.startsWith("/") ? next : "/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login gagal");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-80 rounded-md border bg-surface p-4">
        <h1 className="mb-4 text-xl font-semibold text-fiber">Nexfiber</h1>
        <label className="mb-4 block">
          <span className="mb-1 block text-muted">Username</span>
          <input name="username" required autoFocus autoComplete="username" className={input} />
        </label>
        <label className="mb-4 block">
          <span className="mb-1 block text-muted">Password</span>
          <input name="password" type="password" required autoComplete="current-password" className={input} />
        </label>
        {error && <p className="mb-3 text-down" role="alert">{error}</p>}
        <Button type="submit" variant="secondary" size="lg" className="w-full" disabled={busy}>
          {busy ? "Masuk ..." : "Masuk"}
        </Button>
      </form>
    </main>
  );
}
