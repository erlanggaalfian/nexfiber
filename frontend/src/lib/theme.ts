import { useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";
const media = matchMedia("(prefers-color-scheme: dark)");

function apply(t: Theme) {
  document.documentElement.classList.toggle("dark", t === "dark" || (t === "system" && media.matches));
}

// ponytail: stored in localStorage (per browser); DESIGN.md wants per user. Move to a users column when roaming matters.
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem("theme") as Theme) || "light");
  useEffect(() => {
    localStorage.setItem("theme", theme);
    apply(theme);
    if (theme !== "system") return;
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);
  return [theme, setTheme] as const;
}
