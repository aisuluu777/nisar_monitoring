import { create } from "zustand";
import { setDataModeHeader, setToken, type Meta, type StatusCode } from "./api/client";
import { translate, type Lang } from "./i18n";

export type DataLayer = "none" | "disp" | "sm" | "precip" | "veg" | "relief";
export interface User {
  id: number;
  username: string;
  display_name: string;
  role: string;
  district_id: string | null;
}

function load<T>(storage: "local" | "session", key: string, fallback: T): T {
  try {
    const s = storage === "local" ? window.localStorage : window.sessionStorage;
    const v = s.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(storage: "local" | "session", key: string, value: unknown) {
  try {
    const s = storage === "local" ? window.localStorage : window.sessionStorage;
    if (value === null) s.removeItem(key);
    else s.setItem(key, JSON.stringify(value));
  } catch {
    /* хранилище недоступно — работаем в памяти */
  }
}

const savedAuth = load<{ token: string; user: User } | null>("session", "sw.auth", null);
if (savedAuth) setToken(savedAuth.token);
const savedMode = load<"real" | "demo" | null>("local", "sw.mode", null);
setDataModeHeader(savedMode);

interface State {
  lang: Lang;
  dataMode: "real" | "demo" | null;
  focus: { lon: number; lat: number; id: string } | null;
  tourOpen: boolean;
  token: string | null;
  user: User | null;
  meta: Meta | null;
  path: string;
  cycleIdx: number | null;
  showStatus: boolean;
  dataLayer: DataLayer;
  showEvents: boolean;
  statusFilter: StatusCode | null;
  selectedCell: string | null;
  setLang: (l: Lang) => void;
  setDataMode: (m: "real" | "demo") => void;
  setFocus: (f: { lon: number; lat: number; id: string } | null) => void;
  setTourOpen: (v: boolean) => void;
  login: (token: string, user: User) => void;
  logout: () => void;
  setMeta: (m: Meta) => void;
  navigate: (p: string) => void;
  setCycleIdx: (i: number) => void;
  setShowStatus: (v: boolean) => void;
  setDataLayer: (l: DataLayer) => void;
  setShowEvents: (v: boolean) => void;
  setStatusFilter: (s: StatusCode | null) => void;
  selectCell: (id: string | null) => void;
}

export const useStore = create<State>((set) => ({
  lang: load<Lang>("local", "sw.lang", "ru"),
  dataMode: savedMode,
  focus: null,
  tourOpen: false,
  token: savedAuth?.token ?? null,
  user: savedAuth?.user ?? null,
  meta: null,
  path: window.location.pathname,
  cycleIdx: null,
  showStatus: true,
  dataLayer: "none",
  showEvents: false,
  statusFilter: null,
  selectedCell: null,
  setLang: (lang) => {
    save("local", "sw.lang", lang);
    document.documentElement.lang = lang;
    set({ lang });
  },
  setDataMode: (dataMode) => {
    save("local", "sw.mode", dataMode);
    setDataModeHeader(dataMode);
    // другой режим — другие данные: сбрасываем выбранную ячейку и цикл
    set({ dataMode, meta: null, cycleIdx: null, selectedCell: null, focus: null });
  },
  setFocus: (focus) => set({ focus }),
  setTourOpen: (tourOpen) => set({ tourOpen }),
  login: (token, user) => {
    setToken(token);
    save("session", "sw.auth", { token, user });
    set({ token, user });
  },
  logout: () => {
    setToken(null);
    save("session", "sw.auth", null);
    set({ token: null, user: null, selectedCell: null });
  },
  setMeta: (meta) => set((s) => ({ meta, cycleIdx: s.cycleIdx ?? (meta.cycles.length ? meta.cycles.length - 1 : null) })),
  navigate: (path) => {
    if (path !== window.location.pathname) window.history.pushState({}, "", path);
    set({ path });
  },
  setCycleIdx: (cycleIdx) => set({ cycleIdx }),
  setShowStatus: (showStatus) => set({ showStatus }),
  setDataLayer: (dataLayer) => set({ dataLayer }),
  setShowEvents: (showEvents) => set({ showEvents }),
  setStatusFilter: (statusFilter) => set({ statusFilter }),
  selectCell: (selectedCell) => set({ selectedCell }),
}));

window.addEventListener("popstate", () => useStore.setState({ path: window.location.pathname }));

export function useT() {
  const lang = useStore((s) => s.lang);
  return (key: string, vars?: Record<string, string | number>) => translate(lang, key, vars);
}

export function currentCycle(s: Pick<State, "meta" | "cycleIdx">): string | null {
  if (!s.meta || s.cycleIdx === null) return null;
  return s.meta.cycles[s.cycleIdx] ?? null;
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
