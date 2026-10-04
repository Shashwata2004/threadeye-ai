import type { ReactNode } from "react";

export const inputClass =
  "mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-brand-teal focus:outline-none";

export function Field({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`block ${wide ? "sm:col-span-2" : ""}`}>
      <span className="text-sm text-slate-700">{label}</span>
      {children}
    </label>
  );
}

export function Button({
  children,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" }) {
  const styles =
    variant === "primary"
      ? "bg-brand-navy text-white hover:opacity-90"
      : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100";
  return (
    <button
      type="button"
      {...props}
      className={`rounded-md px-4 py-2 text-sm font-semibold disabled:opacity-50 ${styles} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}
