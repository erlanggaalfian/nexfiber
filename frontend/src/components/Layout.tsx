import { ArrowLeft, CaretDown, WaveSine } from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DropdownMenu, Popover } from "radix-ui";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { api, type PendingOnu, type SystemStatus } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useJobStream } from "../lib/jobs";
import { HEADER, TABS, pageTitle, settingsFor } from "../lib/nav";
import { THEMES, useTheme, type Theme } from "../lib/theme";
import { fmtTime } from "./data";

const ROLE_LABEL = { superadmin: "Superadmin", admin: "Admin", user: "User" };
const overlay = "z-50 rounded-md border bg-surface p-1 shadow-overlay";
const menuItem =
  "flex h-9 cursor-pointer items-center gap-2 rounded-sm px-2 text-sm text-ink outline-none data-[highlighted]:bg-sunken data-[highlighted]:outline-2 data-[highlighted]:outline-solid data-[highlighted]:outline-focus max-lg:min-h-12";

function usePending() {
  return useQuery({
    queryKey: ["pending"],
    queryFn: () => api<PendingOnu[]>("/api/onus/pending"),
    refetchInterval: 60_000,
  }).data?.length ?? 0;
}

function Badge({ n, className = "" }: { n: number; className?: string }) {
  if (!n) return null;
  return (
    <span className={`rounded-sm bg-amber px-1 font-mono text-xs leading-4 text-on-amber ${className}`}>
      {n > 99 ? "99+" : n}
    </span>
  );
}

const menuClass = (active: boolean) =>
  `relative flex h-14 items-center gap-1.5 rounded-sm px-3 text-sm ${
    active
      ? "font-semibold text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-fiber"
      : "font-medium text-muted hover:bg-sunken hover:text-ink"
  }`;

