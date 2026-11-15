import { RAMPS, rampGradient } from "../map/config";
import { useStore, useT, type DataLayer } from "../store";

const LAYERS: { key: Exclude<DataLayer, "none">; ramp: keyof typeof RAMPS }[] = [
  { key: "precip", ramp: "precip" },
  { key: "sm", ramp: "sm" },
  { key: "disp", ramp: "disp" },
];

/** Изометрическая «этажерка» слоёв: плитки раздвигаются при наведении, клик включает слой на карте. */
export function LayerStack() {
  const t = useT();
  const { dataLayer, setDataLayer } = useStore();
  return (
    <div className="lstack" role="group" aria-label={t("card.layers")}>
      <div className="lstack-tiles">
        {LAYERS.map((l, i) => (
          <button
            key={l.key}
            className={`ltile ${dataLayer === l.key ? "on" : ""}`}
            style={{ ["--i" as string]: LAYERS.length - 1 - i, ["--g" as string]: rampGradient(RAMPS[l.ramp]) }}
            onClick={() => setDataLayer(dataLayer === l.key ? "none" : l.key)}
            aria-pressed={dataLayer === l.key}
            aria-label={t(`stack.${l.key}`)}
          >
            <span className="face" />
            <span className="callout">
              <span className="lead" />
              {t(`stack.${l.key}`)}
            </span>
          </button>
        ))}
      </div>
      <p className="small muted" style={{ margin: "4px 0 0" }}>
        {t("stack.hint")}
      </p>
    </div>
  );
}
