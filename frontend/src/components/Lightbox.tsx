"use client";

import { useTranslations } from "next-intl";
import { useEffect, type ReactNode } from "react";

/** A photo shown large in the middle of the screen. Closes with Esc or a click outside the photo. */
export function Lightbox({ src, alt, onClose, children }: { src: string; alt: string; onClose: () => void; children?: ReactNode }) {
  const t = useTranslations();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      onClick={onClose}
      data-testid="lightbox"
    >
      <div className="max-h-full max-w-3xl space-y-2 rounded-lg bg-white p-3 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className="max-h-[75vh] w-auto rounded" />
        <div className="flex items-start justify-between gap-3 text-sm">
          <div className="space-y-0.5">{children}</div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-100"
          >
            ✕ {t("verdict.close")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** URL of the large version of a defect photo: more fabric around it, higher resolution. */
export function largePhoto(cropUrl: string): string {
  return `${cropUrl}${cropUrl.includes("?") ? "&" : "?"}size=800&context=4`;
}
