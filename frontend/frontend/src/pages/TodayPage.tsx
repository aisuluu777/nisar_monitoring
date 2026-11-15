import { useCallback, useEffect, useState } from "react";
import { api, fetchCells, unwrap, type CellsFC, type Task, type TodayOut } from "../api/client";
import { CellCard } from "../components/CellCard";
import { ErrorBox, GlassPanel, Skeleton, StatusChip } from "../components/hud";
import { Sparkline } from "../components/Sparkline";
import { tourSeen } from "../components/Tour";
import { MapView } from "../map/MapView";
import { useStore, useT } from "../store";

function TaskCard({ task, onHandoff, current }: { task: Task; onHandoff: (id: string) => Promise<void>; current: boolean }) {
  const t = useT();
  const { user, selectCell, setFocus } = useStore();
  const [busy, setBusy] = useState(false);
  const zoom = () => setFocus({ lon: task.lon, lat: task.lat, id: task.cell_id });
  return (
    <article
      className="glass quiet task"
      aria-current={current}
      tabIndex={0}
      onClick={zoom}
      onKeyDown={(e) => e.key === "Enter" && zoom()}
      data-tour="task"
    >
      <div className="row1">
        <StatusChip status={task.status as "red" | "yellow"} />
        <span className="place">{task.village ?? task.cell_id}</span>
        {task.is_new && <span className="newb">{t("today.new")}</span>}
        <span className="mono small muted" style={{ marginLeft: "auto" }}>
          {task.cell_id.split("-").slice(-1)[0]}
        </span>
      </div>
      <p className="phrase">{task.phrase}</p>
      <div className="row3">
        <Sparkline values={task.spark} label={t("chart.corrected")} />
        <div className="acts" onClick={(e) => e.stopPropagation()}>
          <button className="btn sm ghost" onClick={() => selectCell(task.cell_id)}>
            {t("today.open")}
          </button>
          {user?.role === "district_admin" ? (
            task.handed_off ? (
              <span className="badge">✓ {t("today.handed")}</span>
            ) : (
              <button
                className="btn sm primary"
                data-tour="handoff"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  await onHandoff(task.cell_id);
                  setBusy(false);
                }}
              >
                {t("today.handoff")}
              </button>
            )
          ) : (
            <button className="btn sm primary" data-tour="handoff" onClick={() => selectCell(task.cell_id)}>
              {t("today.review")}
            </button>
          )}
        </div>
      </div>
      {Object.keys(task.nearby ?? {}).length > 0 && <div className="nearby">{String((task.nearby as Record<string, unknown>).label ?? "")}</div>}
    </article>
  );
}

export function TodayPage() {
  const t = useT();
  const { lang, meta, selectedCell, selectCell, focus, user, setTourOpen } = useStore();
  const [data, setData] = useState<TodayOut | null>(null);
  const [cells, setCells] = useState<CellsFC | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const d = unwrap(await api.GET("/api/v1/today", { params: { query: { lang } } }));
      setData(d);
      if (d.shown_cycle) setCells(await fetchCells(d.shown_cycle));
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [lang]);

  useEffect(() => {
    load();
  }, [load, meta?.data_mode]);

  // первый вход роли — показываем обучение
  useEffect(() => {
    if (data && user && !tourSeen(user.role)) setTourOpen(true);
  }, [data, user, setTourOpen]);

  async function handoff(id: string) {
    try {
      unwrap(await api.POST("/api/v1/cells/{cell_id}/handoff", { params: { path: { cell_id: id } }, body: { comment: "", cycle: data?.shown_cycle ?? null } }));
      setData((d) => (d ? { ...d, tasks: d.tasks.map((x) => (x.cell_id === id ? { ...x, handed_off: true } : x)) } : d));
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const onClose = useCallback(() => selectCell(null), [selectCell]);

  return (
    <div className="today">
      <div className="col">
        <GlassPanel accent className="todayline" label={t("today.title")}>
          {!data && !err && <Skeleton rows={2} />}
          {err && <ErrorBox message={err} onRetry={load} />}
          {data && (
            <>
              <div className="big">
                {t("today.line", { n: "\u0000", m: data.new_since_prev, date: data.shown_cycle ?? "—" })
                  .split("\u0000")
                  .map((part, i) => (
                    <span key={i}>
                      {i > 0 && <span className="n">{data.to_check}</span>}
                      {part}
                    </span>
                  ))}
              </div>
              {data.off_season && (
                <div className="offseason">
                  {t("today.off_season", { reason: data.season_note ?? t("today.off_reason"), date: data.shown_cycle ?? "—" })}
                </div>
              )}
              <div className="meta">{t("today.map_hint")}</div>
            </>
          )}
        </GlassPanel>

        <section className="tasks" aria-label={t("today.tasks")} data-tour="tasks">
          {data && data.tasks.length === 0 && (
            <GlassPanel className="empty">
              <span className="ok" aria-hidden="true">
                ✓
              </span>
              <p style={{ margin: 0 }}>{t("today.empty", { date: data.next_expected ?? "—" })}</p>
            </GlassPanel>
          )}
          {data?.tasks.map((task) => (
            <TaskCard key={task.cell_id} task={task} onHandoff={handoff} current={focus?.id === task.cell_id} />
          ))}
        </section>
      </div>
      <div className="mapcol" data-tour="map">
        <MapView data={cells} bbox={meta?.district?.bbox ?? null} events={null} changed={[]} padding={24} />
      </div>
      {selectedCell && data?.shown_cycle && <CellCard key={selectedCell} cellId={selectedCell} cycle={data.shown_cycle} onClose={onClose} />}
    </div>
  );
}
