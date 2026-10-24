import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router";
import { PageTitle } from "./components/data";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./lib/auth";
import { pageTitle } from "./lib/nav";
import { Dashboard } from "./pages/Dashboard";
import { Lainnya } from "./pages/Lainnya";
import { Login } from "./pages/Login";
import { OltDetail } from "./pages/OltDetail";
import { OnuTypes } from "./pages/settings/OnuTypes";
import { OltManagement } from "./pages/settings/OltManagement";
import { Splitters } from "./pages/settings/Splitters";
import { UserManagement } from "./pages/settings/UserManagement";
import { Setup } from "./pages/Setup";
import { SpeedProfile } from "./pages/settings/SpeedProfile";
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

const LATER = [
  "/unconfigured", "/unconfigured/authorize/:oltId/:serial", "/configured", "/onu/:id",
  "/settings/*", "/logs", "/akun/password",
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
            <Route path="/lainnya" element={<Lainnya />} />
            <Route path="/olt/:id" element={<OltDetail />} />
            <Route path="/settings/olts" element={<OltManagement />} />
            <Route path="/settings/users" element={<UserManagement />} />
            <Route path="/settings/onu-types" element={<OnuTypes />} />
            <Route path="/settings/splitters" element={<Splitters />} />
            <Route path="/settings/speed-profiles" element={<SpeedProfile />} />
            {LATER.map((p) => <Route key={p} path={p} element={<Placeholder />} />)}
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
