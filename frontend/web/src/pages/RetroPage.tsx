import { useEffect, useState } from "react";
import { api, unwrap } from "../api/client";
import { ErrorBox, GlassPanel, Skeleton, StatusChip, statusIcon } from "../components/hud";
import { useStore, useT } from "../store";

type Tl = { date: string; worst: "green" | "yellow" | "red" | "grey"; own: string | null; grey_share: number };
type Ev = {
  event_id: number; date: string; source: string; description: string; cell_id: string | null; result: "noticed" | "missed" | "no_cell";
  lead_days: number | null; reason: string | null; first_alarm?: string; timeline: Tl[]; lon: number; lat: number;
};
type Retro = { events: Ev[]; false_alarms: { alerts_far_from_events: number; evaluated_statuses: number; share: number } | null; period: (string | null)[] };

export function RetroPage() {
  const t = useT();
  const { navigate, setFocus, meta } = useStore();
  const [data, setData] = useState<Retro | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    setErr(null);
    api.GET("/api/v1/retro").then(unwrap).then((r) => setData(r as unknown as Retro)).catch((e) => setErr((e as Error).message));
  };
  useEffect(load, [meta?.data_mode]);

  return (
    <div className="page">
      <div className="page-inner">
        <h1 className="page-title">{t("retro.title")}</h1>
        <GlassPanel accent>
          <p className="panel-body" style={{ margin: 0, paddingTop: 14 }}>
            {t("retro.intro")}
          </p>
        </GlassPanel>
        {err && <ErrorBox message={err} onRetry={load} />}
        {!data && !err && <Skeleton rows={6} />}
        {data && data.events.length === 0 && (
          <GlassPanel>
            <p className="panel-body" style={{ margin: 0, paddingTop: 14 }}>
              {t("retro.none")}
            </p>
          </GlassPanel>
        )}
        {data?.events.map((e) => (
          <GlassPanel key={e.event_id} title={`${t("retro.event")} · ${e.date}`} index="⚑">
            <div className="panel-body" style={{ display: "grid", gap: 10 }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <span className={`retro-res ${e.result}`}>
                  {e.result === "noticed" ? `✓ ${t("retro.noticed", { n: e.lead_days ?? 0 })}` : `✕ ${t("retro.missed")}`}
                </span>
                <span className="small muted">
                  {e.source} · {e.description}
                </span>
              </div>
              {e.result !== "noticed" && e.reason && <p className="small" style={{ margin: 0 }}>{t(`retro.reason.${e.reason}`)}</p>}
              <div>
                <div className="small muted" style={{ marginBottom: 4 }}>
                  {t("retro.timeline")}
                </div>
                <div className="history-strip retro-strip">
                  {e.timeline.map((x) => (
                    <span key={x.date} className={`st-${x.worst}`} title={`${x.date}: ${t(`status.${x.worst}`)}`}>
                      <b>{statusIcon(x.worst)}</b>
                    </span>
                  ))}
                  <span className="retro-event" title={e.date}>⚑</span>
                </div>
                <div className="mono small muted" style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{e.timeline[0]?.date}</span>
                  <span>{e.date}</span>
                </div>
              </div>
              {e.cell_id && (
                <div>
                  <button
                    className="btn sm"
                    onClick={() => {
                      setFocus({ lon: e.lon, lat: e.lat, id: e.cell_id! });
                      navigate("/map");
                    }}
                  >
                    {t("nav.map")} → {e.cell_id.split("-").slice(-1)[0]}
                  </button>
                </div>
              )}
            </div>
          </GlassPanel>
        ))}
        {data?.false_alarms && (
          <GlassPanel>
            <p className="panel-body" style={{ margin: 0, paddingTop: 14 }}>
              <StatusChip status="yellow" />{" "}
              {t("retro.false", {
                a: data.false_alarms.alerts_far_from_events,
                t: data.false_alarms.evaluated_statuses,
                p: (data.false_alarms.share * 100).toFixed(1),
              })}
            </p>
          </GlassPanel>
        )}
      </div>
    </div>
  );
}
