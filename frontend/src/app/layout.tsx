import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import localFont from "next/font/local";
import { Providers } from "@/components/Providers";
import "./globals.css";

// Self-hosted fonts (OFL 1.1): no CDN, so the edge box works without internet.
// Noto Sans renders Latin; the browser falls back per glyph to Noto Sans Bengali for Bangla.
const latin = localFont({
  src: [
    { path: "../fonts/NotoSans-Regular.ttf", weight: "400", style: "normal" },
    { path: "../fonts/NotoSans-Bold.ttf", weight: "700", style: "normal" },
  ],
  variable: "--font-latin",
  display: "swap",
});
const bengali = localFont({
  src: [
    { path: "../fonts/NotoSansBengali-Regular.ttf", weight: "400", style: "normal" },
    { path: "../fonts/NotoSansBengali-Bold.ttf", weight: "700", style: "normal" },
  ],
  variable: "--font-bengali",
  display: "swap",
});

// Bundled monospace: system mono fonts may draw ASCII digits with Bengali shapes when lang="bn",
// but IDs and measurements must always show Latin digits (PLAN.md §2 default 7).
const mono = localFont({
  src: [{ path: "../fonts/NotoSansMono-Regular.ttf", weight: "400", style: "normal" }],
  variable: "--font-mono-latin",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ThreadEye AI",
  description: "Fabric inspection assistant: defect → decision → claim → cutting → supplier",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={`${latin.variable} ${bengali.variable} ${mono.variable}`}>
      <body className="antialiased">
        <NextIntlClientProvider>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
