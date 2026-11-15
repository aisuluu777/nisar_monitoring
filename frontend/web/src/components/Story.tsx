import { useEffect, useRef, useState } from "react";
import { api, unwrap, type TodayOut } from "../api/client";
import { useStore, useT, type User } from "../store";

/** «Демо-история»: автопилот ≈ 3 минуты по живому приложению с титрами. Пауза — клик по титру. */
const STEP_MS = 9000;

export function startStory() {
  useStore.setState({ storyStep: 0, storyPaused: false } as never);
}

export function Story() {
  const t = useT();
  const step = useStore((s) => (s as unknown as { storyStep: number | null }).storyStep ?? null);
  const paused = useStore((s) => (s as unknown as { storyPaused: boolean }).storyPaused ?? false);
  const [task, setTask] = useState<TodayOut["tasks"][number] | null>(null);
  const timer = useRef<number | null>(null);
  const set = (p: Record<string, unknown>) => useStore.setState(p as never);
  const N = 7;

  // действия шага
  useEffect(() => {
    if (step === null) return;
    const st = useStore.getState();
    (async () => {
      try {
        if (step === 0) {
          st.selectCell(null);
          st.navigate("/");
        } else if (step === 1) {
          if (!useStore.getState().user) {
            const acc = unwrap(await api.GET("/api/v1/auth/demo-accounts"));
            const a = acc.find((x) => x.role === "district_admin");
            if (a) {
              const r = unwrap(await api.POST("/api/v1/auth/login", { body: { username: a.username, password: a.password } }));
              st.login(r.access_token, r.user as User);
            }
          }
          st.navigate("/today");
          const d = unwrap(await api.GET("/api/v1/today", { params: { query: { lang: st.lang } } }));
          setTask(d.tasks[0] ?? null);
        } else if (step === 2 && task) {
          st.setFocus({ lon: task.lon, lat: task.lat, id: task.cell_id });
        } else if (step === 3 && task) {
          st.selectCell(task.cell_id);
        } else if (step === 4) {
          st.selectCell(null);
          st.navigate("/map");
          set({ storyPlay: Date.now() });
        } else if (step === 5 && task) {
          st.navigate("/today");
          st.selectCell(task.cell_id);
        } else if (step === 6) {
          st.selectCell(null);
          st.navigate("/retro");
        }
      } catch {
        /* шаг пропускается, история продолжается */
      }
    })();
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  // авто-переход
  useEffect(() => {
    if (step === null || paused) return;
    timer.current = window.setTimeout(() => set({ storyStep: step + 1 < N ? step + 1 : null }), step === 4 ? STEP_MS * 1.6 : STEP_MS);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [step, paused]);

  useEffect(() => {
    if (step === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") set({ storyStep: null });
      if (e.key === " ") set({ storyPaused: !useStore.getState()["storyPaused" as never] });
      if (e.key === "ArrowRight") set({ storyStep: Math.min(step + 1, N - 1) });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  if (step === null) return null;
  return (
    <div className="story" role="region" aria-live="polite" aria-label={t("story.title")}>
      <div className="story-card" onClick={() => set({ storyPaused: !paused })}>
        <div className="story-top">
          <span className="caps">{t("story.title")} · {step + 1}/{N}</span>
          <div className="story-bar" aria-hidden="true">
            {Array.from({ length: N }, (_, i) => (
              <i key={i} className={i < step ? "done" : i === step ? (paused ? "on paused" : "on") : ""} style={i === step && !paused ? { animationDuration: `${step === 4 ? STEP_MS * 1.6 : STEP_MS}ms` } : undefined} />
            ))}
          </div>
        </div>
        <p>{t(`story.s${step + 1}`)}</p>
        <div className="story-acts" onClick={(e) => e.stopPropagation()}>
          <button className="btn sm" onClick={() => set({ storyPaused: !paused })}>{paused ? `▶ ${t("story.play")}` : `❚❚ ${t("story.pause")}`}</button>
          {step < N - 1 && <button className="btn sm primary" onClick={() => set({ storyStep: step + 1 })}>{t("story.next")} →</button>}
          <button className="btn sm ghost" onClick={() => set({ storyStep: null })}>{t("story.exit")}</button>
        </div>
      </div>
    </div>
  );
}
