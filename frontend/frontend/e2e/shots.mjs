// Скриншоты ключевых экранов через системный Chrome/Edge (Playwright).
// node e2e/shots.mjs [base_url] [out_dir] [--sizes=1920x1080,390x844] [--lang=ru] [--mode=real|demo]
import { chromium } from "@playwright/test";
import fs from "node:fs";

const args = process.argv.slice(2);
const pos = args.filter((a) => !a.startsWith("--"));
const opt = Object.fromEntries(args.filter((a) => a.startsWith("--")).map((a) => a.slice(2).split("=")));
const base = pos[0] ?? "http://localhost:8000";
const out = pos[1] ?? "test-results/shots";
const sizes = (opt.sizes ?? "1280x800,360x780").split(",").map((s) => s.split("x").map(Number));
const lang = opt.lang ?? "ru";
fs.mkdirSync(out, { recursive: true });
const exe = ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"].find((p) => fs.existsSync(p));
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const errors = [];

for (const [w, h] of sizes) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript(
    ([l, m]) => {
      localStorage.setItem("sw.lang", JSON.stringify(l));
      if (m) localStorage.setItem("sw.mode", JSON.stringify(m));
      for (const r of ["district_admin", "mchs", "public", "researcher", "sysadmin"]) localStorage.setItem(`sw.tour.${r}`, "1");
    },
    [lang, opt.mode ?? null],
  );
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(`${w}: ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
  const tag = `${lang}-${w}`;

  await page.goto(`${base}/`);
  await page.waitForSelector(".hero h1");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${out}/landing-${tag}.png` });

  await page.goto(`${base}/login`);
  await page.waitForSelector(".demo-accounts button");
  await page.locator(".demo-accounts button").first().click(); // администрация района
  await page.waitForSelector(".task, .empty");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}/today-${tag}.png` });

  const first = page.locator(".task").first();
  if (await first.count()) {
    await first.click();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}/today-focus-${tag}.png` });
    await first.locator("button", { hasText: /Подробнее|Details|Кененирээк/ }).click();
    await page.waitForSelector(".bulletin");
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${out}/card-${tag}.png` });
    await page.locator(".drawer .scroll").evaluate((el) => (el.scrollTop = 700));
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${out}/card2-${tag}.png` });
    await page.keyboard.press("Escape");
  }

  // тур: первые шаги
  await page.evaluate(() => localStorage.removeItem("sw.tour.district_admin"));
  await page.locator("button[aria-label]", { hasText: "?" }).first().click().catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/tour-${tag}.png` });
  await page.keyboard.press("Escape");

  await page.goto(`${base}/map`);
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${out}/map-${tag}.png` });
  await ctx.close();
}
await browser.close();
console.log(errors.length ? "CONSOLE ERRORS:\n" + errors.join("\n") : "no console errors");
