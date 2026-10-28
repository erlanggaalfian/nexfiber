import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router";
import { PageTitle } from "./components/data";
import { Layout } from "./components/Layout";
import { ChangePasswordPage, RequireAuth, useAuth } from "./lib/auth";
// Side effect: lib/theme menerapkan tema tersimpan/sistem saat dimuat, sebelum
// render pertama — penting untuk /login dan /setup yang tidak memanggil useTheme().
import "./lib/theme";
import { pageTitle } from "./lib/nav";
import type { Role } from "./lib/api";
import { Dashboard } from "./pages/Dashboard";
import { Lainnya } from "./pages/Lainnya";
import { Login } from "./pages/Login";
import { OltDetail } from "./pages/OltDetail";
import { GraphData } from "./pages/settings/GraphData";
import { OnuTypes } from "./pages/settings/OnuTypes";
import { OltManagement } from "./pages/settings/OltManagement";
import { Splitters } from "./pages/settings/Splitters";
import { UserManagement } from "./pages/settings/UserManagement";
import { Setup } from "./pages/Setup";
import { SpeedProfile } from "./pages/settings/SpeedProfile";
import { AuthorizeOnu } from "./pages/AuthorizeOnu";
import { Configured } from "./pages/Configured";
import { OnuDetail } from "./pages/OnuDetail";
import { Unconfigured } from "./pages/Unconfigured";
import { Logs } from "./pages/Logs";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 2, refetchOnWindowFocus: true, refetchIntervalInBackground: false },
  },
});

function NotFound() {
  return (
    <>
      <PageTitle title="Halaman tidak ditemukan" />
      <Link to="/" className="text-fiber hover:underline">Kembali ke Dashboard</Link>
    </>
  );
}

// ponytail: routes for later stages render this until their page is built.
function Placeholder() {
  const title = pageTitle(useLocation().pathname);
  return (
    <>
      <PageTitle title={title} />
      <p className="text-muted">Halaman {title} belum dibangun pada tahap ini.</p>
    </>
  );
}

/** Gate role di UI, konsisten dengan menu (settingsFor): bukan redirect diam-diam,
 *  melainkan halaman penjelasan + tautan ke Dashboard. Gate backend tetap penentu. */
function RequireSettingsRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { me } = useAuth();
  if (!roles.includes(me.role)) {
    return (
      <>
        <PageTitle title="Tidak ada akses" />
        <p className="text-muted">Halaman ini hanya untuk {roles.join(", ")}. Peran kamu: {me.role}.</p>
        <Link to="/" className="text-fiber hover:underline">Kembali ke Dashboard</Link>
      </>
    );
  }
  return <>{children}</>;
}

const MANAGERS: Role[] = ["superadmin", "admin"];

// Hanya halaman "Segera" yang dikenal yang masih memakai Placeholder; URL settings
// lain yang tidak dikenal diarahkan ke NotFound (bukan Placeholder yang menyamarkan typo).
const LATER = [
  "/settings/vpn", "/settings/tr069",
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/setup" element={<Setup />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route index element={<Dashboard />} />
            <Route path="/unconfigured" element={<Unconfigured />} />
            <Route path="/unconfigured/authorize/:oltId/:serial" element={<AuthorizeOnu />} />
            <Route path="/configured" element={<Configured />} />
            <Route path="/onu/:id" element={<OnuDetail />} />
            <Route path="/lainnya" element={<Lainnya />} />
            <Route path="/akun/password" element={<ChangePasswordPage />} />
            <Route path="/olt/:id" element={<OltDetail />} />
            <Route path="/settings/olts" element={<RequireSettingsRole roles={MANAGERS}><OltManagement /></RequireSettingsRole>} />
            <Route path="/settings/users" element={<RequireSettingsRole roles={MANAGERS}><UserManagement /></RequireSettingsRole>} />
            <Route path="/settings/onu-types" element={<RequireSettingsRole roles={MANAGERS}><OnuTypes /></RequireSettingsRole>} />
            <Route path="/settings/splitters" element={<Splitters />} />
            <Route path="/settings/speed-profiles" element={<SpeedProfile />} />
            <Route path="/settings/graph-data" element={<RequireSettingsRole roles={MANAGERS}><GraphData /></RequireSettingsRole>} />
            <Route path="/logs" element={<Logs />} />
            {LATER.map((p) => <Route key={p} path={p} element={<Placeholder />} />)}
            <Route path="/settings/*" element={<NotFound />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
