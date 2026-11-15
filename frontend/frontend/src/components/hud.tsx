import type { CSSProperties, ReactNode } from "react";
import type { StatusCode } from "../api/client";
import { useT } from "../store";

/** Стеклянная панель: угловые скобки + однократная прорисовка рамки по контуру. */
export function GlassPanel(props: {
  index?: string;
  title?: string;
  children: ReactNode;
  className?: string;
  stagger?: number;
  style?: CSSProperties;
  headExtra?: ReactNode;
  as?: "section" | "div" | "aside";
  label?: string;
  /** Акцентная панель (неоновая рамка, скобки, прорисовка) — одна на экран. Остальные — спокойные. */
  accent?: boolean;
  tourId?: string;
}) {
  const Tag = props.as ?? "section";
  return (
    <Tag
      className={`glass ${props.accent ? "accent" : "quiet"} ${props.className ?? ""}`}
      data-tour={props.tourId}
      style={{ ...(props.style ?? {}), ["--stagger" as string]: props.stagger ?? 0 }}
      aria-label={props.label ?? props.title}
    >
      {props.accent && (
        <>
          <svg className="trace" aria-hidden="true" preserveAspectRatio="none">
            <rect x="0.5" y="0.5" rx="8" pathLength={1} style={{ width: "calc(100% - 1px)", height: "calc(100% - 1px)" }} />
          </svg>
          <span className="brackets" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
        </>
      )}
      {props.title && (
        <div className="panel-head">
          {props.index && <span className="idx">{props.index} /</span>}
          <span>{props.title}</span>
          <span className="line" />
          {props.headExtra}
        </div>
      )}
      {props.children}
    </Tag>
  );
}

const ICON: Record<StatusCode, string> = { green: "✓", yellow: "!", red: "▲", grey: "?" };

export function StatusChip({ status, large }: { status: StatusCode; large?: boolean }) {
  const t = useT();
  return (
    <span className={`chip st-${status} ${large ? "lg" : ""}`} title={t("status.agree_note")}>
      <span className="ico" aria-hidden="true">
        <b>{ICON[status]}</b>
      </span>
      <span style={{ color: "var(--text-1)" }}>{t(`status.${status}`)}</span>
    </span>
  );
}

export function statusIcon(s: StatusCode) {
  return ICON[s];
}

/** Бейдж источника: семейство · дата · зрелость; устаревшие — янтарная рамка. */
export function SourceBadge(p: { source: string; family?: string; date: string; maturity: string; staleDays?: number | null }) {
  const t = useT();
  const synthetic = p.source === "SYNTHETIC";
  return (
    <span className={`badge ${synthetic ? "synthetic" : ""} ${p.staleDays ? "stale" : ""}`}>
      <span className="src">{synthetic ? "SYNTHETIC" : p.source}</span>
      {p.family && <span>{p.family.replace("SYNTHETIC-", "")}</span>}
      <span>· {p.date}</span>
      <span className="mat">· {p.maturity}</span>
      {p.staleDays ? <span>· {t("map.stale", { n: p.staleDays })}</span> : null}
    </span>
  );
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => (
        <i key={i} style={{ width: `${90 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  );
}

export function Stepper({ steps }: { steps: { key: string; state: "done" | "blocked" | "pending" }[] }) {
  const t = useT();
  return (
    <ol className="stepper" aria-label="Цепочка обработки" style={{ listStyle: "none", margin: 0 }}>
      {steps.map((s, i) => (
        <li key={s.key} style={{ display: "flex", alignItems: "center" }}>
          {i > 0 && <span className={`bar ${steps[i - 1].state === "done" && s.state === "done" ? "done" : ""}`} />}
          <span className={`st ${s.state}`}>
            <span className="dot" aria-hidden="true" />
            {t(`step.${s.key}`)}
            <span className="sr-only">
              {s.state === "done" ? "пройдено" : s.state === "blocked" ? "недоступно" : "ожидает"}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useT();
  return (
    <div role="alert" className="muted" style={{ display: "grid", gap: 8 }}>
      <span>
        {t("common.error")}: {message}
      </span>
      {onRetry && (
        <button className="btn sm" onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}
