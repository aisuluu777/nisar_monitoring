import { useEffect, useState, type ReactNode } from "react";
import { ApiError, api, setUnauthorizedHandler, unwrap } from "./api/client";
import { ErrorBox, Skeleton } from "./components/hud";
import { BottomNav, Header, ROUTES, homeFor } from "./components/Header";
import { Tour } from "./components/Tour";
import { AboutPage, SummaryPage, SystemPage, TypographyPage } from "./pages/InfoPages";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { MapPage } from "./pages/MapPage";
import { Story } from "./components/Story";
import { TodayPage } from "./pages/TodayPage";
import { useStore, useT } from "./store";

const FREE_PATHS = ["/login", "/dev/typography"];

export function App() {
  const t = useT();
  const { path, meta, setMeta, user, navigate, logout, lang, dataMode, setDataMode } = useStore();
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      logout();
      navigate("/login");
    });
  }, [logout, navigate]);

  // meta перезагружается при смене режима данных (реальные / демо)
  useEffect(() => {
    if (meta) return;
    setErr(null);
    api
      .GET("/api/v1/meta")
      .then(unwrap)
      .then(setMeta)
      .catch((e) => {
        // сохранённый режим больше недоступен (например, снимок удалён) → режим по умолчанию
        if (e instanceof ApiError && e.status === 409 && dataMode) {
          try {
            window.localStorage.removeItem("sw.mode");
          } catch {
            /* ignore */
          }
          setDataMode(dataMode === "real" ? "demo" : "real");
          return;
        }
        setErr((e as Error).message);
      });
  }, [meta, setMeta, dataMode, setDataMode]);

  const role = user?.role ?? "public";
  useEffect(() => {
    if (FREE_PATHS.includes(path)) return;
    const r = ROUTES.find((x) => x.path === path);
    if (!r || !r.roles.includes(role)) navigate(homeFor(role));
  }, [path, role, navigate]);

  let page: ReactNode;
  if (err)
    page = (
      <div className="page">
        <ErrorBox message={err} onRetry={() => window.location.reload()} />
      </div>
    );
  else if (!meta)
    page = (
      <div className="page">
        <Skeleton rows={6} />
      </div>
    );
  else if (path === "/") page = <LandingPage />;
  else if (path === "/login") page = <LoginPage />;
  else if (path === "/today" && (role === "district_admin" || role === "mchs")) page = <TodayPage />;
  else if (path === "/map" && (role === "district_admin" || role === "mchs")) page = <MapPage />;
  else if (path === "/public") page = <SummaryPage />;
  else if (path === "/about") page = <AboutPage />;
  else if (path === "/system" && role === "sysadmin") page = <SystemPage />;
  else if (path === "/dev/typography") page = <TypographyPage />;
  else
    page = (
      <div className="page">
        <Skeleton rows={4} />
      </div>
    );

  return (
    <>
      <div className="app-bg" aria-hidden="true" />
      <div className="shell2">
        {meta?.synthetic ? (
          <div className="demo-banner" role="note">
            {t("demo.banner")}
          </div>
        ) : (
          <div />
        )}
        <Header />
        <main key={meta?.data_mode ?? "none"}>{page}</main>
        <footer className="footer">{t("footer.disclaimer")}</footer>
        <BottomNav />
      </div>
      <Tour />
      <Story />
    </>
  );
}
