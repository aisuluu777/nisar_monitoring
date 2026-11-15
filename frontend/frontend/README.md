# Slope Watch — frontend

The web client (React 18 + TypeScript + Vite, MapLibre GL, ECharts, Zustand), split out of the main repository.

## Run locally

```bash
npm ci
npm run dev        # http://localhost:5173
```

In dev mode, `/api`, `/docs` and `/openapi.json` are proxied to the backend at `http://localhost:8000` (see `vite.config.ts`).

## Build

```bash
npm run build      # output goes to dist/
```

## Regenerate API types

```bash
npm run gen:api    # openapi.json -> src/api/schema.d.ts
```

## Docker

```bash
docker build -t slope-watch-web .
```

nginx (`docker/nginx.conf`) serves the static files and proxies `/api/` to `http://api:8000`.
