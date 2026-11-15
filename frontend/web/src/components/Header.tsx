import type { ReactNode } from "react";
import { LANGS } from "../i18n";
import { useStore, useT } from "../store";
import { IconInfo, IconLogin, IconLogout, IconMap, IconSummary, IconSystem, Logo } from "./icons";

export type Route = { path: string; label: string; icon: ReactNode; roles: string[] };

const IconToday = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <rect x="4" y="5" width="16" height="15" rx="3" />
    <path d="M8 3v4M16 3v4M4 10h16M8 14h3M8 17h6" />
  </svg>
);
const IconHome = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 11l8-7 8 7v9H4z" />
    <path d="M10 20v-5h4v5" />
  </svg>
);

const IconRetro = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <path d="M4 12a8 8 0 1 0 2.3-5.6" />
    <path d="M4 4v4h4M12 8v4l3 2" />
  </svg>
);

export const ROUTES: Route[] = [
  { path: "/", label: "nav.home", icon: <IconHome />, roles: ["public"] },
  { path: "/today", label: "nav.today", icon: <IconToday />, roles: ["district_admin", "mchs"] },
  { path: "/map", label: "nav.map", icon: <IconMap />, roles: ["district_admin", "mchs"] },
  { path: "/retro", label: "nav.retro", icon: <IconRetro />, roles: ["district_admin", "mchs"] },
  { path: "/public", label: "nav.summary", icon: <IconSummary />, roles: ["public", "district_admin", "mchs", "researcher", "sysadmin"] },
  { path: "/about", label: "nav.about", icon: <IconInfo />, roles: ["public", "district_admin", "mchs", "researcher", "sysadmin"] },
  { path: "/system", label: "nav.system", icon: <IconSystem />, roles: ["sysadmin"] },
];

export function homeFor(role: string) {
  return role === "sysadmin" ? "/system" : role === "researcher" ? "/about" : role === "public" ? "/" : "/today";
}

export function ModeSwitch() {
  const t = useT();
  const { meta, dataMode, setDataMode } = useStore();
  const avail = meta?.available_modes ?? [];
  const cur = meta?.data_mode ?? dataMode ?? "demo";
  return (
    <div className="modesw" role="group" aria-label={t("mode.label")} data-tour="mode">
      <button
        className="real"
        aria-pressed={cur === "real"}
        disabled={!avail.includes("real")}
        title={avail.includes("real") ? t("mode.real") : t("mode.real_missing")}
        onClick={() => setDataMode("real")}
      >
        <span className="dot" aria-hidden="true" />
        <span className="long">{t("mode.real")}</span>
        <span className="short sr-only">S1</span>
      </button>
      <button className="demo" aria-pressed={cur === "demo"} disabled={!avail.includes("demo")} onClick={() => setDataMode("demo")}>
        <span className="dot" aria-hidden="true" />
        {t("mode.demo")}
      </button>
    </div>
  );
}

export function LangSwitch() {
  const t = useT();
  const { lang, setLang } = useStore();
  return (
    <div className="langsw" role="group" aria-label={t("nav.lang")} data-tour="lang">
      {LANGS.map((l) => (
        <button key={l} aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export function Header() {
  const t = useT();
  const { path, navigate, user, logout, setTourOpen } = useStore();
  const role = user?.role ?? "public";
  return (
    <header className="topbar">
      <button className="brand" onClick={() => navigate(homeFor(role))} aria-label="Slope Watch">
        <Logo />
        <span>
          <b>Slope Watch</b>
          <small>{t("app.subtitle")}</small>
        </span>
      </button>
      <nav className="nav" aria-label="Разделы" data-tour="nav">
        {ROUTES.filter((r) => r.roles.includes(role)).map((r) => (
          <button key={r.path} aria-current={path === r.path ? "page" : undefined} onClick={() => navigate(r.path)}>
            {r.icon}
            <span className="lbl">{t(r.label)}</span>
          </button>
        ))}
      </nav>
      <div className="right">
        <ModeSwitch />
        <LangSwitch />
        <button className="iconbtn" onClick={() => setTourOpen(true)} aria-label={t("help.open")} title={t("help.open")} data-tour="help">
          ?
        </button>
        {user ? (
          <>
            <span className="who">{user.display_name}</span>
            <button
              className="iconbtn"
              onClick={() => {
                logout();
                navigate("/");
              }}
              aria-label={t("nav.logout")}
              title={t("nav.logout")}
            >
              <IconLogout />
            </button>
          </>
        ) : (
          path !== "/login" && (
            <button className="btn sm primary" onClick={() => navigate("/login")}>
              <IconLogin /> {t("nav.login")}
            </button>
          )
        )}
      </div>
    </header>
  );
}

export function BottomNav() {
  const t = useT();
  const { path, navigate, user } = useStore();
  const role = user?.role ?? "public";
  return (
    <nav className="bottomnav" aria-label="Разделы">
      {ROUTES.filter((r) => r.roles.includes(role)).map((r) => (
        <button key={r.path} aria-current={path === r.path ? "page" : undefined} onClick={() => navigate(r.path)}>
          {r.icon}
          <span>{t(r.label)}</span>
        </button>
      ))}
    </nav>
  );
}
