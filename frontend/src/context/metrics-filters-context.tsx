import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";
import { CLIMATE_METRIC_KEYS, type Interval } from "../api/types";
import type { DatePreset } from "../lib/chart-time";

export type ChartStyle = "line" | "area" | "step";
export type { DatePreset };

export interface MetricsFiltersState {
  /** Metrics shown on the chart; selection only affects display, not the query. */
  metrics: string[];
  deviceId: string;
  location: string;
  datePreset: DatePreset;
  /** Explicit window used when datePreset is "custom" (brush, zoom or Apply). */
  customRangeMs: { startMs: number; endMs: number } | null;
  interval: Interval | "auto";
  chartStyle: ChartStyle;
  tablesExpanded: boolean;
}

const defaultState: MetricsFiltersState = {
  metrics: [...CLIMATE_METRIC_KEYS],
  deviceId: "",
  location: "",
  datePreset: "1d",
  customRangeMs: null,
  interval: "auto",
  chartStyle: "line",
  tablesExpanded: false,
};

interface MetricsFiltersContextValue extends MetricsFiltersState {
  setMetrics: (value: string[]) => void;
  setDeviceId: (value: string) => void;
  setLocation: (value: string) => void;
  setDatePreset: (value: DatePreset) => void;
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
      setMetrics: (metrics) => patch({ metrics }),
      setDeviceId: (deviceId) => patch({ deviceId }),
      setLocation: (location) => patch({ location }),
      setDatePreset: (datePreset) =>
        patch({ datePreset, customRangeMs: null, interval: "auto" }),
      setInterval: (interval) => patch({ interval }),
      setChartStyle: (chartStyle) => patch({ chartStyle }),
      setTablesExpanded: (tablesExpanded) => patch({ tablesExpanded }),
      applyCustomRangeMs: (startMs, endMs) => {
        const start = Math.min(startMs, endMs);
        const end = Math.max(startMs, endMs);
        patch({
          datePreset: "custom",
          customRangeMs: { startMs: start, endMs: end },
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
