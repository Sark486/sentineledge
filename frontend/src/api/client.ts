import { API_BASE_URL } from "../lib/utils";
import type {
  ClimateReadingRead,
  CurrentReadingRead,
  DeviceRead,
  DeviceUpdateInput,
  PaginatedResponse,
  SeriesFilters,
  SeriesResponse,
  TelemetryFilters,
} from "./types";

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail ?? "Request failed", response.status);
  }
  return (await response.json()) as T;
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  });
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export const api = {
  getDevices: () => request<PaginatedResponse<DeviceRead>>("/devices"),
  getDevice: (id: number) => request<DeviceRead>(`/devices/${id}`),
  updateDevice: (id: number, payload: DeviceUpdateInput) =>
    request<DeviceRead>(`/devices/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  getDeviceLatest: (id: number) =>
    request<ClimateReadingRead[]>(`/devices/${id}/latest`),
  getTelemetry: (filters: TelemetryFilters = {}) =>
    request<PaginatedResponse<ClimateReadingRead>>(
      `/telemetry${toQuery({
        ...filters,
        limit: filters.limit ?? 100,
        offset: filters.offset ?? 0,
      })}`,
    ),
  getTelemetryByDevice: (deviceId: number, filters: TelemetryFilters = {}) =>
    request<PaginatedResponse<ClimateReadingRead>>(
      `/telemetry/by-device/${deviceId}${toQuery(filters as Record<string, string | number | undefined>)}`,
    ),
  getTelemetryByLocation: (location: string, filters: TelemetryFilters = {}) =>
    request<PaginatedResponse<ClimateReadingRead>>(
      `/telemetry/by-location/${encodeURIComponent(location)}${toQuery(filters as Record<string, string | number | undefined>)}`,
    ),
  getSeries: (filters: SeriesFilters = {}) =>
    request<SeriesResponse>(
      `/telemetry/series${toQuery(filters as Record<string, string | number | undefined>)}`,
    ),
  getCurrentReadings: () => request<CurrentReadingRead[]>("/telemetry/latest"),
};

export { ApiError };
