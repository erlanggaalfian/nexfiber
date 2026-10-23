import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { api, getToken, setToken, type Me } from "./api";

type Auth = { me: Me; can: (perm: string) => boolean; logout: () => void };
const AuthContext = createContext<Auth | null>(null);

export async function login(username: string, password: string) {
  const r = await api<{ access_token: string }>("/api/auth/login", { method: "POST", json: { username, password } });
  setToken(r.access_token);
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const qc = useQueryClient();
  const token = getToken();
  const q = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/auth/me"), enabled: !!token, staleTime: Infinity });
  if (!token) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (q.isPending) return <p className="p-4 text-muted">Memuat sesi ...</p>;
  if (q.isError) return <p className="p-4 text-down">Gagal memuat sesi: {q.error.message}</p>;
  const me = q.data;
  const logout = () => {
    setToken(null);
    qc.clear();
    location.assign("/login");
  };
  return <AuthContext value={{ me, can: (p) => me.permissions.includes(p), logout }}>{children}</AuthContext>;
}

export function useAuth() {
  const a = useContext(AuthContext);
  if (!a) throw new Error("useAuth outside RequireAuth");
  return a;
}
