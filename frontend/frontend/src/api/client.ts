/** Клиент API: типы генерируются из OpenAPI (npm run gen:api → src/api/schema.d.ts). */
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Meta = Schemas["Meta"];
export type CellCard = Schemas["CellCard"];
export type SeriesOut = Schemas["SeriesOut"];
export type Summary = Schemas["Summary"];
export type SourceInfo = Schemas["SourceInfo"];
export type Reason = Schemas["Reason"];
export type StatusCode = "green" | "yellow" | "red" | "grey";
export type TodayOut = Schemas["TodayOut"];
export type Task = Schemas["Task"];

export interface CellProps {
  id: string;
  village: string | null;
  status: StatusCode;
  stale: boolean;
  disp_cm: number | null;
  disp_z: number | null;
  precip_mm: number | null;
  precip_z: number | null;
  sm: number | null;
  veg: number | null;
  valid_frac: number | null;
  elev: number;
  slope: number;
}

export interface CellsFC {
  type: "FeatureCollection";
  features: { type: "Feature"; id: string; geometry: GeoJSON.Polygon; properties: CellProps }[];
  cycle: string | null;
  stale_days: number | null;
}

let token: string | null = null;
let dataMode: "real" | "demo" | null = null;

/** Режим данных для всех запросов: заголовок X-Data-Mode (реальные / демо). */
export function setDataModeHeader(m: "real" | "demo" | null) {
  dataMode = m;
}
let onUnauthorized: (() => void) | null = null;

export function setToken(t: string | null) {
  token = t;
}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

const auth: Middleware = {
  onRequest({ request }) {
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    if (dataMode) request.headers.set("X-Data-Mode", dataMode);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && token && onUnauthorized) onUnauthorized();
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: "" });
api.use(auth);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T {
  if (r.error !== undefined || r.data === undefined) {
    const detail = (r.error as { detail?: unknown })?.detail;
    throw new ApiError(r.response.status, typeof detail === "string" ? detail : `HTTP ${r.response.status}`);
  }
  return r.data;
}

/** /cells возвращает GeoJSON без схемы — типизируем вручную. */
export async function fetchCells(date?: string): Promise<CellsFC> {
  const r = await api.GET("/api/v1/cells", { params: { query: date ? { date } : {} } });
  return unwrap(r) as unknown as CellsFC;
}

export async function fetchEvents(): Promise<GeoJSON.FeatureCollection> {
  const r = await api.GET("/api/v1/events");
  return unwrap(r) as unknown as GeoJSON.FeatureCollection;
}
