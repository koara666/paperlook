export type ThemeMode = "system" | "light" | "dark";

let mql: MediaQueryList | null = null;
let listener: ((e: MediaQueryListEvent) => void) | null = null;

export function applyTheme(mode: ThemeMode) {
  try {
    localStorage.setItem("pl-theme", mode);
  } catch {
    /* storage unavailable */
  }
  const root = document.documentElement;
  if (mql && listener) mql.removeEventListener("change", listener);
  if (mode === "system") {
    mql = window.matchMedia("(prefers-color-scheme: dark)");
    root.classList.toggle("dark", mql.matches);
    listener = (e) => root.classList.toggle("dark", e.matches);
    mql.addEventListener("change", listener);
  } else {
    root.classList.toggle("dark", mode === "dark");
  }
}

export function storedTheme(): ThemeMode {
  try {
    const v = localStorage.getItem("pl-theme");
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "system";
}
