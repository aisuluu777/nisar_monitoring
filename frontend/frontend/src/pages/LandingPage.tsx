import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { api, unwrap, type Summary } from "../api/client";
import { GlassPanel } from "../components/hud";
import { Term } from "../components/Term";
import { GIBS, GIBS_ATTRIBUTION, gibsUrl } from "../map/config";
import { prefersReducedMotion, useStore, useT, type User } from "../store";

function PreviewMap({ districtId, bbox }: { districtId: string; bbox: number[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      interactive: false,
      attributionControl: { compact: true, customAttribution: GIBS_ATTRIBUTION },
      style: {
        version: 8,
        sources: { gibs: { type: "raster", tiles: [gibsUrl(GIBS.relief)], tileSize: 256, maxzoom: GIBS.relief.maxzoom } },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#011425" } },
          { id: "gibs", type: "raster", source: "gibs", paint: { "raster-opacity": 0.8, "raster-brightness-max": 0.7 } },
        ],
      },
      bounds: [bbox[0], bbox[1], bbox[2], bbox[3]],
      fitBoundsOptions: { padding: 24 },
    });
    map.on("load", async () => {
      try {
        const r = await api.GET("/api/v1/districts/{district_id}/outline", { params: { path: { district_id: districtId } } });
        const f = unwrap(r) as unknown as GeoJSON.Feature;
        map.addSource("outline", { type: "geojson", data: f });
        map.addLayer({ id: "o-fill", type: "fill", source: "outline", paint: { "fill-color": "#19E3FF", "fill-opacity": 0.12 } });
        map.addLayer({ id: "o-line", type: "line", source: "outline", paint: { "line-color": "#19E3FF", "line-width": 2 } });
      } catch {
        /* контур не загрузился — остаётся подложка */
      }
    });
    return () => map.remove();
  }, [districtId, bbox]);
  return <div ref={ref} className="map" aria-hidden="true" />;
}

const Satellite = () => (
  <svg width="120" height="96" viewBox="0 0 120 96" aria-hidden="true">
    <g stroke="#19E3FF" fill="none" strokeWidth="1.6">
      <circle className="ring" cx="60" cy="70" r="18" />
      <circle className="ring r2" cx="60" cy="70" r="18" />
      <circle className="ring r3" cx="60" cy="70" r="18" />
    </g>
    <g transform="translate(46 8)">
      <rect x="10" y="8" width="8" height="12" rx="2" fill="#0b3a57" stroke="#19E3FF" />
      <rect x="-6" y="10" width="14" height="8" fill="#0e4f75" stroke="#19E3FF" />
      <rect x="20" y="10" width="14" height="8" fill="#0e4f75" stroke="#19E3FF" />
      <path d="M14 20 L14 30" stroke="#19E3FF" />
    </g>
    <path d="M10 88 L36 62 L52 74 L70 54 L110 88 Z" fill="rgba(25,227,255,.12)" stroke="#9FC3D6" strokeLinejoin="round" />
  </svg>
);
const NormBand = () => (
  <svg width="120" height="96" viewBox="0 0 120 96" aria-hidden="true">
    <path d="M6 40 C30 34, 60 46, 114 38 L114 62 C60 70, 30 58, 6 64 Z" fill="rgba(25,227,255,.14)" />
    <path d="M6 52 C20 50, 32 54, 46 50 S 70 54, 80 50 S 96 62, 114 82" fill="none" stroke="#19E3FF" strokeWidth="2.2" strokeLinecap="round" />
    <circle cx="114" cy="82" r="4" fill="#FF6B5B" />
  </svg>
);
const TaskList = () => (
  <svg width="120" height="96" viewBox="0 0 120 96" aria-hidden="true">
    {[0, 1, 2].map((i) => (
      <g key={i} transform={`translate(10 ${10 + i * 28})`}>
        <rect width="100" height="22" rx="6" fill="rgba(3,30,50,.9)" stroke="rgba(159,195,214,.3)" />
        <circle cx="12" cy="11" r="5" fill={i === 0 ? "#FF6B5B" : "#FFC94D"} />
        <rect x="24" y="8" width={i === 0 ? 60 : 44} height="6" rx="3" fill="#9FC3D6" opacity=".6" />
      </g>
    ))}
  </svg>
);

