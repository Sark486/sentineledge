import type { TooltipProps } from "recharts";
import { formatDateTime, formatMetricValue, metricUnit } from "../lib/utils";

type ChartTooltipProps = TooltipProps<number, string> & {
  /**
   * When set, the tooltip lists these metrics read from the hovered data row
   * (every chart row carries all metric columns) instead of only the series
   * of the hovered panel — so hovering any panel shows the full picture.
   */
  metricKeys?: string[];
  metricColors?: Record<string, string>;
};

export function ChartTooltip({
  active,
  payload,
  label,
  metricKeys,
  metricColors,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const row = payload[0]?.payload as Record<string, unknown> | undefined;
  const timestamp = row?.time as number | undefined;
  const timeLabel = timestamp != null ? formatDateTime(new Date(timestamp).toISOString()) : label;

  const entries = metricKeys
    ? metricKeys
        .map((key) => ({
          name: key,
          value: row?.[key],
          color: metricColors?.[key] ?? "#0284c7",
        }))
        .filter((e): e is { name: string; value: number; color: string } => typeof e.value === "number")
    : payload.map((entry) => ({
        name: String(entry.name),
        value: entry.value,
        color: entry.color,
      }));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xl">
      {/* Header with timestamp */}
      <p className="mb-3 text-sm font-bold text-slate-700 border-b border-slate-100 pb-2">
        📅 {timeLabel}
      </p>

      {/* Metrics list */}
      <div className="space-y-2.5">
        {entries.map((entry, index) => {
          const unit = metricUnit(entry.name);
          const formattedValue =
            typeof entry.value === "number" ? formatMetricValue(entry.name, entry.value) : entry.value;

          return (
            <div
              key={`${entry.name}-${index}`}
              className="flex items-center justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2"
            >
              <div className="flex items-center gap-2.5">
                {/* Color indicator dot */}
                <div
                  className="h-3 w-3 rounded-full shadow-sm"
                  style={{ backgroundColor: entry.color }}
                />
                {/* Metric name */}
                <span className="text-sm font-semibold text-slate-700 capitalize">
                  {entry.name}
                </span>
              </div>

              {/* Value with unit */}
              <div className="text-right">
                <span className="text-lg font-bold" style={{ color: entry.color }}>
                  {formattedValue}
                </span>
                {unit && <span className="text-xs text-slate-500 ml-1">{unit}</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Empty state */}
      {entries.length === 0 && (
        <p className="text-xs text-slate-500 text-center py-2">No data available</p>
      )}
    </div>
  );
}
