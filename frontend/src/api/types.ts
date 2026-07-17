export type DeviceStatus = "pending" | "active" | "blocked";

export interface LocationRead {
  id: number;
  display_name: string;
}

export interface DeviceRead {
  id: number;
  hardware_id: string;
  display_name?: string | null;
  status: DeviceStatus;
  last_seen?: string | null;
  location?: {
    display_name: string;
  } | null;
}

export interface DeviceUpdateInput {
  display_name?: string | null;
  status?: DeviceStatus;
  location_name: string;
}

export interface ClimateReadingRead {
  timestamp: string;
  temperature: number | null;
  humidity: number | null;
  pressure: number | null;
  location_snapshot: string;
  device_id: number;
  device?: DeviceRead | null;
}

export const CLIMATE_METRIC_KEYS = ["temperature", "humidity", "pressure"] as const;
export type ClimateMetricKey = (typeof CLIMATE_METRIC_KEYS)[number];

export interface PaginatedResponse<T> {
  count: number;
  limit: number;
  offset: number;
  data: T[];
}

export interface TelemetryFilters {
  device_id?: number;
  location?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export type Interval = "1m" | "5m" | "1h";

export interface SeriesPoint {
  timestamp: string;
  device_id: number;
  temperature: number | null;
  humidity: number | null;
  pressure: number | null;
}

export interface SeriesResponse {
  interval: Interval;
  requested_interval: Interval | null;
  downgraded: boolean;
  start: string;
  end: string;
  data: SeriesPoint[];
}

export interface SeriesFilters {
  interval?: Interval;
  device_id?: number;
  location?: string;
  start_date?: string;
  end_date?: string;
}

export interface CurrentReadingRead {
  device_id: number;
  display_name: string | null;
  location: string | null;
  timestamp: string;
  temperature: number | null;
  humidity: number | null;
  pressure: number | null;
}
