import type { TooltipProps } from "recharts";
import { formatDateTime, formatMetricValue, metricUnit } from "../lib/utils";

export function ChartTooltip({
  active,
  payload,
  label,
}: TooltipProps<number, string>) {
  if (!active || !payload) {
    return null;
  }

  // Extract timestamp from the first payload item
  const timestamp = payload?.[0]?.payload?.time as number | undefined;
  const timeLabel = timestamp != null ? formatDateTime(new Date(timestamp).toISOString()) : label;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xl">
      {/* Header with timestamp */}
      <p className="mb-3 text-sm font-bold text-slate-700 border-b border-slate-100 pb-2">
        📅 {timeLabel}
      </p>

      {/* Metrics list */}
      <div className="space-y-2.5">
        {payload.map((entry, index) => {
          const value = entry.value;
          const metricName = String(entry.name);
          const unit = metricUnit(metricName);
          const formattedValue = typeof value === "number" ? formatMetricValue(metricName, value) : value;

          return (
            <div
              key={`${metricName}-${index}`}
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
                  {metricName}
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
      {payload.length === 0 && (
        <p className="text-xs text-slate-500 text-center py-2">No data available</p>
      )}
    </div>
  );
}

