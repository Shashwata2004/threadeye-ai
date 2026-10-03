// Shared by server (request.ts) and client components. Keep free of server-only imports.
export const LOCALES = ["bn", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_COOKIE = "NEXT_LOCALE";
// Factory default is Bangla. After login the user's saved locale is written to the cookie.
export const DEFAULT_LOCALE: Locale = "bn";

export function toLocale(value: string | undefined): Locale {
  return value === "en" || value === "bn" ? value : DEFAULT_LOCALE;
}
