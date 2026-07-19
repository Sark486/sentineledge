// Camera stream URLs go straight into <img src> — never through request<T>()
// in client.ts, which is JSON-only by design.
// Empty base = same-origin (the Vite dev proxy forwards /cameras to the agent);
// prod sets VITE_CAMERA_BASE_URL=http://<pi-ip>:8090 to reach the agent
// directly and keep long-lived MJPEG connections off the API origin.
const CAMERA_BASE_URL = import.meta.env.VITE_CAMERA_BASE_URL ?? "";

export const DEFAULT_CAMERA_HARDWARE_ID = "pi_cam_0";

export function buildStreamUrl(hardwareId: string): string {
  return `${CAMERA_BASE_URL}/cameras/${encodeURIComponent(hardwareId)}/stream`;
}
