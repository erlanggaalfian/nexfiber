import {
  Broadcast, ClockCounterClockwise, Cpu, DotsThreeCircle, Gauge, HardDrives, House, ListBullets, PlusCircle,
  ShieldCheck, TreeStructure, Users, type Icon,
} from "@phosphor-icons/react";
import type { Role } from "./api";

export type NavItem = { label: string; to: string; icon: Icon };
export type SettingsItem = NavItem & { roles: Role[]; soon?: boolean };

const ALL: Role[] = ["superadmin", "admin", "user"];
const MANAGERS: Role[] = ["superadmin", "admin"];

/** DESIGN 11: fixed order, hidden per role (PRD 3.7). Phase 2 items stay visible but disabled. */
export const SETTINGS: SettingsItem[] = [
  { label: "OLT Management", to: "/settings/olts", icon: HardDrives, roles: MANAGERS },
  { label: "User Management", to: "/settings/users", icon: Users, roles: MANAGERS },
  { label: "ONU Types", to: "/settings/onu-types", icon: Cpu, roles: MANAGERS },
  { label: "Splitters & Zone", to: "/settings/splitters", icon: TreeStructure, roles: ALL },
  { label: "Speed Profile", to: "/settings/speed-profiles", icon: Gauge, roles: ALL },
  { label: "VPN Tunnels", to: "/settings/vpn", icon: ShieldCheck, roles: MANAGERS, soon: true },
  { label: "TR-069", to: "/settings/tr069", icon: Broadcast, roles: MANAGERS, soon: true },
];

export const settingsFor = (role: Role) => SETTINGS.filter((s) => s.roles.includes(role));

export const HEADER: NavItem[] = [
  { label: "Dashboard", to: "/", icon: House },
  { label: "Unconfigured", to: "/unconfigured", icon: PlusCircle },
  { label: "Configured", to: "/configured", icon: ListBullets },
  { label: "Logs", to: "/logs", icon: ClockCounterClockwise },
];

/** DESIGN 11.1: bottom tabs; only these 5 pages show the bottom bar. */
export const TABS: NavItem[] = [...HEADER, { label: "Lainnya", to: "/lainnya", icon: DotsThreeCircle }];

export function pageTitle(path: string) {
  const tab = TABS.find((t) => t.to === path);
  if (tab) return tab.label;
  const s = SETTINGS.find((i) => path.startsWith(i.to));
  if (s) return s.label;
  if (path.startsWith("/unconfigured/authorize")) return "Otorisasi ONU";
  if (path.startsWith("/onu/")) return "Detail ONU";
  if (path.startsWith("/olt/")) return "Detail OLT";
  if (path === "/akun/password") return "Ganti password";
  return "Nexfiber";
}
