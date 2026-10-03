import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";
import { LOCALE_COOKIE, toLocale } from "./constants";

// next-intl without i18n routing: the locale comes from a cookie, not the URL.
export default getRequestConfig(async () => {
  const store = await cookies();
  const locale = toLocale(store.get(LOCALE_COOKIE)?.value);
  return {
    locale,
    timeZone: "Asia/Dhaka",
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
