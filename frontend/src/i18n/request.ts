import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";
import { LOCALE_COOKIE, toLocale } from "./constants";
import bn from "../../messages/bn.json";
import en from "../../messages/en.json";

// Explicit dependencies keep both catalogs tracked when navigation labels change in dev.
const catalogs = {bn, en};

// next-intl without i18n routing: the locale comes from a cookie, not the URL.
export default getRequestConfig(async () => {
  const store = await cookies();
  const locale = toLocale(store.get(LOCALE_COOKIE)?.value);
  return {
    locale,
    timeZone: "Asia/Dhaka",
    messages: catalogs[locale],
  };
});
