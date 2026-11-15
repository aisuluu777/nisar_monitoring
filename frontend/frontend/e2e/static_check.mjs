// Проверка статической версии: лендинг → вход → «Сегодня» → карточка; реальные данные и демо.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:8099/index.html";
const out = process.argv[3] ?? "test-results/static";
fs.mkdirSync(out, { recursive: true });
const exe = ["C:/Program Files/Google/Chrome/Application/chrome.exe"].find((p) => fs.existsSync(p));
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const errors = [];
for (const mode of ["real", "demo"]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript((m) => {
    localStorage.setItem("sw.mode", JSON.stringify(m));
    for (const r of ["district_admin", "mchs", "public"]) localStorage.setItem(`sw.tour.${r}`, "1");
  }, mode);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${mode}: ${e.message}`));
  await page.goto(base);
  await page.waitForSelector(".hero h1", { timeout: 20000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/${mode}-landing.png` });
  await page.goto(base + "#login");
  await page.waitForSelector(".demo-accounts button");
  await page.locator(".demo-accounts button").first().click();
  await page.waitForSelector(".todayline");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${out}/${mode}-today.png` });
  const btn = page.locator(".task button", { hasText: "Подробнее" }).first();
  if (await btn.count()) {
    await btn.click();
    await page.waitForSelector(".bulletin", { timeout: 15000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}/${mode}-card.png` });
  }
  await page.goto(base + "#map");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}/${mode}-map.png` });
  await ctx.close();
}
await browser.close();
console.log(errors.length ? errors.join("\n") : "no page errors");
