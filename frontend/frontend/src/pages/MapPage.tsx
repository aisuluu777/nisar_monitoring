import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, fetchCells, fetchEvents, unwrap, type CellCard as Card, type CellsFC, type SourceInfo, type StatusCode } from "../api/client";
import { CellCard } from "../components/CellCard";
import { ErrorBox, GlassPanel, Skeleton, SourceBadge, StatusChip, Stepper } from "../components/hud";
import { RAMPS, rampGradient } from "../map/config";
import { MapView } from "../map/MapView";
import { currentCycle, useStore, useT, type DataLayer } from "../store";

const ORDER: StatusCode[] = ["red", "yellow", "grey", "green"];
/** Семейство продукта для бейджа слоя: ищем по ключевому слову в имени семейства. */
const LAYER_KEY: Record<Exclude<DataLayer, "none" | "relief">, string[]> = {
  disp: [],
  sm: ["SME2"],
  precip: ["POWER", "IMERG"],
  veg: ["DIST"],
};

function Legend({ layer, showStatus }: { layer: DataLayer; showStatus: boolean }) {
  const t = useT();
  if (layer === "none") return null;
  const ramp = layer === "relief" && showStatus ? RAMPS.relief_grey : RAMPS[layer];
  const [a, b] = [ramp.stops[0][0], ramp.stops[ramp.stops.length - 1][0]];
  return (
    <div className="legend">
      <span className="small muted">{t(`legend.${layer}`)}</span>
      <div className="bar" style={{ background: rampGradient(ramp) }} />
      <div className="ticks">
        <span>{ramp.fmt(a)}</span>
        {layer === "disp" && <span>0</span>}
        <span>{ramp.fmt(b)}</span>
      </div>
      {layer === "relief" && showStatus && <span className="small muted">{t("legend.relief_grey")}</span>}
    </div>
  );
}

