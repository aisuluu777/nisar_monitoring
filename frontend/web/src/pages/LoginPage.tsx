import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, unwrap } from "../api/client";
import { homeFor } from "../components/Header";
import { GlassPanel } from "../components/hud";
import { GIBS, GIBS_ATTRIBUTION, gibsUrl } from "../map/config";
import { prefersReducedMotion, useStore, useT, type User } from "../store";

type Demo = { username: string; display_name: string; role: string; password: string };

function Globe() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      interactive: false,
      attributionControl: { compact: true, customAttribution: GIBS_ATTRIBUTION },
      style: {
        version: 8,
        projection: { type: "globe" },
        sources: { gibs: { type: "raster", tiles: [gibsUrl(GIBS.globe)], tileSize: 256, maxzoom: GIBS.globe.maxzoom } },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#011425" } },
          { id: "gibs", type: "raster", source: "gibs", paint: { "raster-opacity": 0.85, "raster-saturation": -0.35, "raster-brightness-max": 0.75 } },
        ],
      },
      center: [60, 30],
      zoom: 2.2,
    });
    let raf = 0;
    if (!prefersReducedMotion()) {
      let lon = 60;
      const spin = () => {
        lon = (lon + 0.04) % 360;
        map.jumpTo({ center: [lon, 30] });
        raf = requestAnimationFrame(spin);
      };
      map.on("load", () => (raf = requestAnimationFrame(spin)));
    }
    return () => {
      cancelAnimationFrame(raf);
      map.remove();
    };
  }, []);
  return <div ref={ref} className="login-globe" aria-hidden="true" />;
}

export function LoginPage() {
  const t = useT();
  const { login, navigate, meta } = useStore();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<Demo[]>([]);

  useEffect(() => {
    // демо-база или локальный снимок для хакатона; сервер сам решает, можно ли показывать
    api.GET("/api/v1/auth/demo-accounts").then(unwrap).then(setDemo).catch(() => setDemo([]));
  }, [meta?.data_mode]);

  async function submit(u: string, p: string) {
    setBusy(true);
    setErr(null);
    try {
      const r = unwrap(await api.POST("/api/v1/auth/login", { body: { username: u, password: p } }));
      login(r.access_token, r.user as User);
      navigate(homeFor(r.user.role));
    } catch {
      setErr(t("login.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Globe />
      <div className="login-wrap">
        <div className="login-card">
          <GlassPanel accent index="00" title={t("app.title")}>
            <div className="panel-body" style={{ display: "grid", gap: 14 }}>
              <p className="muted" style={{ margin: 0 }}>
                {t("app.subtitle")}
              </p>
              <form
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  submit(username, password);
                }}
              >
                <h2 style={{ fontSize: 18 }}>{t("login.title")}</h2>
                <label className="field">
                  {t("login.username")}
                  <input className="input" autoComplete="username" value={username} onChange={(e) => setU(e.target.value)} required />
                </label>
                <label className="field">
                  {t("login.password")}
                  <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setP(e.target.value)} required />
                </label>
                {err && (
                  <div role="alert" style={{ color: "#ffb0a6" }}>
                    {err}
                  </div>
                )}
                <button className="btn primary" type="submit" disabled={busy}>
                  {t("login.submit")}
                </button>
              </form>
              {demo.length > 0 && (
                <div style={{ display: "grid", gap: 8 }}>
                  <span className="caps muted">{t("login.demo")}</span>
                  <div className="demo-accounts">
                    {demo.map((d) => (
                      <button key={d.username} className="btn sm" disabled={busy} onClick={() => submit(d.username, d.password)}>
                        {t(`role.${d.role}`)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="login-links">
                <button className="btn sm ghost" onClick={() => navigate("/")}>
                  ← {t("nav.home")}
                </button>
                <button className="btn sm ghost" onClick={() => navigate("/public")}>
                  {t("login.public")}
                </button>
                <button className="btn sm ghost" onClick={() => navigate("/about")}>
                  {t("login.about")}
                </button>
              </div>
            </div>
          </GlassPanel>
        </div>
      </div>
    </>
  );
}
