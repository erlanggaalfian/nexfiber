import { useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";
const media = matchMedia("(prefers-color-scheme: dark)");
const listeners = new Set<() => void>();

const read = () => (localStorage.getItem("theme") as Theme) || "light";

function apply(t: Theme) {
  const dark = t === "dark" || (t === "system" && media.matches);
  document.documentElement.classList.toggle("dark", dark);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#1b1c19" : "#ffffff");
}

media.addEventListener("change", () => apply(read()));

function setTheme(t: Theme) {
  localStorage.setItem("theme", t);
  apply(t);
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

// ponytail: stored in localStorage (per browser); DESIGN.md wants per user. Move to a users column when roaming matters.
export function useTheme() {
  return [useSyncExternalStore(subscribe, read), setTheme] as const;
}

export const THEMES: [Theme, string][] = [["system", "Sistem"], ["light", "Terang"], ["dark", "Gelap"]];