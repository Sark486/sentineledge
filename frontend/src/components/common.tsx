import type { PropsWithChildren } from "react";

export function Card({ children }: PropsWithChildren) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-md hover:shadow-lg transition-shadow duration-200">
      {children}
    </section>
  );
}

export function SectionTitle({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-6">
      <h2 className="text-2xl font-bold text-slate-900">{title}</h2>
      {subtitle ? (
        <p className="mt-1 text-sm text-slate-600 font-medium">{subtitle}</p>
      ) : null}
    </div>
  );
}

export function StatusBadge({ value }: { value: string }) {
  const styles: Record<string, string> = {
    active: "bg-emerald-100 text-emerald-700 border border-emerald-200",
    pending: "bg-amber-100 text-amber-700 border border-amber-200",
    blocked: "bg-rose-100 text-rose-700 border border-rose-200",
    online: "bg-emerald-100 text-emerald-700 border border-emerald-200",
    offline: "bg-slate-100 text-slate-700 border border-slate-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold transition-colors duration-200 ${
        styles[value] ?? styles.offline
      }`}
    >
      <span className={`mr-1.5 h-2 w-2 rounded-full ${value === "online" || value === "active" ? "bg-emerald-500" : "bg-slate-400"}`} />
      {value}
    </span>
  );
}
