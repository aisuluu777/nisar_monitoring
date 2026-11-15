// Скриншоты для слайдов: 1920×1080 и 390×844, реальные данные + демо для красной ячейки.
// node e2e/slides.mjs [base] [out]
import { chromium } from "@playwright/test";
import fs from "node:fs";

const base = process.argv[2] ?? "http://localhost:8000";
const out = process.argv[3] ?? "../docs/screenshots";
fs.mkdirSync(out, { recursive: true });
const exe = ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"].find((p) => fs.existsSync(p));
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const errors = [];

async function session(w, h, mode, lang) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: w < 500 ? 2 : 1 });
  await ctx.addInitScript(([l, m]) => {
    localStorage.setItem("sw.lang", JSON.stringify(l));
    localStorage.setItem("sw.mode", JSON.stringify(m));
    for (const r of ["district_admin", "mchs", "public", "researcher", "sysadmin"]) localStorage.setItem(`sw.tour.${r}`, "1");
  }, [lang, mode]);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${mode}/${w}: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`${mode}/${w}: ${m.text()}`));
  return { ctx, page };
}

async function login(page, idx = 0) {
  await page.goto(`${base}/login`);
  await page.waitForSelector(".demo-accounts button");
  await page.locator(".demo-accounts button").nth(idx).click();
  await page.waitForSelector(".todayline");
  await page.waitForTimeout(2500);
}

for (const [w, h] of [[1920, 1080], [390, 844]]) {
  const sz = `${w}x${h}`;
  // ---------- реальные данные
  let { ctx, page } = await session(w, h, "real", "ru");
  await page.goto(`${base}/`);
  await page.waitForSelector(".hero h1");
  await page.waitForTimeout(3500);
  await page.screenshot({ path: `${out}/01-landing-real-${sz}.png` });
  await login(page, 0);
  await page.screenshot({ path: `${out}/02-today-real-${sz}.png` });
  await page.goto(`${base}/map`);
  await page.waitForTimeout(3500);
  await page.screenshot({ path: `${out}/03-map-real-${sz}.png` });
  if (w > 500) {
    await page.locator("input[name=data-layer]").nth(1).check(); // накопленное смещение
    await page.locator(".ov-layers input[type=checkbox]").first().uncheck();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}/04-timemachine-real-${sz}.png` });
    await page.locator("button", { hasText: "3D" }).click();
    await page.waitForTimeout(4500);
    await page.screenshot({ path: `${out}/05-3d-real-${sz}.png` });
    await page.locator("button", { hasText: "3D" }).click();
    await page.locator(".map-tools button").nth(1).click();
    await page.waitForSelector(".ba-stage img");
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}/06-before-after-real-${sz}.png` });
    await page.keyboard.press("Escape");
    await page.locator(".ba-wrap").click({ position: { x: 5, y: 5 } }).catch(() => {});
    // карточка реальной ячейки с данными
    const g = page.locator(".attention button").first();
    if (await g.count()) {
      await g.click();
      await page.waitForSelector(".bulletin");
      await page.waitForTimeout(2500);
      await page.screenshot({ path: `${out}/07-card-real-${sz}.png` });
    }
  }
  await ctx.close();

  // ---------- демо: красная ячейка, история, ретроспектива
  ({ ctx, page } = await session(w, h, "demo", "ru"));
  await login(page, 0);
  await page.screenshot({ path: `${out}/08-today-demo-${sz}.png` });
  const first = page.locator(".task").first();
  await first.locator("button", { hasText: "Подробнее" }).click();
  await page.waitForSelector(".bulletin");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}/09-card-red-demo-${sz}.png` });
  await page.keyboard.press("Escape");
  await page.goto(`${base}/retro`);
  await page.waitForSelector(".retro-res, .page-title");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/10-retro-demo-${sz}.png` });
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(`${base}/`);
  await page.locator(".btn.primary.lg").click();
  await page.waitForTimeout(12000);
  await page.screenshot({ path: `${out}/11-story-${sz}.png` });
  await ctx.close();

  // ---------- английский
  ({ ctx, page } = await session(w, h, "real", "en"));
  await page.goto(`${base}/`);
  await page.waitForSelector(".hero h1");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${out}/12-landing-en-${sz}.png` });
  await ctx.close();
}
await browser.close();
console.log(errors.length ? "ERRORS:\n" + errors.slice(0, 20).join("\n") : "no console errors");
