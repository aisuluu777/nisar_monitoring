/**
 * Подложки NASA GIBS (WMTS, EPSG:3857). Набор тайловых матриц у каждого слоя свой.
 * Значения проверены запросом тайлов 2026-11-15; на этапе 0 сверить с GetCapabilities:
 * https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml   (VERIFY_STAGE0)
 */
export const GIBS = {
  globe: {
    layer: "BlueMarble_ShadedRelief_Bathymetry",
    matrixSet: "GoogleMapsCompatible_Level8",
    maxzoom: 8,
    ext: "jpeg",
  },
  relief: {
    layer: "ASTER_GDEM_Greyscale_Shaded_Relief",
    matrixSet: "GoogleMapsCompatible_Level12",
    maxzoom: 12,
    ext: "jpg",
  },
} as const;

export function gibsUrl(l: (typeof GIBS)[keyof typeof GIBS]) {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${l.layer}/default/${l.matrixSet}/{z}/{y}/{x}.${l.ext}`;
}

export const GIBS_ATTRIBUTION = "Imagery: NASA GIBS / ESDIS";

/** Цвета статусов (только для статусов) — те же, что в tokens.css. */
export const STATUS_COLORS = { green: "#3DDC97", yellow: "#FFC94D", red: "#FF6B5B", grey: "#7A8A99" } as const;

/**
 * Шкалы данных не пересекаются со статусами:
 * смещение — расходящаяся cyan ↔ magenta (без зелёного, жёлтого, кораллового);
 * влажность — последовательная синяя; осадки — фиолетово-синяя; растительность — оливковая;
 * рельеф — радужная по высоте (при включённых статусах → серая отмывка).
 */
export type Ramp = { stops: [number, string][]; unit: string; fmt: (v: number) => string };

export const RAMPS: Record<"disp" | "sm" | "precip" | "veg" | "relief" | "relief_grey", Ramp> = {
  disp: {
    stops: [
      [-2, "#19E3FF"],
      [-1, "#1597B8"],
      [-0.25, "#183A52"],
      [0, "#1B2838"],
      [0.25, "#4A2A55"],
      [1, "#B03CA8"],
      [2, "#FF4FD8"],
    ],
    unit: "см",
    fmt: (v) => v.toFixed(1),
  },
  sm: {
    stops: [
      [0.05, "#0B2545"],
      [0.15, "#1F4E8C"],
      [0.25, "#3F86D1"],
      [0.35, "#8FD3FF"],
    ],
    unit: "м³/м³",
    fmt: (v) => v.toFixed(2),
  },
  precip: {
    stops: [
      [0, "#1A1446"],
      [40, "#3B2F99"],
      [90, "#6B63E8"],
      [150, "#B7B0FF"],
    ],
    unit: "мм",
    fmt: (v) => v.toFixed(0),
  },
  veg: {
    stops: [
      [0, "#1E2410"],
      [0.05, "#46521E"],
      [0.15, "#86973A"],
      [0.3, "#C7D66D"],
    ],
    unit: "",
    fmt: (v) => `${Math.round(v * 100)}%`,
  },
  relief: {
    stops: [
      [1300, "#2B3A8C"],
      [1700, "#2F7FC1"],
      [2000, "#38B6A8"],
      [2300, "#8CC56A"],
      [2600, "#E3C74E"],
      [2900, "#E08A4C"],
      [3150, "#C85A5A"],
      [3400, "#F2F2F2"],
    ],
    unit: "м",
    fmt: (v) => v.toFixed(0),
  },
  relief_grey: {
    stops: [
      [1300, "#1d2731"],
      [3400, "#8a96a3"],
    ],
    unit: "м",
    fmt: (v) => v.toFixed(0),
  },
};

export function rampExpression(prop: string, ramp: Ramp): unknown[] {
  return [
    "case",
    ["==", ["get", prop], null],
    "rgba(0,0,0,0)",
    ["interpolate", ["linear"], ["get", prop], ...ramp.stops.flat()],
  ];
}

export function rampGradient(ramp: Ramp) {
  const [min, max] = [ramp.stops[0][0], ramp.stops[ramp.stops.length - 1][0]];
  return `linear-gradient(90deg, ${ramp.stops
    .map(([v, c]) => `${c} ${(((v - min) / (max - min)) * 100).toFixed(1)}%`)
    .join(", ")})`;
}
