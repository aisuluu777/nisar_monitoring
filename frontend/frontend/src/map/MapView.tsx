import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { CellsFC } from "../api/client";
import { prefersReducedMotion, useStore } from "../store";
import { GIBS, GIBS_ATTRIBUTION, RAMPS, STATUS_COLORS, gibsUrl, rampExpression } from "./config";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
const DATA_PROP = { disp: "disp_cm", sm: "sm", precip: "precip_mm", veg: "veg", relief: "elev" } as const;
const FADE_MS = 200;

export function MapView(props: {
  data: CellsFC | null;
  bbox: number[] | null;
  events: GeoJSON.FeatureCollection | null;
  changed: string[];
  /** Отступы при подгонке карты к району; по умолчанию — под панели экрана карты */
  padding?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const ready = useRef(false);
  const hasData = useRef(false);
  const pending = useRef<() => void>(() => {});
  const { showStatus, dataLayer, showEvents, statusFilter, selectedCell, selectCell, focus } = useStore();
  const highlighted = selectedCell ?? focus?.id ?? null;
  const reduced = prefersReducedMotion();

  // --- инициализация ---------------------------------------------------------
  useEffect(() => {
    if (!ref.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      attributionControl: { compact: true, customAttribution: GIBS_ATTRIBUTION },
      style: {
        version: 8,
        sources: {
          gibs: { type: "raster", tiles: [gibsUrl(GIBS.relief)], tileSize: 256, maxzoom: GIBS.relief.maxzoom },
          cells: { type: "geojson", data: EMPTY, promoteId: "id" },
          events: { type: "geojson", data: EMPTY },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#011425" } },
          {
            id: "gibs",
            type: "raster",
            source: "gibs",
            paint: { "raster-opacity": 0.55, "raster-brightness-max": 0.55, "raster-saturation": -0.4, "raster-contrast": 0.1 },
          },
          { id: "relief-grey", type: "fill", source: "cells", paint: { "fill-color": rampExpression("elev", RAMPS.relief_grey) as never, "fill-opacity": 0.28 } },
          { id: "data-fill", type: "fill", source: "cells", layout: { visibility: "none" }, paint: { "fill-opacity": 0.82, "fill-opacity-transition": { duration: FADE_MS } } },
          {
            id: "status-fill",
            type: "fill",
            source: "cells",
            paint: {
              "fill-color": ["match", ["get", "status"], "green", STATUS_COLORS.green, "yellow", STATUS_COLORS.yellow, "red", STATUS_COLORS.red, STATUS_COLORS.grey] as never,
              "fill-opacity": ["match", ["get", "status"], "green", 0.22, "grey", 0.3, 0.62] as never,
              "fill-opacity-transition": { duration: FADE_MS },
            },
          },
          {
            id: "status-line",
            type: "line",
            source: "cells",
            filter: ["in", ["get", "status"], ["literal", ["yellow", "red"]]],
            paint: {
              "line-color": ["match", ["get", "status"], "red", STATUS_COLORS.red, STATUS_COLORS.yellow] as never,
              "line-width": ["match", ["get", "status"], "red", 2, 1.2] as never,
            },
          },
          { id: "grey-line", type: "line", source: "cells", filter: ["==", ["get", "status"], "grey"], paint: { "line-color": STATUS_COLORS.grey, "line-width": 0.8, "line-dasharray": [2, 2] } },
          { id: "grid-line", type: "line", source: "cells", paint: { "line-color": "rgba(25,227,255,0.10)", "line-width": 0.5 } },
          { id: "flash-line", type: "line", source: "cells", filter: ["in", ["get", "id"], ["literal", []]], paint: { "line-color": "#E6F6FF", "line-width": 2.5, "line-opacity": 0, "line-opacity-transition": { duration: 600 } } },
          { id: "selected-glow", type: "line", source: "cells", filter: ["==", ["get", "id"], ""], paint: { "line-color": "#19E3FF", "line-width": 8, "line-blur": 6, "line-opacity": 0.5 } },
          { id: "selected-line", type: "line", source: "cells", filter: ["==", ["get", "id"], ""], paint: { "line-color": "#19E3FF", "line-width": 2.2 } },
          {
            id: "events",
            type: "circle",
            source: "events",
            layout: { visibility: "none" },
            paint: { "circle-radius": 7, "circle-color": "rgba(230,246,255,0.15)", "circle-stroke-color": "#E6F6FF", "circle-stroke-width": 2 },
          },
        ],
      },
      center: [72.95, 40.95],
      zoom: 11,
      minZoom: 8,
      maxZoom: 15,
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => {
      ready.current = true;
      pending.current();
    });
    map.on("click", "status-fill", (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id) selectCell(id);
    });
    map.on("click", "data-fill", (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id) selectCell(id);
    });
    for (const l of ["status-fill", "data-fill"]) {
      map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
    }
    mapRef.current = map;
    return () => {
      ready.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, [selectCell]);

  const whenReady = (fn: () => void) => {
    if (ready.current && mapRef.current) fn();
    else pending.current = ((prev) => () => {
      prev();
      fn();
    })(pending.current);
  };

  // --- границы района ----------------------------------------------------------
  useEffect(() => {
    if (!props.bbox) return;
    const [a, b, c, d] = props.bbox;
    whenReady(() => mapRef.current!.fitBounds([a, b, c, d], { padding: props.padding !== undefined ? props.padding : window.innerWidth > 760 ? { top: 30, bottom: 110, left: 310, right: 320 } : { top: 110, bottom: 110, left: 16, right: 16 }, duration: 0 }));
  }, [props.bbox]);

  // --- данные цикла: плавный кроссфейд ------------------------------------------
  useEffect(() => {
    if (!props.data) return;
    whenReady(() => {
      const map = mapRef.current!;
      const src = map.getSource("cells") as GeoJSONSource;
      if (!hasData.current || reduced) {
        src.setData(props.data as unknown as GeoJSON.FeatureCollection);
        hasData.current = true;
        return;
      }
      map.setPaintProperty("status-fill", "fill-opacity", 0.05);
      map.setPaintProperty("data-fill", "fill-opacity", 0.1);
      window.setTimeout(() => {
        src.setData(props.data as unknown as GeoJSON.FeatureCollection);
        map.setPaintProperty("status-fill", "fill-opacity", ["match", ["get", "status"], "green", 0.22, "grey", 0.3, 0.62]);
        map.setPaintProperty("data-fill", "fill-opacity", 0.82);
      }, FADE_MS);
    });
  }, [props.data, reduced]);

  // --- слои ----------------------------------------------------------------------
  useEffect(() => {
    whenReady(() => {
      const map = mapRef.current!;
      const vis = (id: string, on: boolean) => map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
      vis("status-fill", showStatus);
      vis("status-line", showStatus);
      vis("grey-line", showStatus);
      // рельеф: радужный как слой данных; при включённых статусах — только серая отмывка
      vis("relief-grey", showStatus || dataLayer !== "relief");
      if (dataLayer === "none") vis("data-fill", false);
      else {
        const ramp = dataLayer === "relief" && showStatus ? RAMPS.relief_grey : RAMPS[dataLayer];
        map.setPaintProperty("data-fill", "fill-color", rampExpression(DATA_PROP[dataLayer], ramp));
        vis("data-fill", !(dataLayer === "relief" && showStatus));
      }
      const f = statusFilter ? ["==", ["get", "status"], statusFilter] : null;
      for (const id of ["status-fill", "data-fill"]) map.setFilter(id, f as never);
    });
  }, [showStatus, dataLayer, statusFilter]);

  useEffect(() => {
    whenReady(() => {
      const map = mapRef.current!;
      (map.getSource("events") as GeoJSONSource).setData(props.events ?? EMPTY);
      map.setLayoutProperty("events", "visibility", showEvents && props.events ? "visible" : "none");
    });
  }, [props.events, showEvents]);

  // --- выбранная ячейка: пульсирующий неоновый контур ------------------------------
  useEffect(() => {
    let raf = 0;
    whenReady(() => {
      const map = mapRef.current!;
      const f = ["==", ["get", "id"], highlighted ?? ""];
      map.setFilter("selected-line", f as never);
      map.setFilter("selected-glow", f as never);
      if (!highlighted || reduced) return;
      const t0 = performance.now();
      const tick = (t: number) => {
        const k = 0.5 + 0.5 * Math.sin((t - t0) / 380);
        map.setPaintProperty("selected-glow", "line-opacity", 0.2 + 0.5 * k);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(raf);
  }, [highlighted, reduced]);

  // задача выбрана в списке «Сегодня» — приближаем карту к участку
  useEffect(() => {
    if (!focus) return;
    whenReady(() => mapRef.current!.flyTo({ center: [focus.lon, focus.lat], zoom: 13.6, duration: reduced ? 0 : 900 }));
  }, [focus, reduced]);

  // --- ячейки с новым статусом мигают один раз ---------------------------------------
  useEffect(() => {
    if (!props.changed.length || reduced) return;
    whenReady(() => {
      const map = mapRef.current!;
      map.setFilter("flash-line", ["in", ["get", "id"], ["literal", props.changed]] as never);
      map.setPaintProperty("flash-line", "line-opacity", 0.95);
      window.setTimeout(() => map.setPaintProperty("flash-line", "line-opacity", 0), 700);
    });
  }, [props.changed, reduced]);

  return <div ref={ref} className="map" role="application" aria-label="Карта ячеек района" />;
}
