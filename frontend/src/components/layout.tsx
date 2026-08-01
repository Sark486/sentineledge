import { NavLink, Outlet } from "react-router-dom";
import { Logo } from "./logo";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-4 py-2 text-sm font-semibold transition-all duration-200 ${
    isActive
      ? "bg-brand-600 text-white shadow-md"
      : "text-slate-600 hover:text-brand-600 hover:bg-brand-50"
  }`;

export function AppLayout() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-sm sticky top-0 z-50 shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          {/* Logo and Title */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-lg">
              <Logo className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">SentinelEdge</h1>
              <p className="text-xs text-slate-500 font-medium">Smart Environment Monitoring</p>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex gap-1">
            <NavLink className={linkClass} to="/metrics">
              📊 Metrics
            </NavLink>
            <NavLink className={linkClass} to="/devices">
              🔧 Devices
            </NavLink>
            <NavLink className={linkClass} to="/camera">
              📹 Camera
            </NavLink>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="mt-16 border-t border-slate-200 bg-slate-50/50 py-8 text-center text-sm text-slate-500">
        <p>© 2024 SentinelEdge • Smart Environment Monitoring System</p>
      </footer>
    </div>
  );
}
