import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { CLIMATE_METRIC_KEYS, type Interval } from "../api/types";
import { ChartRangeBrush } from "../components/chart-range-brush";
import { ChartTooltip } from "../components/chart-tooltip";
import { Card, SectionTitle } from "../components/common";
import { useMetricsFilters, type DatePreset } from "../context/metrics-filters-context";
import {
  buildSeriesChartData,
  computeAxisTicks,
  DATE_PRESETS,
  formatBucketLabel,
  INTERVALS,
  intervalLabel,
  msToDateTimeLocal,
  parseDateTimeLocal,
  resolveFilterRangeMs,
} from "../lib/chart-time";
import { formatDateTime, formatMetricValue, metricUnit } from "../lib/utils";

const METRIC_COLORS: Record<string, string> = {
  temperature: "#0284c7",
  humidity: "#16a34a",
  pressure: "#7c3aed",
};

const MIN_ZOOM_RANGE_MS = 5 * 60_000;
const AUTO_REFRESH_MS = 60_000;

const inputClass =
  "mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400";

function MetricMultiSelect({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onDocPointerDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocPointerDown);
    return () => document.removeEventListener("mousedown", onDocPointerDown);
  }, [open]);

  const toggle = (key: string) => {
    onChange(
      selected.includes(key)
        ? selected.filter((k) => k !== key)
        : // Keep the canonical metric order regardless of click order.
          CLIMATE_METRIC_KEYS.filter((k) => k === key || selected.includes(k)),
    );
  };

  const summary =
    selected.length === CLIMATE_METRIC_KEYS.length
      ? "All metrics"
      : selected.length === 0
        ? "No metrics"
        : selected.join(", ");

  return (
    <div className="relative" ref={ref}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`${inputClass} flex items-center justify-between text-left`}
        onClick={() => setOpen(!open)}
        type="button"
      >
        <span className="truncate capitalize font-normal">{summary}</span>
        <span className="ml-2 text-xs text-slate-500">▾</span>
      </button>
      {open ? (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-slate-200 bg-white p-2 shadow-lg">
          {CLIMATE_METRIC_KEYS.map((key) => (
            <label
              className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
              key={key}
            >
              <input
                checked={selected.includes(key)}
                className="accent-brand-600"
                onChange={() => toggle(key)}
                type="checkbox"
              />
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: METRIC_COLORS[key] }}
              />
              <span className="capitalize">{key}</span>
              <span className="text-xs text-slate-500">({metricUnit(key)})</span>
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function MetricsPage() {
  const filters = useMetricsFilters();
  const {
    metrics,
    deviceId,
    location,
    datePreset,
    customRangeMs,
    interval,
    chartStyle,
    tablesExpanded,
    setMetrics,
    setDeviceId,
    setLocation,
    setDatePreset,
    setInterval,
    setChartStyle,
    setTablesExpanded,
    applyCustomRangeMs,
  } = filters;

  // "Now" anchor for preset ranges. Bumping it slides the window forward,
  // which changes the series query key and triggers a refetch — this is what
  // makes both the Refresh button and the periodic refresh pick up new data.
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  const filterRange = useMemo(
    () => resolveFilterRangeMs({ datePreset, customRangeMs, nowMs }),
    [datePreset, customRangeMs, nowMs],
  );

  const queryStart = new Date(filterRange.startMs).toISOString();
  const queryEnd = new Date(filterRange.endMs).toISOString();

  const devicesQuery = useQuery({
    queryKey: ["devices-for-filters"],
    queryFn: api.getDevices,
    refetchInterval: AUTO_REFRESH_MS,
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
    refetchInterval: AUTO_REFRESH_MS,
  });

  const currentReadingsQuery = useQuery({
    queryKey: ["current-readings"],
    queryFn: api.getCurrentReadings,
    refetchInterval: AUTO_REFRESH_MS,
  });

  const refresh = () => {
    setNowMs(Date.now());
    // Preset windows refetch on their own because the query key moves with
    // nowMs; a frozen custom window needs an explicit refetch.
    if (datePreset === "custom") {
      seriesQuery.refetch();
    }
    currentReadingsQuery.refetch();
  };

  const effectiveInterval: Interval = seriesQuery.data?.interval ?? "1m";

  const domain = useMemo<[number, number]>(() => {
    if (seriesQuery.data) {
      return [new Date(seriesQuery.data.start).getTime(), new Date(seriesQuery.data.end).getTime()];
    }
    return [filterRange.startMs, filterRange.endMs];
  }, [seriesQuery.data, filterRange]);

  const seriesPoints = useMemo(() => seriesQuery.data?.data ?? [], [seriesQuery.data]);

  // Device and location option lists filter each other so it's impossible to
  // pick a device/location combination that can't return data.
  const devices = useMemo(() => devicesQuery.data?.data ?? [], [devicesQuery.data]);

  const deviceOptions = useMemo(
    () => devices.filter((d) => !location || d.location?.display_name === location),
    [devices, location],
  );

  const locationOptions = useMemo(() => {
    const source = deviceId ? devices.filter((d) => String(d.id) === deviceId) : devices;
    const names = new Set<string>();
    for (const device of source) {
      if (device.location?.display_name) {
        names.add(device.location.display_name);
      }
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [devices, deviceId]);

  // If the loaded device list invalidates the current selection (e.g. the
  // selected device moved to another location), drop the stale selection.
  useEffect(() => {
    if (!devicesQuery.data) {
      return;
    }
    if (deviceId && !deviceOptions.some((d) => String(d.id) === deviceId)) {
      setDeviceId("");
    } else if (location && !locationOptions.includes(location)) {
      setLocation("");
    }
  }, [devicesQuery.data, deviceId, deviceOptions, location, locationOptions, setDeviceId, setLocation]);

  // From/To fields mirror whatever window is currently shown (preset, brush
  // or zoom). While the user is editing them we stop syncing until they hit
  // Apply or change the window some other way.
  const [draftStart, setDraftStart] = useState("");
  const [draftEnd, setDraftEnd] = useState("");
  const [rangeDirty, setRangeDirty] = useState(false);
  const [rangeError, setRangeError] = useState<string | null>(null);

  useEffect(() => {
    setRangeDirty(false);
    setRangeError(null);
  }, [datePreset, customRangeMs]);

  useEffect(() => {
    if (!rangeDirty) {
      setDraftStart(msToDateTimeLocal(filterRange.startMs));
      setDraftEnd(msToDateTimeLocal(filterRange.endMs));
    }
  }, [filterRange.startMs, filterRange.endMs, rangeDirty]);

  const applyDraftRange = () => {
    const startMs = parseDateTimeLocal(draftStart);
    const endMs = parseDateTimeLocal(draftEnd);
    if (startMs == null || endMs == null) {
      setRangeError("Enter both a start and an end date/time.");
      return;
    }
    if (endMs <= startMs) {
      setRangeError("Start must be before end.");
      return;
    }
    setRangeError(null);
    applyCustomRangeMs(startMs, endMs);
  };

  const onPresetChange = (value: DatePreset) => {
    if (value === "custom") {
      // Freeze the currently shown window instead of jumping somewhere else.
      applyCustomRangeMs(filterRange.startMs, filterRange.endMs);
    } else {
      setDatePreset(value);
    }
  };

  // Remember the last preset so "Reset zoom" can return to it after brushing.
  const lastPresetRef = useRef<Exclude<DatePreset, "custom">>("1d");
  useEffect(() => {
    if (datePreset !== "custom") {
      lastPresetRef.current = datePreset;
    }
  }, [datePreset]);

  const zoomRange = (factor: number) => {
    const now = Date.now();
    const { startMs, endMs } = filterRange;
    const center = (startMs + endMs) / 2;
    const halfWidth = Math.max(((endMs - startMs) / 2) * factor, MIN_ZOOM_RANGE_MS / 2);
    let newStart = center - halfWidth;
    let newEnd = center + halfWidth;
    if (newEnd > now) {
      // Never extend into the future: pin the right edge to now and keep the width.
      newStart -= newEnd - now;
      newEnd = now;
    }
    applyCustomRangeMs(newStart, newEnd);
  };

  const chartMetricKeys = useMemo(
    () => CLIMATE_METRIC_KEYS.filter((key) => metrics.includes(key)),
    [metrics],
  );

  const chartData = useMemo(
    () => buildSeriesChartData(seriesPoints, effectiveInterval, domain),
    [seriesPoints, effectiveInterval, domain],
  );

  const xAxisTicks = useMemo(() => computeAxisTicks(domain, 8), [domain]);

  const metricStats = useMemo(() => {
    const stats: Record<string, { min: number; max: number; avg: number }> = {};
    for (const key of chartMetricKeys) {
      let min = Infinity;
      let max = -Infinity;
      let total = 0;
      let count = 0;
      for (const row of chartData) {
        const value = row[key];
        if (typeof value === "number") {
          min = Math.min(min, value);
          max = Math.max(max, value);
          total += value;
          count += 1;
        }
      }
      if (count > 0) {
        stats[key] = { min, max, avg: total / count };
      }
    }
    return stats;
  }, [chartData, chartMetricKeys]);

  const noData =
    !seriesQuery.isLoading && seriesQuery.data != null && seriesPoints.length === 0;

  // Axis ticks need more precision than table values when the metric only
  // spans a few units (e.g. pressure ~1002–1004 hPa), otherwise neighbouring
  // ticks round to the same label.
  const formatAxisValue = (metricKey: string, value: number) => {
    const stats = metricStats[metricKey];
    const span = stats ? stats.max - stats.min : Infinity;
    if (span < 5) {
      return value.toFixed(1);
    }
    return formatMetricValue(metricKey, value);
  };

  // One panel per metric ("small multiples") instead of stacking several
  // y-axes on a single plot — each metric gets its own scale and stays legible.
  const renderMetricPanel = (metricKey: string, index: number) => {
    const color = METRIC_COLORS[metricKey] ?? "#0284c7";
    const isLast = index === chartMetricKeys.length - 1;
    const multi = chartMetricKeys.length > 1;
    const stats = metricStats[metricKey];
    const unit = metricUnit(metricKey);

    return (
      <div key={metricKey} className={multi ? (isLast ? "h-52" : "h-44") : "h-96"}>
        <div className="flex items-baseline justify-between px-2">
          <span className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="capitalize">{metricKey}</span>
            {unit ? <span className="font-normal normal-case text-slate-500">({unit})</span> : null}
          </span>
          {stats ? (
            <span className="text-xs text-slate-500">
              min {formatMetricValue(metricKey, stats.min)} · avg{" "}
              {formatMetricValue(metricKey, stats.avg)} · max {formatMetricValue(metricKey, stats.max)}
            </span>
          ) : null}
        </div>
        <ResponsiveContainer width="100%" height="88%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: isLast ? 8 : 0, left: 16 }}>
            <defs>
              <linearGradient id={`metric-fill-${metricKey}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis
              type="number"
              dataKey="time"
              domain={domain}
              scale="time"
              ticks={xAxisTicks}
              hide={!isLast}
              tick={{ fontSize: 12, fill: "#64748b" }}
              tickFormatter={(ts) => formatBucketLabel(Number(ts), effectiveInterval)}
            />
            <YAxis
              width={72}
              tick={{ fontSize: 12, fill: "#64748b" }}
              axisLine={{ stroke: "#cbd5e1" }}
              tickLine={{ stroke: "#cbd5e1" }}
              domain={["auto", "auto"]}
              tickFormatter={(v) => formatAxisValue(metricKey, v as number)}
            />
            <Tooltip
              cursor={{ strokeDasharray: "3 3", stroke: "#94a3b8", strokeWidth: 1.5 }}
              content={<ChartTooltip metricKeys={chartMetricKeys} metricColors={METRIC_COLORS} />}
            />
            {chartStyle === "area" ? (
              <Area
                type="monotone"
                dataKey={metricKey}
                name={metricKey}
                stroke={color}
                strokeWidth={2}
                fill={`url(#metric-fill-${metricKey})`}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ) : (
              <Line
                type={chartStyle === "step" ? "stepAfter" : "monotone"}
                dataKey={metricKey}
                name={metricKey}
                stroke={color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    );
  };

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
        {noData ? (
          <p className="mb-3 rounded bg-amber-50 p-2 text-sm text-amber-700">
            No data for the selected filters and time range.
          </p>
        ) : null}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm font-semibold text-slate-700">
            Quick range
            <select
              className={inputClass}
              value={datePreset}
              onChange={(e) => onPresetChange(e.target.value as DatePreset)}
            >
              {DATE_PRESETS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <div className="text-sm font-semibold text-slate-700">
            Metrics
            <MetricMultiSelect selected={metrics} onChange={setMetrics} />
          </div>
          <label className="text-sm font-semibold text-slate-700">
            Device
            <select className={inputClass} value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              <option value="">All devices</option>
              {deviceOptions.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.display_name || device.hardware_id}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Location
            <select className={inputClass} value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">All locations</option>
              {locationOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="text-sm font-semibold text-slate-700">
            From
            <input
              className={inputClass}
              type="datetime-local"
              value={draftStart}
              onChange={(e) => {
                setDraftStart(e.target.value);
                setRangeDirty(true);
                setRangeError(null);
              }}
            />
          </label>
          <label className="text-sm font-semibold text-slate-700">
            To
            <input
              className={inputClass}
              type="datetime-local"
              value={draftEnd}
              onChange={(e) => {
                setDraftEnd(e.target.value);
                setRangeDirty(true);
                setRangeError(null);
              }}
            />
          </label>
          <button
            className="rounded-lg bg-gradient-to-r from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-md transition-all duration-200 hover:shadow-lg hover:from-brand-700 hover:to-brand-800 active:scale-95 disabled:from-slate-300 disabled:to-slate-300 disabled:shadow-none"
            disabled={!rangeDirty}
            onClick={applyDraftRange}
            type="button"
          >
            Apply
          </button>
          {rangeError ? <p className="pb-2 text-sm text-rose-600">{rangeError}</p> : null}
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
                <option value="area">Area</option>
                <option value="step">Step</option>
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
                title="Zoom out (double the time range, capped at now)"
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
              {datePreset === "custom" ? (
                <button
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-all duration-200 hover:border-slate-400 hover:bg-slate-50 active:scale-95"
                  onClick={() => setDatePreset(lastPresetRef.current)}
                  title="Back to the last quick range"
                  type="button"
                >
                  Reset zoom
                </button>
              ) : null}
            </div>
            <button
              className="rounded-lg bg-gradient-to-r from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-md transition-all duration-200 hover:shadow-lg hover:from-brand-700 hover:to-brand-800 active:scale-95 disabled:opacity-60"
              disabled={seriesQuery.isFetching}
              onClick={refresh}
              type="button"
            >
              {seriesQuery.isFetching ? "⏳ Refreshing…" : "🔄 Refresh"}
            </button>
          </div>
        </div>
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50/50 p-4">
          {chartMetricKeys.length === 0 ? (
            <p className="flex h-40 items-center justify-center text-sm text-slate-500">
              Select at least one metric to display.
            </p>
          ) : (
            <ChartRangeBrush domain={domain} onRangeSelected={(startMs, endMs) => applyCustomRangeMs(startMs, endMs)}>
              <div className="space-y-1">
                {chartMetricKeys.map((metricKey, i) => renderMetricPanel(metricKey, i))}
              </div>
            </ChartRangeBrush>
          )}
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
