import { useEffect, useMemo, useState } from "react";
import { api, unwrap, type SourceInfo, type StatusCode, type Summary } from "../api/client";
import { ErrorBox, GlassPanel, Skeleton, SourceBadge, StatusChip } from "../components/hud";
import { translateList } from "../i18n";
import { STATUS_COLORS } from "../map/config";
import { useStore, useT } from "../store";

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = () => {
    setErr(null);
    fn().then(setData).catch((e) => setErr((e as Error).message));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(run, deps);
  return { data, err, retry: run };
}

/** Сводка района: публичная версия показывает только агрегаты. */
export function SummaryPage() {
  const t = useT();
  const meta = useStore((s) => s.meta);
  const did = meta?.district?.id;
  const { data, err, retry } = useLoad<Summary | null>(
    () => (did ? api.GET("/api/v1/districts/{district_id}/summary", { params: { path: { district_id: did } } }).then(unwrap) : Promise.resolve(null)),
    [did],
  );
  const lang = useStore((s) => s.lang);
  const max = useMemo(() => Math.max(1, ...(data?.dynamics ?? []).map((d) => d.counts.red + d.counts.yellow)), [data]);
  return (
    <div className="page">
      <div className="page-inner">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h1 className="page-title">{t("summary.title")}</h1>
        </div>
        {err && <ErrorBox message={err} onRetry={retry} />}
        {!data && !err && <Skeleton rows={6} />}
        {data && (
          <>
            <GlassPanel index="01" title={lang === "ky" ? data.district.name_ky : data.district.name_ru}>
              <div className="panel-body kpis">
                <div className="kpi">
                  <div className="v">{data.n_cells}</div>
                  <div className="l">{t("summary.cells")}</div>
                </div>
                <div className="kpi">
                  <div className="v">{data.last_cycle ?? "—"}</div>
                  <div className="l">{t("summary.last_cycle")}</div>
                </div>
                <div className="kpi">
                  <div className="v">
                    {data.data_age_days ?? "—"} <span className="small">{t("summary.days")}</span>
                  </div>
                  <div className="l">{t("summary.age")}</div>
                </div>
              </div>
            </GlassPanel>
            {!data.levels_visible && (
              <GlassPanel index="02" title={t("map.counters")} stagger={1}>
                <p className="panel-body" style={{ margin: 0 }}>
                  {t("summary.levels_hidden")}
                </p>
              </GlassPanel>
            )}
            {data.levels_visible && data.counts && (
              <div className="grid-2">
                <GlassPanel index="02" title={t("map.counters")} stagger={1}>
                  <div className="panel-body" style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
                    <Donut counts={data.counts as Record<StatusCode, number>} />
                    <div style={{ display: "grid", gap: 6 }}>
                      {(["red", "yellow", "grey", "green"] as StatusCode[]).map((s) => (
                        <div key={s} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                          <StatusChip status={s} />
                          <span className="mono">{data.counts![s]}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </GlassPanel>
                <GlassPanel index="03" title={t("summary.dynamics")} stagger={2}>
                  <div className="panel-body">
                    <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 120 }} role="img" aria-label={t("summary.dynamics")}>
                      {(data.dynamics ?? []).map((d) => (
                        <div key={d.date} title={`${d.date}: ▲${d.counts.red} !${d.counts.yellow}`} style={{ flex: 1, display: "flex", flexDirection: "column-reverse" }}>
                          <span style={{ height: (d.counts.red / max) * 110, background: STATUS_COLORS.red }} />
                          <span style={{ height: (d.counts.yellow / max) * 110, background: STATUS_COLORS.yellow, opacity: 0.85 }} />
                        </div>
                      ))}
                    </div>
                    <div className="small muted mono" style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>{data.dynamics?.[0]?.date}</span>
                      <span>{data.dynamics?.[data.dynamics.length - 1]?.date}</span>
                    </div>
                  </div>
                </GlassPanel>
              </div>
            )}
            <GlassPanel index="04" title={t("summary.villages")} stagger={3}>
              <p className="panel-body" style={{ margin: 0 }}>
                {(data.villages ?? []).join(" · ")}
              </p>
            </GlassPanel>
          </>
        )}
      </div>
    </div>
  );
}

function Donut({ counts }: { counts: Record<StatusCode, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  const r = 42;
  const c = 2 * Math.PI * r;
  return (
    <svg width="120" height="120" viewBox="0 0 120 120" role="img" aria-label="Доли статусов">
      {(["red", "yellow", "grey", "green"] as StatusCode[]).map((s) => {
        const len = (counts[s] / total) * c;
        const el = (
          <circle key={s} cx="60" cy="60" r={r} fill="none" stroke={STATUS_COLORS[s]} strokeWidth="14" strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-acc} transform="rotate(-90 60 60)" />
        );
        acc += len;
        return el;
      })}
      <text x="60" y="65" textAnchor="middle" fill="#E6F6FF" fontFamily="JetBrains Mono" fontSize="16">
        {total}
      </text>
    </svg>
  );
}

export function AboutPage() {
  const t = useT();
  const lang = useStore((s) => s.lang);
  const user = useStore((s) => s.user);
  const meta = useStore((s) => s.meta);
  const { data, err, retry } = useLoad<SourceInfo[]>(() => api.GET("/api/v1/sources").then(unwrap), []);
  const origin = window.location.origin;
  return (
    <div className="page">
      <div className="page-inner">
        <h1 className="page-title">{t("about.title")}</h1>
        <div className="grid-2">
          <GlassPanel index="01" title={t("about.does")}>
            <p className="panel-body" style={{ margin: 0 }}>
              {t("about.does_text")}
            </p>
          </GlassPanel>
          <GlassPanel index="02" title={t("about.not_do")} stagger={1}>
            <ul className="panel-body" style={{ margin: 0, paddingLeft: 32 }}>
              {translateList(lang, "about.not_do_items").map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </GlassPanel>
        </div>
        <GlassPanel index="03" title={t("about.sources")} stagger={2}>
          <div className="panel-body" style={{ overflowX: "auto" }}>
            {err && <ErrorBox message={err} onRetry={retry} />}
            {!data && !err && <Skeleton rows={5} />}
            {data && (
              <table className="hud">
                <thead>
                  <tr>
                    <th>{t("common.source")}</th>
                    <th>{t("about.period")}</th>
                    <th style={{ textAlign: "right" }}>{t("about.products")}</th>
                    <th>{t("about.license")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((s) => (
                    <tr key={s.family}>
                      <td>
                        <SourceBadge source={s.source} family={s.family} date={s.last_date} maturity={s.maturity} staleDays={s.stale ? s.age_days : null} />
                        <div className="small muted">{s.name}</div>
                      </td>
                      <td className="mono small">
                        {s.first_date} → {s.last_date}
                      </td>
                      <td className="num mono">{s.products}</td>
                      <td className="small">{s.license}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </GlassPanel>
        <GlassPanel index="04" title={t("about.api")} stagger={3}>
          <div className="panel-body" style={{ display: "grid", gap: 8 }}>
            <p style={{ margin: 0 }}>{t("about.api_text")}</p>
            <pre className="mono small" style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all", color: "var(--text-2)" }}>
              {`curl -H "X-API-Key: <ключ>" ${origin}/api/v1/cells/<cell_id>/series\ncurl -H "X-API-Key: <ключ>" ${origin}/api/v1/cells/<cell_id>/products`}
            </pre>
            {user?.role === "researcher" && meta?.data_mode === "demo" && (
              <p className="small muted" style={{ margin: 0 }}>
                Демо-ключ (только синтетика): <span className="mono">sk_demo_synthetic_only_not_for_real_data</span>
              </p>
            )}
            <a href="/docs" target="_blank" rel="noreferrer">
              OpenAPI /docs
            </a>
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}

type Run = { id: number; started_at: string; status: string; new_products: number; message: string; mode: string };

export function SystemPage() {
  const t = useT();
  const health = useLoad(() => api.GET("/api/v1/health").then(unwrap), []);
  const runs = useLoad<Run[]>(() => api.GET("/api/v1/admin/pipeline-runs").then(unwrap) as Promise<Run[]>, []);
  return (
    <div className="page">
      <div className="page-inner">
        <h1 className="page-title">{t("system.title")}</h1>
        <GlassPanel index="01" title={t("system.health")}>
          <div className="panel-body">
            {health.err && <ErrorBox message={health.err} onRetry={health.retry} />}
            {health.data && (
              <div className="kpis">
                <div className="kpi">
                  <div className="v" style={{ color: health.data.status === "ok" ? "var(--neon)" : "var(--stale)" }}>
                    {health.data.status.toUpperCase()}
                  </div>
                  <div className="l">API</div>
                </div>
                <div className="kpi">
                  <div className="v">{health.data.last_cycle ?? "—"}</div>
                  <div className="l">{t("summary.last_cycle")}</div>
                </div>
                <div className="kpi">
                  <div className="v">{health.data.data_age_days ?? "—"}</div>
                  <div className="l">
                    {t("summary.age")}, {t("summary.days")}
                  </div>
                </div>
                <div className="kpi">
                  <div className="v">{health.data.pipeline_version}</div>
                  <div className="l">pipeline / analytics {health.data.analytics_version}</div>
                </div>
              </div>
            )}
          </div>
        </GlassPanel>
        <GlassPanel index="02" title={t("system.runs")} stagger={1}>
          <div className="panel-body" style={{ overflowX: "auto" }}>
            {runs.err && <ErrorBox message={runs.err} onRetry={runs.retry} />}
            {runs.data && (
              <table className="hud">
                <thead>
                  <tr>
                    <th>{t("system.started")}</th>
                    <th>{t("system.status")}</th>
                    <th style={{ textAlign: "right" }}>{t("system.new_products")}</th>
                    <th>{t("system.message")}</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.map((r) => (
                    <tr key={r.id}>
                      <td className="mono small">{r.started_at.slice(0, 19).replace("T", " ")}</td>
                      <td className="mono">
                        {r.mode} · {r.status}
                      </td>
                      <td className="num mono">{r.new_products}</td>
                      <td className="small">{r.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}

const KY = "ң Ң ө Ө ү Ү";
const SAMPLE = "Көңүл буруу · Түндүк боор · Өзгөн · Үч-Коргон · Ңң Өө Үү";

/** Проверка: есть ли глиф в шрифте (сравнение ширины с запасным шрифтом на canvas). */
function hasGlyph(font: string, ch: string) {
  const c = document.createElement("canvas").getContext("2d")!;
  const probe = (f: string) => {
    c.font = `40px ${f}`;
    return c.measureText(ch.repeat(4)).width;
  };
  return ["monospace", "serif"].some((fb) => Math.abs(probe(`"${font}", ${fb}`) - probe(fb)) > 0.5);
}

export function TypographyPage() {
  const t = useT();
  const [res, setRes] = useState<Record<string, Record<string, boolean>>>({});
  useEffect(() => {
    document.fonts.ready.then(async () => {
      for (const f of ["Exo 2", "JetBrains Mono"]) await document.fonts.load(`40px "${f}"`, KY);
      const out: Record<string, Record<string, boolean>> = {};
      for (const f of ["Exo 2", "JetBrains Mono"]) out[f] = Object.fromEntries(["ң", "ө", "ү", "Ң", "Ө", "Ү"].map((ch) => [ch, hasGlyph(f, ch)]));
      setRes(out);
    });
  }, []);
  return (
    <div className="page">
      <div className="page-inner">
        <h1 className="page-title">{t("typo.title")}</h1>
        {(["Exo 2", "JetBrains Mono"] as const).map((f, i) => (
          <GlassPanel key={f} index={`0${i + 1}`} title={f} stagger={i}>
            <div className="panel-body typo-sample" style={{ fontFamily: f === "Exo 2" ? "var(--font-head)" : "var(--font-mono)" }}>
              <span className="big">{KY}</span>
              <span>{SAMPLE}</span>
              <span style={{ fontWeight: 700 }}>{SAMPLE}</span>
              <span className="mono small">0123456789 · 1,25 см · 2026-11-08</span>
              <span className="small muted">
                {Object.keys(res[f] ?? {}).length === 0
                  ? "…"
                  : Object.entries(res[f])
                      .map(([ch, ok]) => `${ch} ${ok ? "✓ в шрифте" : "✗ подставлен запасной шрифт"}`)
                      .join(" · ")}
              </span>
            </div>
          </GlassPanel>
        ))}
        <p className="small muted">
          Если глифа нет в основном шрифте, браузер автоматически берёт его из запасных шрифтов стека (Segoe UI / Noto Sans / DejaVu — см. tokens.css).
        </p>
      </div>
    </div>
  );
}