export function MapPage() {
  const t = useT();
  const st = useStore();
  const { meta, user, cycleIdx, selectedCell, statusFilter, showStatus, dataLayer, showEvents } = st;
  const cycle = currentCycle(st);
  const cache = useRef(new Map<string, CellsFC>());
  const [data, setData] = useState<CellsFC | null>(null);
  const [changed, setChanged] = useState<string[]>([]);
  const [events, setEvents] = useState<GeoJSON.FeatureCollection | null>(null);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [steps, setSteps] = useState<Card["steps"] | null>(null);
  const [layersOpen, setLayersOpen] = useState(window.innerWidth > 760);

  const get = useCallback(async (d: string) => {
    const hit = cache.current.get(d);
    if (hit) return hit;
    const fc = await fetchCells(d);
    cache.current.set(d, fc);
    return fc;
  }, []);

  useEffect(() => {
    if (!cycle || !meta) return;
    let alive = true;
    setErr(null);
    get(cycle)
      .then(async (fc) => {
        if (!alive) return;
        setData(fc);
        const i = meta.cycles.indexOf(cycle);
        if (i > 0) {
          const prev = await get(meta.cycles[i - 1]);
          const ps = new Map(prev.features.map((f) => [f.id, f.properties.status]));
          if (alive) setChanged(fc.features.filter((f) => ps.get(f.id) && ps.get(f.id) !== f.properties.status && f.properties.status !== "green").map((f) => f.id));
        }
        // подгружаем соседние циклы заранее — для плавного ползунка
        if (i + 1 < meta.cycles.length) get(meta.cycles[i + 1]).catch(() => undefined);
      })
      .catch((e) => alive && setErr((e as Error).message));
    return () => {
      alive = false;
    };
  }, [cycle, meta, get]);

  useEffect(() => {
    fetchEvents().then(setEvents).catch(() => setEvents(null));
    api.GET("/api/v1/sources").then(unwrap).then(setSources).catch(() => setSources([]));
  }, []);

  const counts = useMemo(() => {
    const c: Record<StatusCode, number> = { green: 0, yellow: 0, red: 0, grey: 0 };
    data?.features.forEach((f) => c[f.properties.status]++);
    return c;
  }, [data]);

  const attention = useMemo(
    () =>
      (data?.features ?? [])
        .filter((f) => f.properties.status === "red" || f.properties.status === "yellow")
        .sort((a, b) => (a.properties.status === b.properties.status ? Math.abs(b.properties.disp_z ?? 0) - Math.abs(a.properties.disp_z ?? 0) : a.properties.status === "red" ? -1 : 1))
        .slice(0, 60),
    [data],
  );

  const onClose = useCallback(() => {
    st.selectCell(null);
    setSteps(null);
  }, [st]);

  if (!meta) return <Skeleton rows={6} />;
  const years = [...new Set(meta.cycles.map((c) => c.slice(0, 4)))];
  const sourceFor = (fam: string) => sources.find((s) => s.family === fam);
  const primary = sourceFor(meta.primary_family ?? "");
  const layerSource = (l: DataLayer) =>
    l === "none" || l === "relief" ? undefined : l === "disp" ? primary : sources.find((s) => LAYER_KEY[l].some((k) => s.family.includes(k)));

  return (
    <>
      <MapView data={data} bbox={meta.district?.bbox ?? null} events={events} changed={changed} />

      <div className="ov ov-counters">
        <GlassPanel accent index="01" title={t("map.counters")} stagger={0} style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div className="panel-body" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div className="counters">
              {ORDER.map((s) => (
                <button
                  key={s}
                  className="counter"
                  aria-pressed={statusFilter === s}
                  title={t("map.filter_hint")}
                  onClick={() => st.setStatusFilter(statusFilter === s ? null : s)}
                >
                  <StatusChip status={s} />
                  <span className="n">{data ? counts[s] : "…"}</span>
                </button>
              ))}
            </div>
            {err && <ErrorBox message={err} />}
            {!data && !err && <Skeleton rows={3} />}
            {attention.length > 0 && (
              <nav className="attention" aria-label={t("map.attention")}>
                <ul>
                  {attention.map((f) => (
                    <li key={f.id}>
                      <button aria-current={selectedCell === f.id} onClick={() => st.selectCell(f.id)}>
                        <StatusChip status={f.properties.status} />
                        <span>
                          <span className="cid">{f.id.split("-").slice(-1)[0]}</span>
                          <br />
                          <span className="small muted">{f.properties.village}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </nav>
            )}
          </div>
        </GlassPanel>
      </div>

      <div className={`ov ov-layers ${layersOpen ? "" : "collapsed"}`}>
        <GlassPanel
          index="03"
          title={t("map.layers")}
          stagger={1}
          headExtra={
            <button className="btn sm ghost" onClick={() => setLayersOpen(!layersOpen)} aria-expanded={layersOpen} aria-label={t("map.layers")}>
              {layersOpen ? "–" : "+"}
            </button>
          }
        >
          <div className="panel-body">
            <label className="layer-row">
              <input type="checkbox" checked={showStatus} onChange={(e) => st.setShowStatus(e.target.checked)} />
              {t("map.layer.status")}
            </label>
            {showStatus && (
              <div className="legend">
                <div className="status-legend">
                  {(["green", "yellow", "red", "grey"] as StatusCode[]).map((s) => (
                    <StatusChip key={s} status={s} />
                  ))}
                </div>
              </div>
            )}
            {primary && (
              <div className="badges">
                <SourceBadge source={primary.source} family={primary.family} date={primary.last_date} maturity={primary.maturity} staleDays={primary.stale ? primary.age_days : null} />
              </div>
            )}
            <hr style={{ border: 0, borderTop: "1px solid var(--neon-dim)", margin: "10px 0" }} />
            {(["none", "disp", "sm", "precip", "veg", "relief"] as DataLayer[]).map((l) => (
              <label className="layer-row" key={l}>
                <input type="radio" name="data-layer" checked={dataLayer === l} onChange={() => st.setDataLayer(l)} />
                {t(`map.layer.${l}`)}
              </label>
            ))}
            <Legend layer={dataLayer} showStatus={showStatus} />
            {(() => {
              const s = layerSource(dataLayer);
              return s ? (
                <div className="badges">
                  <SourceBadge source={s.source} family={s.family} date={s.last_date} maturity={s.maturity} staleDays={s.stale ? s.age_days : null} />
                </div>
              ) : null;
            })()}
            {events && (
              <label className="layer-row" style={{ marginTop: 6 }}>
                <input type="checkbox" checked={showEvents} onChange={(e) => st.setShowEvents(e.target.checked)} />
                {t("map.layer.events")} ({events.features.length})
              </label>
            )}
            <p className="small muted" style={{ margin: "6px 0 0" }}>
              {t("map.basemap")}
            </p>
          </div>
        </GlassPanel>
      </div>

      {selectedCell && steps && (
        <div className="ov ov-stepper with-drawer">
          <GlassPanel stagger={0} label={t("step.status")}>
            <Stepper steps={steps} />
          </GlassPanel>
        </div>
      )}

      <div className={`ov ov-cycle ${selectedCell ? "with-drawer" : ""}`}>
        <GlassPanel stagger={2} label={t("map.cycle")}>
          <div className="cycle-bar">
            <button className="btn sm" aria-label={t("map.prev")} disabled={!cycleIdx} onClick={() => st.setCycleIdx(Math.max(0, (cycleIdx ?? 0) - 1))}>
              ‹
            </button>
            <div>
              <div className="caps muted" style={{ textAlign: "center" }}>
                {t("map.cycle")} · <span className="date">{cycle}</span>
              </div>
              <input
                type="range"
                min={0}
                max={meta.cycles.length - 1}
                value={cycleIdx ?? 0}
                onChange={(e) => st.setCycleIdx(Number(e.target.value))}
                aria-label={t("map.cycle")}
                aria-valuetext={cycle ?? ""}
              />
            </div>
            <button
              className="btn sm"
              aria-label={t("map.next")}
              disabled={cycleIdx === meta.cycles.length - 1}
              onClick={() => st.setCycleIdx(Math.min(meta.cycles.length - 1, (cycleIdx ?? 0) + 1))}
            >
              ›
            </button>
            <div className="years">
              {years.map((y) => (
                <span key={y}>{y}</span>
              ))}
            </div>
          </div>
        </GlassPanel>
      </div>

      {selectedCell && cycle && user && <CellCard key={selectedCell} cellId={selectedCell} cycle={cycle} onClose={onClose} onSteps={setSteps} />}
    </>
  );
}
