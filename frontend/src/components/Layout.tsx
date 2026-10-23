import {
  BellSimple, ChartBar, ClockCounterClockwise, Cpu, Desktop, HardDrives, Moon, Plugs, SignOut, SlidersHorizontal,
  Stack, Sun,
  type Icon,
} from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";
import { api, type PendingOnu } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useJobStream } from "../lib/jobs";
import { useTheme, type Theme } from "../lib/theme";

type Item = { label: string; icon: Icon; to?: string; badge?: number };

function NavItem({ item }: { item: Item }) {
  const base = "flex h-8 items-center gap-2 rounded-sm px-2";
  const Ic = item.icon;
  const body = (
    <>
      <Ic size={16} className="shrink-0" />
      <span className="hidden flex-1 truncate lg:inline">{item.label}</span>
      {item.badge ? <span className="hidden font-mono text-xs lg:inline">{item.badge}</span> : null}
      {!item.to && <span className="hidden text-xs text-faint lg:inline">Segera</span>}
    </>
  );
  if (!item.to)
    return (
      <span className={`${base} cursor-not-allowed text-faint`} aria-disabled title={`${item.label} (segera)`}>
        {body}
      </span>
    );
  return (
    <NavLink
      to={item.to}
      end={item.to === "/" || item.to === "/onus"}
      title={item.label}
      className={({ isActive }) => `${base} ${isActive ? "bg-sunken font-medium text-fiber" : "text-ink hover:bg-sunken"}`}
    >
      {body}
    </NavLink>
  );
}

const THEMES: [Theme, string][] = [["system", "Sistem"], ["light", "Terang"], ["dark", "Gelap"]];

export function Layout() {
  const { me, logout } = useAuth();
  const [theme, setTheme] = useTheme();
  useJobStream();
  const pending = useQuery({
    queryKey: ["pending"],
    queryFn: () => api<PendingOnu[]>("/api/onus/pending"),
    refetchInterval: 60_000,
  });

  const groups: [string, Item[]][] = [
    ["Monitor", [
      { label: "Ringkasan", icon: ChartBar, to: "/" },
      { label: "Alarm", icon: BellSimple },
    ]],
    ["Perangkat", [
      { label: "OLT", icon: HardDrives, to: "/olts" },
      { label: "ONU", icon: Cpu, to: "/onus" },
      { label: "Otorisasi menunggu", icon: Plugs, to: "/onus/pending", badge: pending.data?.length },
    ]],
    ["Konfigurasi", [
      { label: "Profile", icon: SlidersHorizontal },
      { label: "Template Provisioning", icon: Stack },
    ]],
    ["Riwayat", [{ label: "Log Aksi", icon: ClockCounterClockwise }]],
  ];

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 flex h-dvh w-12 shrink-0 flex-col border-r bg-surface lg:w-52">
        <div className="flex h-12 items-center px-3 text-lg font-semibold text-fiber">
          <span className="lg:hidden">N</span>
          <span className="hidden lg:inline">Nexfiber</span>
        </div>
        <nav className="flex-1 overflow-y-auto px-1.5 lg:px-2">
          {groups.map(([group, items]) => (
            <div key={group} className="mb-3">
              <p className="mb-1 hidden px-2 text-xs text-muted lg:block">{group}</p>
              {items.map((i) => <NavItem key={i.label} item={i} />)}
            </div>
          ))}
        </nav>
        <div className="border-t p-2 text-xs">
          <label className="hidden lg:block">
            <span className="text-muted">Tema</span>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
              className="mt-1 h-7 w-full rounded-sm border border-line-strong bg-surface px-1"
            >
              {THEMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <button
            onClick={() => setTheme(THEMES[(THEMES.findIndex(([v]) => v === theme) + 1) % 3][0])}
            title={`Tema: ${THEMES.find(([v]) => v === theme)?.[1]}`}
            className="rounded-sm p-1.5 text-muted hover:bg-sunken lg:hidden"
          >
            {theme === "dark" ? <Moon size={16} /> : theme === "light" ? <Sun size={16} /> : <Desktop size={16} />}
            <span className="sr-only">Ganti tema</span>
          </button>
          <div className="mt-2 flex flex-col items-center gap-2 lg:flex-row">
            <div className="hidden min-w-0 flex-1 lg:block">
              <p className="truncate text-sm text-ink">{me.full_name}</p>
              <p className="text-muted">{me.role}</p>
            </div>
            <button onClick={logout} title="Keluar" className="rounded-sm p-1.5 text-muted hover:bg-sunken">
              <SignOut size={16} />
              <span className="sr-only">Keluar</span>
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-3 lg:p-4">
        <Outlet />
      </main>
    </div>
  );
}