function SettingsMenu() {
  const { me } = useAuth();
  const { pathname } = useLocation();
  const items = settingsFor(me.role);
  const active = pathname.startsWith("/settings");
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger className={menuClass(active)} aria-current={active ? "page" : undefined}>
        Settings <CaretDown size={12} />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={4} className={`${overlay} w-60`}>
          {items.map((i, idx) => {
            const sep = i.soon && !items[idx - 1]?.soon;
            const Ic = i.icon;
            const isActive = pathname === i.to;
            return (
              <div key={i.to}>
                {sep && <DropdownMenu.Separator className="my-1 h-px bg-line" />}
                {i.soon ? (
                  <DropdownMenu.Item disabled className={`${menuItem} cursor-not-allowed text-faint`}>
                    <Ic size={16} /> <span className="flex-1">{i.label}</span>
                    <span className="text-xs">Segera</span>
                  </DropdownMenu.Item>
                ) : (
                  <DropdownMenu.Item asChild className={`${menuItem}${isActive ? " bg-sunken font-semibold text-ink" : ""}`}>
                    <Link to={i.to} aria-current={isActive ? "page" : undefined}>
                      <Ic size={16} /> {i.label}
                    </Link>
                  </DropdownMenu.Item>
                )}
              </div>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function SystemDot() {
  const q = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api<SystemStatus>("/api/system/status"),
    refetchInterval: 30_000,
  });
  const alive = q.data?.worker_alive;
  // Tertunda = worker hidup tapi masih ada job yang mengantre (data yang sudah
  // diambil query ini, tanpa endpoint/polling baru, tanpa animasi pada titik).
  const stalled = alive && (q.data?.jobs_pending ?? 0) > 0;
  const label = q.isPending ? "Memeriksa" : stalled ? "Sistem tertunda" : alive ? "Sistem aktif" : "Worker mati";
  const color = q.isPending ? "bg-idle" : stalled ? "bg-warn" : alive ? "bg-up" : "bg-down";
  return (
    <Popover.Root>
      <Popover.Trigger className="flex h-8 items-center gap-1.5 rounded-sm px-2 text-xs text-muted hover:bg-sunken" title={label}>
        <span className={`size-1.5 ${color}`} aria-hidden />
        <span className="max-xl:sr-only">{label}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={4} className={`${overlay} w-60 p-3 text-sm`}>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted">Worker</dt>
            <dd>{alive ? "Aktif" : "Mati"} · {fmtTime(q.data?.worker_heartbeat_at ?? null)}</dd>
            <dt className="text-muted">Job antre</dt>
            <dd className="font-mono">{q.data?.jobs_pending ?? "—"}</dd>
            <dt className="text-muted">Poll terakhir</dt>
            <dd className="font-mono">{fmtTime(q.data?.last_poll_at ?? null)}</dd>
          </dl>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

function AvatarMenu() {
  const { me, logout } = useAuth();
  const [theme, setTheme] = useTheme();
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger
        className="flex size-12 items-center justify-center lg:size-7"
        aria-label={`Akun ${me.full_name}`}
      >
        <span className="flex size-7 items-center justify-center rounded-full bg-sunken text-xs font-semibold text-ink">
          {initials(me.full_name)}
        </span>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4} className={`${overlay} w-60`}>
          <div className="px-2 py-1.5">
            <p className="truncate text-sm text-ink">{me.full_name}</p>
            <p className="text-xs text-muted">{ROLE_LABEL[me.role]}</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item asChild className={menuItem}>
            <Link to="/akun/password">Ganti password</Link>
          </DropdownMenu.Item>
          <DropdownMenu.Label className="px-2 pt-1.5 text-xs text-muted">Tema</DropdownMenu.Label>
          <DropdownMenu.RadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
            {THEMES.map(([v, l]) => (
              <DropdownMenu.RadioItem key={v} value={v} className={`${menuItem} data-[state=checked]:font-semibold`}>
                <span className="w-3 text-fiber">{theme === v ? "●" : ""}</span> {l}
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item onSelect={logout} className={menuItem}>Logout</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function DesktopHeader({ pending }: { pending: number }) {
  return (
    <header className="sticky top-0 z-40 hidden h-14 border-b bg-surface lg:block">
      <div className="mx-auto flex h-full max-w-[1440px] items-center gap-4 px-4">
        <Link to="/" className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <WaveSine size={20} className="text-fiber" /> Nexfiber
        </Link>
        <nav aria-label="Menu utama" className="flex items-center gap-1">
          {HEADER.slice(0, 3).map((i) => (
            <NavLink key={i.to} to={i.to} end className={({ isActive }) => menuClass(isActive)}>
              {i.label}
              {i.to === "/unconfigured" && <Badge n={pending} />}
            </NavLink>
          ))}
          <SettingsMenu />
          <NavLink to="/logs" className={({ isActive }) => menuClass(isActive)}>Logs</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <SystemDot />
          <AvatarMenu />
        </div>
      </div>
    </header>
  );
}

function MobileTopBar({ isTab, title }: { isTab: boolean; title: string }) {
  const navigate = useNavigate();
  // Bila tidak ada riwayat kembali (mis. dibuka langsung lewat URL), kembali ke
  // Dashboard, bukan navigate(-1) yang tidak ke mana-mana.
  const goBack = () => { window.history.length > 1 ? navigate(-1) : navigate("/"); };
  return (
    <header className="sticky top-0 z-40 flex h-[calc(3.5rem+env(safe-area-inset-top))] items-center gap-2 border-b bg-surface px-3 pt-[env(safe-area-inset-top)] lg:hidden">
      {!isTab && (
        <button onClick={goBack} className="-ml-1 flex size-12 items-center justify-center rounded-sm transition-colors duration-[var(--motion-hover)] hover:bg-sunken motion-reduce:transition-none" aria-label="Kembali">
          <ArrowLeft size={20} />
        </button>
      )}
      <span className="min-w-0 flex-1 truncate text-lg font-semibold" aria-hidden>{title}</span>
      <AvatarMenu />
    </header>
  );
}

function BottomNav({ pending }: { pending: number }) {
  const { pathname } = useLocation();
  const qc = useQueryClient();
  return (
    <nav
      aria-label="Menu utama"
      className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {TABS.map((t) => {
        const active = pathname === t.to;
        const Ic = t.icon;
        return (
          <Link
            key={t.to}
            to={t.to}
            aria-current={active ? "page" : undefined}
            onClick={() => {
              if (!active) return;
              scrollTo({ top: 0 });
              qc.invalidateQueries();
            }}
            className={`flex h-16 flex-col items-center justify-center gap-1 text-xs ${active ? "font-semibold text-ink" : "font-medium text-muted"}`}
          >
            <span className="relative flex h-8 w-14 items-center justify-center">
              <span
                className={`absolute inset-0 rounded-nav bg-fiber/12 transition-transform duration-[var(--motion-hover)] ease-out motion-reduce:transition-none ${active ? "scale-100" : "scale-0"}`}
                aria-hidden
              />
              <Ic size={24} weight={active ? "fill" : "regular"} className={`relative ${active ? "text-fiber" : ""}`} />
              {t.to === "/unconfigured" && <Badge n={pending} className="absolute -top-1 right-1" />}
            </span>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Layout() {
  const { disconnected } = useJobStream();
  const pending = usePending();
  const { pathname } = useLocation();
  const isTab = TABS.some((t) => t.to === pathname);
  return (
    <div className="min-h-dvh">
      <a href="#konten" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-2">
        Langsung ke konten
      </a>
      {disconnected && (
        <p className="border-l-2 border-warn bg-sunken px-4 py-2 text-center text-xs text-warn" role="status">
          Koneksi update job terputus — pembaruan job mungkin tertunda sampai koneksi pulih.
        </p>
      )}
      <DesktopHeader pending={pending} />
      <MobileTopBar isTab={isTab} title={pageTitle(pathname)} />
      <main id="konten" className={`mx-auto max-w-[1440px] p-3 lg:p-4 ${isTab ? "pb-[calc(6rem+env(safe-area-inset-bottom))] lg:pb-4" : "pb-[calc(0.75rem+env(safe-area-inset-bottom))] lg:pb-4"}`}>
        <Outlet />
      </main>
      {isTab && <BottomNav pending={pending} />}
    </div>
  );
}
