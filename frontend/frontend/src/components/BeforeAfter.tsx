import { useEffect, useMemo, useState } from "react";
import { api, fetchImage, unwrap } from "../api/client";
import { useT } from "../store";
import { GlassPanel, Skeleton } from "./hud";

type Item = { date: string; file: string; scene: string; coordinates: number[][] };

/** «До / после» радара: шторка между двумя снимками обратного рассеяния Sentinel-1 RTC. */
export function BeforeAfter({ onClose }: { onClose: () => void }) {
  const t = useT();
  const [items, setItems] = useState<Item[] | null>(null);
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [pos, setPos] = useState(50);

  useEffect(() => {
    api.GET("/api/v1/rtc").then(unwrap).then((r) => {
      const it = (r as { items: Item[] }).items ?? [];
      setItems(it);
      if (it.length > 1) {
        // по умолчанию: летний снимок и последний доступный
        const summer = [...it].reverse().find((x) => ["07", "08", "09"].includes(x.date.slice(5, 7))) ?? it[0];
        setA(summer.date);
        setB(it[it.length - 1].date === summer.date ? it[0].date : it[it.length - 1].date);
      }
    }).catch(() => setItems([]));
  }, []);

  useEffect(() => {
    for (const d of [a, b]) {
      if (!d || urls[d]) continue;
      const it = items?.find((x) => x.date === d);
      if (it) fetchImage(`/api/v1/rtc/${it.file}`).then((u) => setUrls((m) => ({ ...m, [d]: u }))).catch(() => undefined);
    }
  }, [a, b, items, urls]);

  const dates = useMemo(() => (items ?? []).map((x) => x.date), [items]);
  const scene = (d: string) => items?.find((x) => x.date === d)?.scene ?? "";

  return (
    <div className="ba-wrap" role="dialog" aria-modal="true" aria-label={t("ba.title")} onClick={onClose}>
      <GlassPanel accent className="ba" title={t("ba.title")} index="◐" headExtra={<button className="btn sm ghost" onClick={onClose} aria-label="close">✕</button>}>
        <div className="panel-body" onClick={(e) => e.stopPropagation()} style={{ display: "grid", gap: 10 }}>
          {!items && <Skeleton rows={4} />}
          {items && items.length < 2 && <p className="muted">{t("ba.none")}</p>}
          {items && items.length >= 2 && (
            <>
              <div className="ba-sel">
                <label className="field">
                  {t("ba.before")}
                  <select className="input" value={a} onChange={(e) => setA(e.target.value)}>
                    {dates.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  {t("ba.after")}
                  <select className="input" value={b} onChange={(e) => setB(e.target.value)}>
                    {dates.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="ba-stage">
                {urls[a] && <img src={urls[a]} alt={`${t("ba.before")} ${a}`} />}
                {urls[b] && <img src={urls[b]} alt={`${t("ba.after")} ${b}`} style={{ clipPath: `inset(0 0 0 ${pos}%)` }} />}
                <div className="ba-line" style={{ left: `${pos}%` }} aria-hidden="true" />
                <span className="ba-tag l">{t("ba.before")} · {a}</span>
                <span className="ba-tag r">{t("ba.after")} · {b}</span>
                <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))} aria-label={t("ba.title")} />
              </div>
              <p className="small muted" style={{ margin: 0 }}>{t("ba.hint")}</p>
              <p className="mono small muted" style={{ margin: 0 }}>Sentinel-1 RTC · {scene(a)} · {scene(b)} · Copernicus / Microsoft Planetary Computer</p>
            </>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}
