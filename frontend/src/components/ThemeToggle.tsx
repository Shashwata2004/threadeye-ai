"use client";

import { useLocale } from "next-intl";
import { useSyncExternalStore } from "react";

// Light/dark choice for the fabric skin, kept per browser in localStorage. The shell puts it on
// its root element as data-theme; the colours live in styles/fabric.css.
export type Theme = "light" | "dark";

const KEY = "te-theme";
const EVENT = "te-theme-change";
let memory: Theme = "light"; // used when storage is blocked (private window, policy)

function read(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) return saved === "dark" ? "dark" : "light";
  } catch {
    // fall through to the in-memory choice
  }
  return memory;
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange); // other tabs
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, read, () => "light");
}

function setTheme(next: Theme) {
  memory = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // not persisted: the in-memory choice still applies until the page reloads
  }
  window.dispatchEvent(new Event(EVENT));
}

// Label text stays out of messages/*.json on purpose: two words, no shared file to touch.
const LABELS = {
  en: { dark: "Dark mode", light: "Light mode" },
  bn: { dark: "ডার্ক মোড", light: "লাইট মোড" },
} as const;

export function ThemeToggle() {
  const theme = useTheme();
  const locale = useLocale() === "bn" ? "bn" : "en";
  const dark = theme === "dark";
  const label = dark ? LABELS[locale].light : LABELS[locale].dark;

  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={label}
      title={label}
      aria-pressed={dark}
      className="te-btn inline-flex h-8 w-8 items-center justify-center rounded-md"
    >
      {dark ? (
        // sun: switch back to light
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        // moon: switch to dark
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
        </svg>
      )}
    </button>
  );
}
