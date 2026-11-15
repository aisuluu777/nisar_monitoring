import { useId, useState, type ReactNode } from "react";
import { useT } from "../store";

export type TermKey = "insar" | "los" | "coherence" | "norm" | "mad" | "provisional" | "backscatter";

/** Термин с подсказкой в одну строку (наведение, фокус с клавиатуры или касание). */
export function Term({ k, children }: { k: TermKey; children?: ReactNode }) {
  const t = useT();
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <button
      type="button"
      className={`term ${open ? "open" : ""}`}
      aria-describedby={id}
      onClick={(e) => {
        e.stopPropagation();
        setOpen((v) => !v);
      }}
      onBlur={() => setOpen(false)}
    >
      {children ?? t(`g.${k}.t`)}
      <span role="tooltip" id={id} className="tip">
        <b>{t(`g.${k}.t`)}</b>
        {t(`g.${k}.d`)}
      </span>
    </button>
  );
}
