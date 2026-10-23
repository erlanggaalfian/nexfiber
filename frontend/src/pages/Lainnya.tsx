import { Key, Palette, SignOut } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { PageTitle } from "../components/data";
import { useAuth } from "../lib/auth";
import { settingsFor } from "../lib/nav";
import { THEMES, useTheme, type Theme } from "../lib/theme";

const row = "flex min-h-12 items-center gap-3 px-4 text-base";

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-4">
      <h2 className="mb-1 px-1 text-xs text-muted">{title}</h2>
      <ul className="divide-y rounded-md border bg-surface">{children}</ul>
    </section>
  );
}

/** DESIGN 11.1 tab 5: Settings (per role) + Akun. */
export function Lainnya() {
  const { me, logout } = useAuth();
  const [theme, setTheme] = useTheme();
  return (
    <>
      <PageTitle title="Lainnya" />
      <Group title="Settings">
        {settingsFor(me.role).map((i) => {
          const Ic = i.icon;
          return (
            <li key={i.to}>
              {i.soon ? (
                <span className={`${row} text-faint`} aria-disabled>
                  <Ic size={20} /> <span className="flex-1">{i.label}</span> <span className="text-xs">Segera</span>
                </span>
              ) : (
                <Link to={i.to} className={`${row} hover:bg-sunken`}>
                  <Ic size={20} /> {i.label}
                </Link>
              )}
            </li>
          );
        })}
      </Group>
      <Group title="Akun">
        <li>
          <Link to="/akun/password" className={`${row} hover:bg-sunken`}>
            <Key size={20} /> Ganti password
          </Link>
        </li>
        <li className={row}>
          <Palette size={20} /> <span className="flex-1">Tema</span>
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value as Theme)}
            aria-label="Tema"
            className="h-9 rounded-sm border border-line-strong bg-surface px-2"
          >
            {THEMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </li>
        <li>
          <button onClick={logout} className={`${row} w-full text-down hover:bg-sunken`}>
            <SignOut size={20} /> Logout
          </button>
        </li>
      </Group>
      <p className="px-1 text-xs text-muted">{me.full_name} · {me.username}</p>
    </>
  );
}
