import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { api } from "../api/client";
import type { DeviceRead, DeviceStatus } from "../api/types";
import { Card, SectionTitle, StatusBadge } from "../components/common";
import { formatDateTime, metricUnit, onlineStatus } from "../lib/utils";

const formSchema = z.object({
  display_name: z.string().optional(),
  location_name: z.string().min(1, "Location is required"),
  status: z.enum(["pending", "active", "blocked"]),
});

type FormValues = z.infer<typeof formSchema>;

export function DevicesPage() {
  const queryClient = useQueryClient();
  const [selectedDevice, setSelectedDevice] = useState<DeviceRead | null>(null);

  const devicesQuery = useQuery({
    queryKey: ["devices"],
    queryFn: api.getDevices,
    refetchInterval: 60_000,
  });

  const latestQuery = useQuery({
    queryKey: ["device-latest", selectedDevice?.id],
    queryFn: () => api.getDeviceLatest(selectedDevice!.id),
    enabled: Boolean(selectedDevice?.id),
    refetchInterval: 60_000,
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      display_name: "",
      location_name: "",
      status: "pending",
    },
  });

  useEffect(() => {
    if (!selectedDevice) {
      return;
    }
    form.reset({
      display_name: selectedDevice.display_name ?? "",
      location_name: selectedDevice.location?.display_name ?? "Unknown",
      status: selectedDevice.status as DeviceStatus,
    });
  }, [selectedDevice, form]);

  const updateMutation = useMutation({
    mutationFn: (values: FormValues) => api.updateDevice(selectedDevice!.id, values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["devices"] });
      await queryClient.invalidateQueries({ queryKey: ["device-latest", selectedDevice?.id] });
    },
  });

  return (
    <div className="space-y-6">
      <SectionTitle
        title="🔧 Devices Management"
        subtitle="View and manage device status, display name, and location."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="mb-4 font-bold text-slate-900">Connected Devices</h3>
          {devicesQuery.isLoading ? <p className="mb-2 text-sm text-slate-500">Loading devices...</p> : null}
          {devicesQuery.isError ? (
            <p className="mb-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 border border-rose-200">Failed to load devices.</p>
          ) : null}
          <div className="space-y-2">
            {(devicesQuery.data?.data.length ?? 0) === 0 ? (
              <p className="text-sm text-slate-500">No devices found.</p>
            ) : null}
            {(devicesQuery.data?.data ?? []).map((device) => {
              const isOnline = onlineStatus(device.last_seen);
              return (
                <button
                  className={`w-full rounded-lg border p-4 text-left transition-all duration-200 ${
                    selectedDevice?.id === device.id
                      ? "border-brand-600 bg-gradient-to-r from-brand-50 to-brand-100/50 shadow-md"
                      : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                  key={device.id}
                  onClick={() => setSelectedDevice(device)}
                  type="button"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <strong className="text-slate-900">{device.display_name || device.hardware_id}</strong>
                    <StatusBadge value={device.status} />
                  </div>
                  <div className="space-y-1 text-sm text-slate-600">
                    <div><span className="font-semibold text-slate-700">Hardware:</span> {device.hardware_id}</div>
                    <div><span className="font-semibold text-slate-700">Location:</span> {device.location?.display_name ?? "Unknown"}</div>
                    <div><span className="font-semibold text-slate-700">Last seen:</span> {formatDateTime(device.last_seen)}</div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="font-semibold text-slate-700">Connectivity:</span>
                      <StatusBadge value={isOnline ? "online" : "offline"} />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </Card>

        <Card>
          <h3 className="mb-4 font-bold text-slate-900">Device Details</h3>
          {!selectedDevice ? <p className="text-sm text-slate-500 bg-slate-50 p-4 rounded-lg">Select a device to view and edit details.</p> : null}
          {selectedDevice ? (
            <div className="space-y-6">
              <form
                className="space-y-4"
                onSubmit={form.handleSubmit(async (values) => {
                  await updateMutation.mutateAsync(values);
                })}
              >
                <label className="block text-sm font-semibold text-slate-700">
                  Display name
                  <input
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
                    {...form.register("display_name")}
                  />
                </label>
                <label className="block text-sm font-semibold text-slate-700">
                  Location
                  <input
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
                    {...form.register("location_name")}
                  />
                </label>
                <label className="block text-sm font-semibold text-slate-700">
                  Status
                  <select
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm transition-all duration-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 hover:border-slate-400"
                    {...form.register("status")}
                  >
                    <option value="pending">Pending</option>
                    <option value="active">Active</option>
                    <option value="blocked">Blocked</option>
                  </select>
                </label>
                <button
                  className="w-full rounded-lg bg-gradient-to-r from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-md transition-all duration-200 hover:shadow-lg hover:from-brand-700 hover:to-brand-800 active:scale-95 disabled:opacity-50"
                  type="submit"
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending ? "💾 Saving..." : "✓ Save Changes"}
                </button>
              </form>

              <div className="pt-4 border-t border-slate-200">
                <h4 className="mb-4 font-bold text-slate-900">📡 Latest Telemetry</h4>
                {latestQuery.isLoading ? <p className="text-sm text-slate-500">Loading latest telemetry...</p> : null}
                {latestQuery.isError ? (
                  <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 border border-rose-200">Failed to load latest telemetry.</p>
                ) : null}
                <div className="space-y-2 text-sm">
                  {(latestQuery.data?.length ?? 0) === 0 && !latestQuery.isLoading ? (
                    <p className="text-sm text-slate-500">No telemetry available for this device.</p>
                  ) : null}
                  {(latestQuery.data ?? []).map((reading, idx) => (
                    <div key={`${reading.timestamp}-${idx}`} className="space-y-1">
                      {([
                        ["temperature", reading.temperature],
                        ["humidity", reading.humidity],
                        ["pressure", reading.pressure],
                      ] as const)
                        .filter(([, value]) => value != null)
                        .map(([name, value], i) => (
                          <div
                            className={`flex justify-between items-center px-3 py-2 rounded-lg ${i % 2 === 0 ? "bg-slate-50" : "bg-white"}`}
                            key={name}
                          >
                            <span className="font-semibold text-slate-700 capitalize">{name}</span>
                            <span className="font-bold text-brand-600">
                              {value} <span className="text-slate-500 font-normal">{metricUnit(name)}</span>
                            </span>
                          </div>
                        ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </Card>
      </div>
    </div>
  );
}
