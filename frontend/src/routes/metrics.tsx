import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { CLIMATE_METRIC_KEYS, type Interval } from "../api/types";
import { ChartRangeBrush } from "../components/chart-range-brush";
import { ChartTooltip } from "../components/chart-tooltip";
import { Card, SectionTitle } from "../components/common";
import { useMetricsFilters } from "../context/metrics-filters-context";
import {
  buildSeriesChartData,
  computeAxisTicks,
  DATE_PRESETS,
  formatBucketLabel,
  INTERVALS,
  intervalLabel,
  resolveFilterRangeMs,
} from "../lib/chart-time";
import { formatDateTime, formatMetricValue, metricUnit } from "../lib/utils";

const METRIC_COLORS: Record<string, string> = {
  temperature: "#0284c7",
  humidity: "#16a34a",
  pressure: "#7c3aed",
};

const DEFAULT_RANGE_MS = 24 * 60 * 60_000;
const MIN_ZOOM_RANGE_MS = 5 * 60_000;

export function MetricsPage() {
  const filters = useMetricsFilters();
  const {
    metric,
    deviceId,
    location,
    datePreset,
    startDate,
    endDate,
    brushRangeMs,
    interval,
    chartStyle,
    tablesExpanded,
    setMetric,
    setDeviceId,
    setLocation,
    setDatePreset,
    setStartDate,
    setEndDate,
    setInterval,
    setChartStyle,
    setTablesExpanded,
    applyCustomRangeMs,
  } = filters;

  const filterRangeMs = useMemo(
    () => resolveFilterRangeMs({ datePreset, startDate, endDate, brushRangeMs }),
    [datePreset, startDate, endDate, brushRangeMs],
  );

  const queryStart = filterRangeMs.startMs != null ? new Date(filterRangeMs.startMs).toISOString() : undefined;
  const queryEnd = filterRangeMs.endMs != null ? new Date(filterRangeMs.endMs).toISOString() : undefined;

  const devicesQuery = useQuery({
    queryKey: ["devices-for-filters"],
    queryFn: api.getDevices,
    refetchInterval: 60_000,
  });

  const seriesQuery = useQuery({
    queryKey: ["telemetry-series", interval, deviceId, location, queryStart, queryEnd],
    queryFn: () =>
      api.getSeries({
        interval: interval === "auto" ? undefined : interval,
        device_id: deviceId ? Number(deviceId) : undefined,
        location: location || undefined,
        start_date: queryStart,
        end_date: queryEnd,
      }),
    refetchInterval: 60_000,
  });

  const currentReadingsQuery = useQuery({
    queryKey: ["current-readings"],
    queryFn: api.getCurrentReadings,
    refetchInterval: 60_000,
  });

  const effectiveInterval: Interval = seriesQuery.data?.interval ?? "1m";

  const domain = useMemo<[number, number]>(() => {
    if (seriesQuery.data) {
      return [new Date(seriesQuery.data.start).getTime(), new Date(seriesQuery.data.end).getTime()];
    }
    const endMs = filterRangeMs.endMs ?? Date.now();
    const startMs = filterRangeMs.startMs ?? endMs - DEFAULT_RANGE_MS;
    return [startMs, endMs];
  }, [seriesQuery.data, filterRangeMs]);

  const seriesPoints = useMemo(() => seriesQuery.data?.data ?? [], [seriesQuery.data]);

  const availableLocations = useMemo(() => {
    const names = new Set<string>();
    for (const device of devicesQuery.data?.data ?? []) {
      if (device.location?.display_name) {
        names.add(device.location.display_name);
      }
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [devicesQuery.data]);

  const zoomRange = (factor: number) => {
    const endMs = filterRangeMs.endMs ?? Date.now();
    const startMs = filterRangeMs.startMs ?? endMs - DEFAULT_RANGE_MS;
    const center = (startMs + endMs) / 2;
    const halfWidth = Math.max(((endMs - startMs) / 2) * factor, MIN_ZOOM_RANGE_MS / 2);
    applyCustomRangeMs(center - halfWidth, center + halfWidth);
  };

  const chartMetricKeys = useMemo(() => {
    if (metric) {
      return [metric];
    }
    return CLIMATE_METRIC_KEYS.filter((key) => seriesPoints.some((p) => p[key] != null));
  }, [seriesPoints, metric]);

  const chartData = useMemo(
    () => buildSeriesChartData(seriesPoints, effectiveInterval, domain),
    [seriesPoints, effectiveInterval, domain],
  );

  const xAxisTicks = useMemo(() => computeAxisTicks(domain, 8), [domain]);

  const chartYAxisIds = useMemo(() => chartMetricKeys.map((k) => `y_${k}`), [chartMetricKeys]);

  const showLine = chartStyle === "line" || chartStyle === "both";
  const showDots = chartStyle === "dots" || chartStyle === "both";

  type DotRenderProps = {
    key?: string;
    cx?: number;
    cy?: number;
    payload?: Record<string, unknown>;
  };

  // Plain markers only — exact values are available on hover via ChartTooltip.
  // An earlier version stamped a text label next to every Nth dot, but with
  // dense data (e.g. the 1-day/1440-point view) the labels overlapped each
  // other and became unreadable.
  const renderMetricDot = (metricKey: string, color: string) => {
    return ({ key, cx, cy, payload }: DotRenderProps) => {
      const value = payload?.[metricKey];
      if (cx == null || cy == null || typeof value !== "number") {
        return <circle key={key} cx={cx ?? 0} cy={cy ?? 0} r={0} fill="none" />;
      }
      return <circle key={key} cx={cx} cy={cy} r={3.5} fill={color} opacity={0.85} />;
    };
  };

  const chartElement = (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={chartData} margin={{ top: 32, right: 16, bottom: 24, left: 16 }}>
        <XAxis
          type="number"
          dataKey="time"
          domain={domain}
          scale="time"
          ticks={xAxisTicks}
          tick={{ fontSize: 12, fill: "#64748b" }}
          tickFormatter={(ts) => formatBucketLabel(Number(ts), effectiveInterval)}
        />

        {chartMetricKeys.map((metricKey, i) => {
          const color = METRIC_COLORS[metricKey] ?? "#0284c7";
          return (
            <YAxis
              key={metricKey}
              yAxisId={`y_${metricKey}`}
              orientation={i === 0 ? "left" : "right"}
              tick={{ fill: color, fontSize: 12 }}
              axisLine={{ stroke: color, opacity: 0.3 }}
              width={72}
              tickFormatter={(v) => {
                const unit = metricUnit(metricKey);
                const formatted = formatMetricValue(metricKey, v as number);
                return unit ? `${formatted} ${unit}` : formatted;
              }}
            />
          );
        })}
        <Tooltip
          cursor={{ strokeDasharray: "3 3", stroke: "#94a3b8", strokeWidth: 2 }}
          content={<ChartTooltip />}
        />

        {chartMetricKeys.map((metricKey, i) => {
          const color = METRIC_COLORS[metricKey] ?? "#0284c7";
          const yAxisId = chartYAxisIds[i];
          return (
            <Line
              key={metricKey}
              type="monotone"
              dataKey={metricKey}
              yAxisId={yAxisId}
              name={metricKey}
              stroke={showLine ? color : "transparent"}
              strokeWidth={showLine ? 2.5 : 0}
              dot={showDots ? renderMetricDot(metricKey, color) : undefined}
              activeDot={showDots ? { r: 5 } : undefined}
              connectNulls={false}
              isAnimationActive={false}
            />
          );
        })}
      </LineChart>
    </ResponsiveContainer>
  );

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Metrics Dashboard"
        subtitle="Explore telemetry as graphs and tables with quick filters."
      />

      <Card>
        {devicesQuery.isError || seriesQuery.isError ? (
          <p className="mb-3 rounded bg-rose-50 p-2 text-sm text-rose-700">
            Failed to load some data. Check backend connectivity and try refresh.
          </p>
        ) : null}
        {seriesQuery.isLoading ? (
          <p className="mb-3 rounded bg-slate-100 p-2 text-sm text-slate-600">Loading telemetry...</p>
        ) : null}
        <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
          <label className="text-sm font-semibold text-slate-700">
            Quick range
            <select
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
              value={datePreset}
              onChange={(e) => setDatePreset(e.target.value as typeof datePreset)}
            >
              {DATE_PRESETS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Metric
            <select
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              <option value="">All metrics</option>
              {CLIMATE_METRIC_KEYS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Device
            <select
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
            >
              <option value="">All devices</option>
              {(devicesQuery.data?.data ?? []).map((device) => (
                <option key={device.id} value={device.id}>
                  {device.display_name || device.hardware_id}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Location
            <select
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            >
              <option value="">All locations</option>
              {availableLocations.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Start date
            <input
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400 disabled:bg-slate-50 disabled:text-slate-500"
              type="date"
              value={startDate}
              disabled={datePreset !== "custom"}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </label>
          <label className="text-sm font-semibold text-slate-700">
            End date
            <input
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400 disabled:bg-slate-50 disabled:text-slate-500"
              type="date"
              value={endDate}
              disabled={datePreset !== "custom"}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
        </div>
      </Card>

      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="font-bold text-slate-900">Trend Graph</h3>
            <p className="mt-1 text-xs text-slate-600">
              {chartData.length} points • {intervalLabel(effectiveInterval)}
              {interval === "auto" ? " (auto)" : ""}
            </p>
            {seriesQuery.data?.downgraded ? (
              <p className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
                Showing {intervalLabel(effectiveInterval)} data — finer data isn't retained for this range.
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm font-semibold text-slate-700">
              Style
              <select
                className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
                value={chartStyle}
                onChange={(e) => setChartStyle(e.target.value as typeof chartStyle)}
              >
                <option value="line">Line</option>
                <option value="both">Dots + Line</option>
                <option value="dots">Dots</option>
              </select>
            </label>
            <label className="text-sm font-semibold text-slate-700">
              Interval
              <select
                className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
                value={interval}
                onChange={(e) =>
                  setInterval(e.target.value === "auto" ? "auto" : (e.target.value as Interval))
                }
              >
                <option value="auto">Auto ({intervalLabel(effectiveInterval)})</option>
                {INTERVALS.map((i) => (
                  <option key={i.key} value={i.key}>
                    {i.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-center gap-1" role="group" aria-label="Zoom range">
              <button
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-all duration-200 hover:border-slate-400 hover:bg-slate-50 active:scale-95"
                onClick={() => zoomRange(2)}
                title="Zoom out (double the time range)"
                type="button"
              >
                −
              </button>
              <button
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-all duration-200 hover:border-slate-400 hover:bg-slate-50 active:scale-95"
                onClick={() => zoomRange(0.5)}
                title="Zoom in (halve the time range)"
                type="button"
              >
                +
              </button>
            </div>
            <button
              className="rounded-lg bg-gradient-to-r from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-md transition-all duration-200 hover:shadow-lg hover:from-brand-700 hover:to-brand-800 active:scale-95"
              onClick={() => {
                seriesQuery.refetch();
                currentReadingsQuery.refetch();
              }}
              type="button"
            >
              🔄 Refresh
            </button>
          </div>
        </div>
        <div className="h-96 mt-4 rounded-lg border border-slate-200 bg-slate-50/50 p-4">
          <ChartRangeBrush domain={domain} onRangeSelected={(startMs, endMs) => applyCustomRangeMs(startMs, endMs)}>
            {chartElement}
          </ChartRangeBrush>
        </div>
      </Card>

      <Card>
        <button
          className="flex w-full items-center justify-between text-left font-bold text-slate-900 transition-colors duration-200 hover:text-brand-600"
          onClick={() => setTablesExpanded(!tablesExpanded)}
          type="button"
        >
          <span>📊 Current readings</span>
          <span className="text-sm font-semibold text-slate-500">{tablesExpanded ? "▼ Hide" : "▶ Show"}</span>
        </button>

        {tablesExpanded ? (
          <div className="mt-6">
            <div className="overflow-auto rounded-lg border border-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left font-semibold text-slate-700">
                  <tr>
                    <th className="px-4 py-3">Device</th>
                    <th className="px-4 py-3">Location</th>
                    <th className="px-4 py-3">Temperature</th>
                    <th className="px-4 py-3">Humidity</th>
                    <th className="px-4 py-3">Pressure</th>
                    <th className="px-4 py-3">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {(currentReadingsQuery.data ?? []).length === 0 ? (
                    <tr>
                      <td className="px-4 py-3 text-center text-slate-500" colSpan={6}>
                        No devices are currently online.
                      </td>
                    </tr>
                  ) : null}
                  {(currentReadingsQuery.data ?? []).map((item, idx) => (
                    <tr
                      className={idx % 2 === 0 ? "bg-white" : "bg-slate-50 hover:bg-slate-100"}
                      key={item.device_id}
                    >
                      <td className="px-4 py-3 font-semibold text-slate-900">
                        {item.display_name ?? item.device_id}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{item.location ?? "—"}</td>
                      <td className="px-4 py-3 font-semibold text-brand-600">
                        {item.temperature != null
                          ? `${formatMetricValue("temperature", item.temperature)} ${metricUnit("temperature")}`
                          : "—"}
                      </td>
                      <td className="px-4 py-3 font-semibold text-brand-600">
                        {item.humidity != null
                          ? `${formatMetricValue("humidity", item.humidity)} ${metricUnit("humidity")}`
                          : "—"}
                      </td>
                      <td className="px-4 py-3 font-semibold text-brand-600">
                        {item.pressure != null
                          ? `${formatMetricValue("pressure", item.pressure)} ${metricUnit("pressure")}`
                          : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-600">{formatDateTime(item.timestamp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