export function LandingPage() {
  const t = useT();
  const { meta, navigate, login, lang } = useStore();
  const [sum, setSum] = useState<Summary | null>(null);
  const did = meta?.district?.id;

  useEffect(() => {
    if (!did) return;
    api
      .GET("/api/v1/districts/{district_id}/summary", { params: { path: { district_id: did } } })
      .then(unwrap)
      .then(setSum)
      .catch(() => setSum(null));
  }, [did, meta?.data_mode]);

  async function story() {
    // Демо-история: вход под ролью администрации → экран «Сегодня» → обучение
    try {
      const acc = unwrap(await api.GET("/api/v1/auth/demo-accounts"));
      const a = acc.find((x) => x.role === "district_admin");
      if (!a) throw new Error("no account");
      const r = unwrap(await api.POST("/api/v1/auth/login", { body: { username: a.username, password: a.password } }));
      login(r.access_token, r.user as User);
      navigate("/today");
      useStore.getState().setTourOpen(true);
    } catch {
      navigate("/login");
    }
  }

  const d = meta?.district;
  const name = d ? (lang === "ky" ? d.name_ky : lang === "en" ? d.name_en ?? d.name_ru : d.name_ru) : "";
  const toCheck = sum?.counts ? (sum.counts.red ?? 0) + (sum.counts.yellow ?? 0) : null;
  const reduced = prefersReducedMotion();

  return (
    <div className="landing">
      <div className="land-inner">
        <section className="hero">
          <div>
            <div className="kicker">{t("land.kicker")}</div>
            <h1>{t("land.title")}</h1>
            <p className="sub">{t("land.sub")}</p>
            <div className="cta">
              <button className="btn primary lg" onClick={story}>
                ▶ {t("land.cta.story")}
              </button>
              <button className="btn lg" onClick={() => navigate("/login")}>
                {t("land.cta.login")}
              </button>
              <button className="btn lg ghost" onClick={() => navigate("/about")}>
                {t("land.cta.about")}
              </button>
            </div>
            <p className="honest">
              <span aria-hidden="true">ⓘ</span>
              {t("land.honest")}
            </p>
          </div>

          <GlassPanel accent className="preview" index="●" title={t("land.object")} label={t("land.object")}>
            <div className="ptitle">
              {!reduced && <span className="livedot" aria-hidden="true" />}
              {name}
            </div>
            <div className="pmap">{d && <PreviewMap districtId={d.id} bbox={d.bbox} />}</div>
            <div className="kpis-big">
              <div>
                <div className="v">{d?.area_km2 ? Math.round(d.area_km2) : "—"}</div>
                <div className="l">{t("land.kpi.area")}</div>
              </div>
              <div>
                <div className="v">{sum?.n_cells ?? "—"}</div>
                <div className="l">{t("land.kpi.cells")}</div>
              </div>
              <div>
                <div className="v small">{sum?.last_cycle ?? "—"}</div>
                <div className="l">{t("land.kpi.last")}</div>
              </div>
              <div>
                {toCheck !== null ? (
                  <div className={`v ${toCheck > 0 ? "warn" : ""}`}>{toCheck}</div>
                ) : (
                  <div className="v small">🔒 {t("land.kpi.locked")}</div>
                )}
                <div className="l">{t("land.kpi.check")}</div>
              </div>
            </div>
          </GlassPanel>
        </section>

        <section aria-label="3">
          <div className="steps3">
            <GlassPanel className="step3">
              <div className="ill">
                <Satellite />
              </div>
              <span className="n">01</span>
              <h3>{t("land.step1.t")}</h3>
              <p>{t("land.step1.d")}</p>
            </GlassPanel>
            <div className="flow" aria-hidden="true">
              <i />
            </div>
            <GlassPanel className="step3">
              <div className="ill">
                <NormBand />
              </div>
              <span className="n">02</span>
              <h3>{t("land.step2.t")}</h3>
              <p>{t("land.step2.d")}</p>
            </GlassPanel>
            <div className="flow" aria-hidden="true">
              <i />
            </div>
            <GlassPanel className="step3">
              <div className="ill">
                <TaskList />
              </div>
              <span className="n">03</span>
              <h3>{t("land.step3.t")}</h3>
              <p>{t("land.step3.d")}</p>
            </GlassPanel>
          </div>
        </section>

        <section>
          <h2 className="section-title">{t("land.why.t")}</h2>
          <div className="why3">
            <GlassPanel>
              <span aria-hidden="true" style={{ fontSize: 24 }}>☁</span>
              <h3>{t("land.why1.t")}</h3>
              <p>{t("land.why1.d")}</p>
            </GlassPanel>
            <GlassPanel>
              <span aria-hidden="true" style={{ fontSize: 24 }}>↕</span>
              <h3>{t("land.why2.t")}</h3>
              <p>
                <Term k="insar" /> · {t("land.why2.d")}
              </p>
            </GlassPanel>
            <GlassPanel>
              <span aria-hidden="true" style={{ fontSize: 24 }}>⇩</span>
              <h3>{t("land.why3.t")}</h3>
              <p>{t("land.why3.d")}</p>
            </GlassPanel>
          </div>
        </section>
      </div>
    </div>
  );
}
