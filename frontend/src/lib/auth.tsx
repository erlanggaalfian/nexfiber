import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useState, type FormEvent, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { api, getToken, setToken, type Me } from "./api";

type Auth = { me: Me; isManager: boolean; logout: () => void };
const AuthContext = createContext<Auth | null>(null);

export async function login(username: string, password: string) {
  const r = await api<{ access_token: string }>("/api/auth/login", { method: "POST", json: { username, password } });
  setToken(r.access_token);
}

/** Form ganti password yang ditampilkan saat must_change_password aktif.

    Sebelumnya flag ini tidak pernah dibaca di mana pun, sehingga password
    sementara hasil reset berlaku selamanya. Login tetap berhasil (token
    valid), tapi pengguna tidak bisa masuk ke aplikasi sebelum mengganti
    password lewat endpoint /api/auth/change-password — itu jalan keluarnya,
    bukan jebakan tanpa jalan. Setelah berhasil, token lama tercabut karena
    password_hash berubah, jadi token sesi ini ikut diganti lewat login ulang
    sederhana: form ini memanggil change-password lalu memaksa login ulang
    dengan password baru supaya sesi berjalan dengan token yang baru. */
function ChangePasswordForm({ onDone, title }: { onDone: () => void; title?: string }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const change = useMutation({
    mutationFn: (body: { old_password: string; new_password: string }) =>
      api<void>("/api/auth/change-password", { method: "POST", json: body }),
  });
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const oldPw = String(f.get("old_password"));
    const newPw = String(f.get("new_password"));
    const confirm = String(f.get("new_password_confirm"));
    if (newPw.length < 12) return setError("Password baru minimal 12 karakter");
    if (newPw !== confirm) return setError("Password baru tidak sama");
    setBusy(true);
    setError("");
    try {
      await change.mutateAsync({ old_password: oldPw, new_password: newPw });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ganti password gagal");
      setBusy(false);
    }
  }
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-4">
      <form onSubmit={submit} className="w-full max-w-[360px] rounded-md border bg-surface p-4">
        <p className="mb-4 text-sm font-medium">{title ?? "Password Anda harus diganti"}</p>
        <label className="mb-4 block">
          <span className="mb-1 block text-muted">Password lama</span>
          <input required name="old_password" type="password" autoComplete="current-password"
                 className="h-8 max-md:h-12 w-full min-w-0 rounded-sm border border-line-strong bg-surface px-3 text-sm" />
        </label>
        <label className="mb-4 block">
          <span className="mb-1 block text-muted">Password baru (min 12 karakter)</span>
          <input required name="new_password" type="password" minLength={12} autoComplete="new-password"
                 className="h-8 max-md:h-12 w-full min-w-0 rounded-sm border border-line-strong bg-surface px-3 text-sm" />
        </label>
        <label className="mb-4 block">
          <span className="mb-1 block text-muted">Ulangi password baru</span>
          <input required name="new_password_confirm" type="password" minLength={12} autoComplete="new-password"
                 className="h-8 max-md:h-12 w-full min-w-0 rounded-sm border border-line-strong bg-surface px-3 text-sm" />
        </label>
        {error && <p className="mb-3 text-down" role="alert">{error}</p>}
        <button type="submit" disabled={busy}
                className="h-8 max-md:h-12 w-full rounded-sm bg-fiber px-4 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "Menyimpan ..." : "Ganti password"}
        </button>
      </form>
    </main>
  );
}

/** Halaman ganti password mandiri (/akun/password): pakai ulang form yang sama
 *  dengan jalur wajib, lalu logout paksa sesudahnya — token lama tercabut saat
 *  password berubah, jadi sesi harus dimulai ulang dengan password baru. */
export function ChangePasswordPage() {
  const qc = useQueryClient();
  return (
    <ChangePasswordForm
      title="Ganti password"
      onDone={() => {
        setToken(null);
        qc.clear();
        location.assign("/login");
      }}
    />
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const qc = useQueryClient();
  const token = getToken();
  // staleTime terbatas 60 detik (bukan Infinity): perubahan role/status user
  // (mis. dinonaktifkan/diminta ganti password) tidak lagi tertahan selamanya
  // di cache sampai refresh penuh. Dipilih staleTime, bukan invalidate ["me"]
  // di SSE, supaya tidak ada refetch tiap job selesai.
  const q = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/auth/me"), enabled: !!token, staleTime: 60_000 });
  if (!token) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (q.isPending) return <p className="p-4 text-muted">Memuat sesi ...</p>;
  if (q.isError) {
    // Jalan buntu sebelumnya: hanya teks error tanpa aksi apa pun.
    // 401 berarti token mati — arahkan ke login. Error lain (jaringan/server)
    // diberi tombol Coba lagi (invalidate query me) dan Keluar.
    const status = (q.error as Error & { status?: number }).status;
    if (status === 401) return <Navigate to="/login" replace />;
    const logout = () => {
      setToken(null);
      qc.clear();
      location.assign("/login");
    };
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-4">
        <p className="text-down" role="alert">Gagal memuat sesi: {q.error.message}</p>
        <div className="flex gap-2">
          <button type="button" onClick={() => void qc.invalidateQueries({ queryKey: ["me"] })}
                  className="h-8 max-md:h-12 rounded-sm border border-line-strong px-4 text-sm font-medium">
            Coba lagi
          </button>
          <button type="button" onClick={logout}
                  className="h-8 max-md:h-12 rounded-sm border border-line-strong px-4 text-sm font-medium">
            Keluar
          </button>
        </div>
      </main>
    );
  }
  const me = q.data;
  if (me.must_change_password) {
    return (
      <ChangePasswordForm
        onDone={() => {
          // Token lama tercabut saat password berubah; arahkan ke login
          // supaya pengguna masuk dengan token baru, bukan token tercabut.
          setToken(null);
          qc.clear();
          location.assign("/login");
        }}
      />
    );
  }
  const logout = () => {
    // Cabut token di server dulu (best-effort): tanpa ini token lama tetap
    // hidup sampai kedaluwarsa walau localStorage sudah dibersihkan.
    void api<void>("/api/auth/logout", { method: "POST" }).catch(() => undefined).finally(() => {
      setToken(null);
      qc.clear();
      location.assign("/login");
    });
  };
  // Menu visibility only; the backend enforces scope and roles on every endpoint (PRD 3.7).
  return <AuthContext value={{ me, isManager: me.role !== "user", logout }}>{children}</AuthContext>;
}

export function useAuth() {
  const a = useContext(AuthContext);
  if (!a) throw new Error("useAuth outside RequireAuth");
  return a;
}