import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout";
import { MetricsFiltersProvider } from "./context/metrics-filters-context";
import { CameraPage } from "./routes/camera";
import { DevicesPage } from "./routes/devices";
import { MetricsPage } from "./routes/metrics";

export default function App() {
  return (
    <MetricsFiltersProvider>
    <Routes>
      <Route element={<AppLayout />} path="/">
        <Route element={<Navigate replace to="/metrics" />} index />
        <Route element={<MetricsPage />} path="metrics" />
        <Route element={<DevicesPage />} path="devices" />
        <Route element={<CameraPage />} path="camera" />
      </Route>
    </Routes>
    </MetricsFiltersProvider>
  );
}
