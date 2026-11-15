import { useCallback, useEffect, useState } from "react";
import { api, unwrap, type CellCard as Card, type Reason, type SeriesOut } from "../api/client";
import { useStore, useT } from "../store";
import { ErrorBox, GlassPanel, Skeleton, SourceBadge, StatusChip, statusIcon } from "./hud";
import { LayerStack } from "./LayerStack";
import { SeriesChart } from "./SeriesChart";
import { Term } from "./Term";

const MAIN_RULES = ["valid_frac", "low_quality", "history", "disp_z", "persistence", "cluster", "precip_z", "soil_moisture_z", "veg_disturbance"];
const INFO_RULES = ["scene_offset", "weak_signal", "secondary_family"];

function fmtNum(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined) return "—";
  if (unit === "count" || unit === "cycles" || unit === "cells" || unit === "flag") return String(v);
  return Math.abs(v) < 10 ? v.toFixed(2) : v.toFixed(1);
}

function ReasonsTable({ reasons }: { reasons: Reason[] }) {
  const t = useT();
  const main = MAIN_RULES.map((r) => reasons.find((x) => x.rule === r)).filter(Boolean) as Reason[];
  const info = reasons.filter((r) => INFO_RULES.includes(r.rule));
  return (
    <>
      <table className="hud">
        <thead>
          <tr>
            <th>{t("card.rule")}</th>
            <th style={{ textAlign: "right" }}>{t("card.value")}</th>
            <th style={{ textAlign: "right" }}>{t("card.threshold")}</th>
            <th>{t("card.unit")}</th>
            <th aria-label="сработало" />
          </tr>
        </thead>
        <tbody>
          {main.map((r) => {
            const excluded = (r.details as { excluded?: string })?.excluded;
            return (
              <tr key={r.rule} className={r.triggered ? "hit" : ""}>
                <td>
                  {t(`rule.${r.rule}`)}
                  {excluded && (
                    <span className="small muted">
                      {" "}
                      · {t("card.excluded")}: {t(`excluded.${excluded}`)}
                    </span>
                  )}
                  {r.rule === "precip_z" && <span className="small muted"> · {r.family?.replace("SYNTHETIC-", "")}</span>}
                </td>
                <td className="num mono">{fmtNum(r.value as number | null, r.unit)}</td>
                <td className="num mono">
                  {r.threshold === null || r.threshold === undefined ? "—" : `${r.op.replace("|z|", "")} ${r.threshold}`}
                </td>
                <td className="mono small">{t(`unit.${r.unit}`)}</td>
                <td>
                  <span className={`tick ${r.triggered ? "on" : "off"}`} aria-label={r.triggered ? "сработало" : "не сработало"}>
                    {r.triggered ? "●" : "○"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {info.length > 0 && (
        <ul className="small muted" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
          {info.map((r) => (
            <li key={r.rule + (r.family ?? "")}>
              {t("card.info")}: {t(`rule.${r.rule}`)}
              {r.value !== null && r.value !== undefined ? ` — ${fmtNum(r.value as number, r.unit)} ${t(`unit.${r.unit}`)}` : ""}
              {r.rule === "secondary_family" && ` · ${r.family} · ${t("card.secondary")}`}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

type Steps = Card["steps"];

export function CellCard({ cellId, cycle, onClose, onSteps }: { cellId: string; cycle: string; onClose: () => void; onSteps?: (s: Steps | null) => void }) {
  const t = useT();
  const { lang, user } = useStore();
  const [card, setCard] = useState<Card | null>(null);
  const [series, setSeries] = useState<SeriesOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [c, s] = await Promise.all([
        api.GET("/api/v1/cells/{cell_id}", { params: { path: { cell_id: cellId }, query: { date: cycle, lang } } }).then(unwrap),
        api.GET("/api/v1/cells/{cell_id}/series", { params: { path: { cell_id: cellId } } }).then(unwrap),
      ]);
      setCard(c);
      setSeries(s);
      onSteps?.(c.steps);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [cellId, cycle, lang, onSteps]);

  useEffect(() => {
    setCard(null);
    setSent(null);
    load();
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handoff() {
    setBusy(true);
    try {
      unwrap(await api.POST("/api/v1/cells/{cell_id}/handoff", { params: { path: { cell_id: cellId } }, body: { comment, cycle } }));
      setSent(t("card.handoff_done"));
      setComment("");
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(verdict: "confirmed" | "false_alarm") {
    if (comment.trim().length < 3) {
      setSent(t("card.comment_required"));
      return;
    }
    setBusy(true);
    try {
      unwrap(await api.POST("/api/v1/cells/{cell_id}/decisions", { params: { path: { cell_id: cellId } }, body: { verdict, comment, cycle } }));
      setSent(t("common.sent"));
      setComment("");
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const primary = card?.passports.find((p) => p.family === card.family);

  return (
    <div className="drawer">
      <GlassPanel
        as="aside"
        accent
        index="02"
        title={`${t("card.title")} ${cellId.split("-").slice(-1)[0]}`}
        label={`${t("card.title")} ${cellId}`}
        headExtra={
          <button className="btn sm ghost" onClick={onClose} aria-label={t("card.close")}>
            ✕
          </button>
        }
      >
        <div className="scroll">
          {err && <ErrorBox message={err} onRetry={load} />}
          {!card && !err && <Skeleton rows={8} />}
          {card && (
            <>
              {/* 1. Статус и одна фраза «почему» */}
              <div className="card-top">
                <div className="row">
                  <StatusChip status={card.status} large />
                  <span className="mono small muted">
                    {t("card.cycle")} {card.cycle}
                  </span>
                </div>
                <p className="whyline">{card.bulletin.see[0]}</p>
                <div className="row small muted">
                  {card.cell.village ?? "—"} · <span className="mono">{card.cell.id.split("-").slice(-1)[0]}</span>
                  {primary && (
                    <SourceBadge source={primary.source} family={primary.family} date={primary.acq_end} maturity={primary.maturity} staleDays={card.stale_days} />
                  )}
                </div>
              </div>

              {/* 2. График с полосой нормы */}
              <section className="card-sec">
                <h3>
                  {t("card.series")} · <Term k="norm" />
                </h3>
                {series ? <SeriesChart data={series} cycle={card.cycle} /> : <Skeleton rows={5} />}
              </section>

              {/* 3. Что мы видим / Чего мы не знаем */}
              <section className="card-sec bulletin">
                <h3>
                  {t("card.explain")} · {t("card.mode.plain")}
                </h3>
                <div className="blk">
                  <h4>{t("card.see")}</h4>
                  {card.bulletin.see.slice(1).map((p, i) => (
                    <p key={i}>{p}</p>
                  ))}
                </div>
                <div className="blk unknown">
                  <h4>{t("card.unknown")}</h4>
                  {card.bulletin.unknown.map((p, i) => (
                    <p key={i}>{p}</p>
                  ))}
                </div>
                <div className="labels">
                  <span className="badge">{card.bulletin.generator === "template" ? t("card.template_label") : t("card.ai_label")}</span>
                  <span className="badge">{t("card.draft")}</span>
                  {card.bulletin.needs_native_review && <span className="badge stale">{t("card.ky_review")}</span>}
                </div>
              </section>

              {/* 4. Действие */}
              <section className="card-sec actions">
                <p className="small muted" style={{ margin: 0 }}>
                  {t("card.decision_hint")}
                </p>
                <label className="field">
                  {t("card.comment")}
                  <textarea className="input" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000} />
                </label>
                <div className="row">
                  {user?.role === "district_admin" && (
                    <button className="btn primary" disabled={busy} onClick={handoff}>
                      {t("card.handoff")}
                    </button>
                  )}
                  {user?.role === "mchs" && (
                    <>
                      <button className="btn primary" disabled={busy} onClick={() => decide("confirmed")}>
                        ✓ {t("card.confirm")}
                      </button>
                      <button className="btn" disabled={busy} onClick={() => decide("false_alarm")}>
                        ✕ {t("card.false_alarm")}
                      </button>
                    </>
                  )}
                </div>
                {sent && (
                  <span role="status" className="small" style={{ color: "var(--neon)" }}>
                    {sent}
                  </span>
                )}
                {(card.decisions.length > 0 || card.handoffs.length > 0) && (
                  <ul className="journal" aria-label={t("card.decisions")}>
                    {card.handoffs.map((h, i) => (
                      <li key={`h${i}`}>
                        <span className="mono small muted">{h.ts.slice(0, 16).replace("T", " ")}</span> · {t("card.handoffs")} · {h.user}
                        {h.comment && <div>{h.comment}</div>}
                      </li>
                    ))}
                    {card.decisions.map((d) => (
                      <li key={d.id}>
                        <span className="mono small muted">{d.created_at.slice(0, 16).replace("T", " ")}</span> ·{" "}
                        <b>{d.verdict === "confirmed" ? `✓ ${t("card.confirm")}` : `✕ ${t("card.false_alarm")}`}</b> · {d.user}
                        <div>{d.comment}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {/* 5. Технические детали — для специалиста */}
              <details className="spec">
                <summary>{t("card.details")}</summary>
                <div className="inner">
                  <section className="card-sec">
                    <h3>{t("card.reasons")}</h3>
                    <p className="small muted" style={{ margin: "0 0 6px" }}>
                      <Term k="los" /> · <Term k="coherence" /> · <Term k="mad" />
                    </p>
                    <ReasonsTable reasons={card.reasons} />
                  </section>
                  <section className="card-sec">
                    <h3>{t("card.history")}</h3>
                    <div className="history-strip">
                      {card.history.map((h) => (
                        <span key={h.date} className={`st-${h.status}`} title={`${h.date}: ${t(`status.${h.status}`)}`}>
                          <b>{statusIcon(h.status)}</b>
                        </span>
                      ))}
                    </div>
                  </section>
                  <section className="card-sec bulletin">
                    <div className="blk basis">
                      <h4>{t("card.basis")}</h4>
                      {card.bulletin.basis.map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                    </div>
                  </section>
                  <section className="card-sec">
                    <h3>{t("card.layers")}</h3>
                    <LayerStack />
                  </section>
                  <section className="card-sec">
                    <h3>{t("card.terrain")}</h3>
                    <p className="mono small muted" style={{ margin: 0 }}>
                      {t("terrain.line", {
                        elev: card.cell.elev_mean.toFixed(0),
                        slope: card.cell.slope_mean.toFixed(1),
                        smax: card.cell.slope_max.toFixed(1),
                        aspect: card.cell.aspect.toFixed(0),
                        forest: (card.cell.frac_forest * 100).toFixed(0),
                        water: (card.cell.frac_water * 100).toFixed(0),
                        built: (card.cell.frac_built * 100).toFixed(0),
                      })}
                    </p>
                  </section>
                  <details className="passport">
                    <summary>
                      {t("card.passport")} · <Term k="provisional" />
                    </summary>
                    <div className="pp">
                      {card.passports.map((p) => (
                        <div key={p.product_id}>
                          <SourceBadge source={p.source} family={p.family} date={p.acq_end} maturity={p.maturity} />
                          <br />
                          {p.name} · v{p.version} · pipeline {p.pipeline_version}
                          <br />
                          {p.acq_start} → {p.acq_end} · {p.license}
                          {p.url && (
                            <>
                              <br />
                              <a href={p.url} target="_blank" rel="noreferrer">
                                {p.url.length > 70 ? p.url.slice(0, 70) + "…" : p.url}
                              </a>
                            </>
                          )}
                          <br />
                          {Object.entries(p.processing_params)
                            .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
                            .join(" · ")}
                        </div>
                      ))}
                    </div>
                  </details>
                </div>
              </details>
            </>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}
