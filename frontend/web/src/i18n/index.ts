import ru from "./ru.json";
import ky from "./ky.json";
import en from "./en.json";

export type Lang = "ru" | "ky" | "en";
export const LANGS: Lang[] = ["ru", "ky", "en"];
const dicts: Record<Lang, Record<string, unknown>> = { ru, ky, en };

export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const raw = (dicts[lang][key] ?? dicts.ru[key] ?? key) as string;
  if (typeof raw !== "string") return key;
  return vars ? raw.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? "")) : raw;
}

export function translateList(lang: Lang, key: string): string[] {
  const v = dicts[lang][key] ?? dicts.ru[key];
  return Array.isArray(v) ? (v as string[]) : [];
}
