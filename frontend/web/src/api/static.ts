/**
 * Статическая версия (сборка VITE_STATIC=1): вместо сервера — заранее выгруженные ответы API
 * (static-api/real.json, static-api/demo.json, см. tools/export_static.py).
 * Действия (передать специалисту, решения) сохраняются только в памяти вкладки.
 */
export const STATIC = import.meta.env.VITE_STATIC === "1";

const bundles = new Map<string, Promise<Record<string, unknown>>>();

function bundle(mode: string) {
  if (!bundles.has(mode))
    bundles.set(
      mode,
      fetch(`./static-api/${mode}.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
    );
  return bundles.get(mode)!;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export async function staticFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const req = input instanceof Request ? input : new Request(String(input), init);
  const url = new URL(req.url, window.location.href);
  const path = url.pathname.slice(url.pathname.indexOf("/api/v1"));
  const mode = req.headers.get("X-Data-Mode") ?? ((await bundle("real"))["GET /api/v1/meta"] ? "real" : "demo");
  const b = await bundle(mode);
  if (req.method === "POST") {
    const body = await req.clone().json().catch(() => ({}) as Record<string, unknown>);
    if (path === "/api/v1/auth/login") {
      const r = b[`POST /api/v1/auth/login:${body.username}`];
      return r ? json(r) : json({ detail: "Неверное имя пользователя или пароль" }, 401);
    }
    const now = new Date().toISOString();
    if (path.endsWith("/handoff")) return json({ ts: now, user: "Demo", comment: body.comment ?? "", cycle: body.cycle ?? null }, 201);
    if (path.endsWith("/decisions"))
      return json({ id: Math.floor(Math.random() * 1e6), verdict: body.verdict, comment: body.comment, created_at: now, user: "Demo" }, 201);
    if (path.endsWith("/approve")) return json({ id: 0, status: "approved" });
    return json({ detail: "Недоступно в статической версии" }, 501);
  }
  const params = [...url.searchParams.entries()].sort(([a], [b2]) => a.localeCompare(b2)).map(([k, v]) => `${k}=${v}`).join("&");
  let key = `GET ${path}` + (params ? `?${params}` : "");
  if (path.endsWith("/summary") && req.headers.get("Authorization")) key += "#auth";
  if (key in b) return json(b[key]);
  return json({ detail: "Эти данные не входят в статическую версию — откройте полную версию (python tasks.py real)" }, 404);
}
