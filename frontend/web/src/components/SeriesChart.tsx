import { BarChart, LineChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";
import type { SeriesOut } from "../api/client";
import { prefersReducedMotion, useStore, useT } from "../store";

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, DataZoomComponent, CanvasRenderer]);

const TXT = "#9FC3D6";
const AX = "rgba(25,227,255,0.18)";

export function SeriesChart({ data, cycle }: { data: SeriesOut; cycle: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const t = useT();
  const lang = useStore((s) => s.lang);

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.current?.dispose();
    };
  }, []);

  useEffect(() => {
    if (!chart.current) return;
    const d = data.displacement;
    const lower = d.median.map((m, i) => (m == null || d.sigma[i] == null ? null : +(m - (d.sigma[i] as number)).toFixed(3)));
    const width = d.sigma.map((s, i) => (s == null || d.median[i] == null ? null : +(2 * s).toFixed(3)));
    const pts = (dates: string[], vals: (number | null)[]) => dates.map((x, i) => [x, vals[i]]);
    const sec = data.other_displacement[0];
    const pr = data.precip_30d;
    const start = d.dates.length > 70 ? Math.round(((d.dates.length - 62) / d.dates.length) * 100) : 0;
    const reduced = prefersReducedMotion();
    chart.current.setOption(
      {
        animation: !reduced,
        animationDuration: 900,
        animationEasing: "cubicOut",
        textStyle: { fontFamily: "JetBrains Mono, monospace", color: TXT, fontSize: 12 },
        grid: { left: 44, right: 48, top: 104, bottom: 46 },
        legend: { top: 0, left: 0, orient: "vertical", itemGap: 4, textStyle: { color: TXT, fontSize: 12 }, itemWidth: 14, itemHeight: 8, data: [t("chart.corrected"), t("chart.norm"), ...(sec ? [t("chart.secondary")] : []), t("chart.precip")] },
        tooltip: {
          trigger: "axis",
          backgroundColor: "rgba(2,42,68,0.95)",
          borderColor: "rgba(25,227,255,0.5)",
          textStyle: { color: "#E6F6FF", fontSize: 12 },
          valueFormatter: (v: unknown) => (typeof v === "number" ? v.toFixed(2) : "—"),
        },
        xAxis: { type: "time", axisLine: { lineStyle: { color: AX } }, axisLabel: { color: TXT, fontSize: 12 }, splitLine: { show: false } },
        yAxis: [
          { type: "value", name: "см", nameTextStyle: { color: TXT }, axisLabel: { color: TXT, fontSize: 12 }, splitLine: { lineStyle: { color: AX } } },
          { type: "value", name: "мм", nameTextStyle: { color: TXT }, axisLabel: { color: TXT, fontSize: 12 }, splitLine: { show: false } },
        ],
        dataZoom: [{ type: "inside", start, end: 100 }, { type: "slider", start, end: 100, height: 16, bottom: 6, borderColor: AX, textStyle: { color: TXT }, fillerColor: "rgba(25,227,255,0.12)" }],
        series: [
          { name: "lower", type: "line", data: pts(d.dates, lower), stack: "band", symbol: "none", lineStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
          { name: t("chart.norm"), type: "line", data: pts(d.dates, width), stack: "band", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: "rgba(25,227,255,0.14)" }, color: "rgba(25,227,255,0.4)" },
          {
            name: t("chart.corrected"),
            type: "line",
            data: pts(d.dates, d.corrected),
            symbol: "circle",
            symbolSize: 4,
            connectNulls: false,
            color: "#19E3FF",
            lineStyle: { width: 2 },
            markLine: {
              symbol: "none",
              silent: true,
              label: { color: "#E6F6FF", fontSize: 12, formatter: "{b}" },
              data: [
                { name: cycle, xAxis: cycle, lineStyle: { color: "#E6F6FF", type: "solid", opacity: 0.6 } },
                ...data.events.map((e) => ({ name: `${t("chart.event")} ${e.date}`, xAxis: e.date as string, lineStyle: { color: "#FF4FD8", type: "dashed" } })),
              ],
            },
          },
          ...(sec
            ? [{ name: t("chart.secondary"), type: "line", data: pts(sec.dates, sec.values), symbol: "none", color: "#C77DFF", lineStyle: { width: 1.4, type: "dashed" } }]
            : []),
          ...(pr ? [{ name: t("chart.precip"), type: "bar", yAxisIndex: 1, data: pts(pr.dates, pr.values), color: "rgba(123,108,255,0.45)", barMaxWidth: 6 }] : []),
        ],
      },
      true,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, cycle, lang]);

  return (
    <figure style={{ margin: 0 }}>
      <div ref={ref} style={{ width: "100%", height: 300 }} role="img" aria-label={t("card.series")} />
      <figcaption className="small muted">{t("chart.los_note")} · {data.displacement.family} · {data.analytics_version && `analytics ${data.analytics_version}`}</figcaption>
    </figure>
  );
}
