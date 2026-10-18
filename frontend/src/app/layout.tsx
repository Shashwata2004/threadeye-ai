import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import localFont from "next/font/local";
import { Providers } from "@/components/Providers";
import "./globals.css";

// Self-hosted fonts (OFL 1.1): no CDN, so the edge box works without internet.
// IBM Plex Sans renders Latin; the browser falls back per glyph to Hind Siliguri for Bangla.
const latin = localFont({
  src: [
    { path: "../fonts/IBMPlexSans-400.woff2", weight: "400", style: "normal" },
    { path: "../fonts/IBMPlexSans-500.woff2", weight: "500", style: "normal" },
    { path: "../fonts/IBMPlexSans-600.woff2", weight: "600", style: "normal" },
    { path: "../fonts/IBMPlexSans-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-latin",
  display: "swap",
});
const bengali = localFont({
  src: [
    { path: "../fonts/HindSiliguri-400.woff2", weight: "400", style: "normal" },
    { path: "../fonts/HindSiliguri-500.woff2", weight: "500", style: "normal" },
    { path: "../fonts/HindSiliguri-600.woff2", weight: "600", style: "normal" },
    { path: "../fonts/HindSiliguri-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-bengali",
  display: "swap",
});

// Headings in the fabric skin (--te-serif); Bangla headings fall back to Hind Siliguri.
const sourceSerif = localFont({
  src: [
    { path: "../fonts/SourceSerif4-400.woff2", weight: "400", style: "normal" },
    { path: "../fonts/SourceSerif4-600.woff2", weight: "600", style: "normal" },
    { path: "../fonts/SourceSerif4-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-serif-latin",
  display: "swap",
});

// Bundled monospace: system mono fonts may draw ASCII digits with Bengali shapes when lang="bn",
// but IDs and measurements must always show Latin digits (PLAN.md §2 default 7).
const mono = localFont({
  src: [
    { path: "../fonts/IBMPlexMono-400.woff2", weight: "400", style: "normal" },
    { path: "../fonts/IBMPlexMono-500.woff2", weight: "500", style: "normal" },
  ],
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
    <html lang={locale} className={`${latin.variable} ${bengali.variable} ${sourceSerif.variable} ${mono.variable}`}>
      <body className="antialiased">
        <NextIntlClientProvider>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
