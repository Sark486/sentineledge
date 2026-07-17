import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";
import type { Interval } from "../api/types";

export type ChartStyle = "dots" | "line" | "both";
export type DatePreset = "custom" | "1h" | "1d" | "1w" | "1m";

export interface MetricsFiltersState {
  metric: string;
  deviceId: string;
  location: string;
  datePreset: DatePreset;
  startDate: string;
  endDate: string;
  brushRangeMs: { startMs: number; endMs: number } | null;
  interval: Interval | "auto";
  chartStyle: ChartStyle;
  tablesExpanded: boolean;
}

const defaultState: MetricsFiltersState = {
  metric: "",
  deviceId: "",
  location: "",
  datePreset: "1d",
  startDate: "",
  endDate: "",
  brushRangeMs: null,
  interval: "auto",
  chartStyle: "line",
  tablesExpanded: false,
};

interface MetricsFiltersContextValue extends MetricsFiltersState {
  setMetric: (value: string) => void;
  setDeviceId: (value: string) => void;
  setLocation: (value: string) => void;
  setDatePreset: (value: DatePreset) => void;
  setStartDate: (value: string) => void;
  setEndDate: (value: string) => void;
  setBrushRangeMs: (value: { startMs: number; endMs: number } | null) => void;
  setInterval: (value: Interval | "auto") => void;
  setChartStyle: (value: ChartStyle) => void;
  setTablesExpanded: (value: boolean) => void;
  applyCustomRangeMs: (startMs: number, endMs: number) => void;
}

const MetricsFiltersContext = createContext<MetricsFiltersContextValue | null>(null);

export function MetricsFiltersProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<MetricsFiltersState>(defaultState);

  const patch = useCallback((partial: Partial<MetricsFiltersState>) => {
    setState((prev) => ({ ...prev, ...partial }));
  }, []);

  const value = useMemo<MetricsFiltersContextValue>(
    () => ({
      ...state,
      setMetric: (metric) => patch({ metric }),
      setDeviceId: (deviceId) => patch({ deviceId }),
      setLocation: (location) => patch({ location }),
      setDatePreset: (datePreset) =>
        patch({ datePreset, brushRangeMs: null, interval: "auto" }),
      setStartDate: (startDate) =>
        patch({ startDate, datePreset: "custom", brushRangeMs: null, interval: "auto" }),
      setEndDate: (endDate) =>
        patch({ endDate, datePreset: "custom", brushRangeMs: null, interval: "auto" }),
      setBrushRangeMs: (brushRangeMs) => patch({ brushRangeMs }),
      setInterval: (interval) => patch({ interval }),
      setChartStyle: (chartStyle) => patch({ chartStyle }),
      setTablesExpanded: (tablesExpanded) => patch({ tablesExpanded }),
      applyCustomRangeMs: (startMs, endMs) => {
        const start = Math.min(startMs, endMs);
        const end = Math.max(startMs, endMs);
        patch({
          datePreset: "custom",
          brushRangeMs: { startMs: start, endMs: end },
          startDate: msToDateInput(start),
          endDate: msToDateInput(end),
          interval: "auto",
        });
      },
    }),
    [state, patch],
  );

  return (
    <MetricsFiltersContext.Provider value={value}>{children}</MetricsFiltersContext.Provider>
  );
}

export function useMetricsFilters(): MetricsFiltersContextValue {
  const ctx = useContext(MetricsFiltersContext);
  if (!ctx) {
    throw new Error("useMetricsFilters must be used within MetricsFiltersProvider");
  }
  return ctx;
}

function msToDateInput(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
