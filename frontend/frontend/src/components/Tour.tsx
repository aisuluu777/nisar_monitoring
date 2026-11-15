import { useEffect, useLayoutEffect, useState } from "react";
import { useStore, useT } from "../store";

/** Обучение из 4 шагов для роли: подсветка элемента [data-tour=...], можно пропустить, «?» — снова. */
const STEPS: Record<string, string[]> = {
  district_admin: ["tasks", "map", "task", "handoff"],
  mchs: ["tasks", "map", "task", "task"],
  other: ["nav", "mode", "lang", "help"],
};

function tourKey(role: string) {
  return `sw.tour.${role}`;
}

export function tourSeen(role: string): boolean {
  try {
    return window.localStorage.getItem(tourKey(role)) === "1";
  } catch {
    return true;
  }
}

export function Tour() {
  const t = useT();
  const { tourOpen, setTourOpen, user, path } = useStore();
  const role = user?.role ?? "public";
  const set = role === "district_admin" ? "admin" : role === "mchs" ? "mchs" : "other";
  const anchors = STEPS[role] ?? STEPS.other;
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (tourOpen) setI(0);
  }, [tourOpen, path]);

  useLayoutEffect(() => {
    if (!tourOpen) return;
    const find = () => {
      const el = document.querySelector(`[data-tour="${anchors[i]}"]`) as HTMLElement | null;
      if (el) {
        el.scrollIntoView({ block: "nearest" });
        setRect(el.getBoundingClientRect());
      } else setRect(null);
    };
    find();
    const id = window.setTimeout(find, 350); // элементы могут появиться после загрузки данных
    window.addEventListener("resize", find);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("resize", find);
    };
  }, [tourOpen, i, anchors]);

  useEffect(() => {
    if (!tourOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") setI((v) => Math.min(v + 1, anchors.length - 1));
      if (e.key === "ArrowLeft") setI((v) => Math.max(v - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function close() {
    try {
      window.localStorage.setItem(tourKey(role), "1");
    } catch {
      /* без хранилища тур просто покажется снова */
    }
    setTourOpen(false);
  }

  if (!tourOpen) return null;
  const pad = 6;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const card = { w: Math.min(360, vw - 32), h: 170 };
  let left = 16;
  let top = vh / 2 - card.h / 2;
  if (rect) {
    const below = rect.bottom + 12 + card.h < vh;
    const right = rect.right + 12 + card.w < vw;
    if (right && rect.width < vw * 0.5) {
      left = rect.right + 12;
      top = Math.min(Math.max(16, rect.top), vh - card.h - 16);
    } else {
      left = Math.min(Math.max(16, rect.left), vw - card.w - 16);
      top = below ? rect.bottom + 12 : Math.max(16, rect.top - card.h - 12);
    }
  }
  return (
    <div className="tour-shade" role="dialog" aria-modal="true" aria-label={t("help.open")}>
      {rect && (
        <div
          className="tour-hole"
          style={{ left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }}
        />
      )}
      <div className="tour-card" style={{ left, top }}>
        <span className="caps muted">{t("tour.step", { i: i + 1, n: anchors.length })}</span>
        <p>{t(`tour.${set}.${i + 1}`)}</p>
        <div className="row">
          <div className="dots" aria-hidden="true">
            {anchors.map((_, k) => (
              <i key={k} className={k === i ? "on" : ""} />
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn sm ghost" onClick={close}>
              {t("tour.skip")}
            </button>
            {i > 0 && (
              <button className="btn sm" onClick={() => setI(i - 1)}>
                {t("tour.prev")}
              </button>
            )}
            {i < anchors.length - 1 ? (
              <button className="btn sm primary" autoFocus onClick={() => setI(i + 1)}>
                {t("tour.next")}
              </button>
            ) : (
              <button className="btn sm primary" autoFocus onClick={close}>
                {t("tour.done")}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
