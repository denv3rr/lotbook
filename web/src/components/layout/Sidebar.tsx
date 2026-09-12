import { motion } from "framer-motion";
import { NavLink } from "react-router-dom";
import { useApi } from "../../lib/api";

type NavItem = {
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  path: string;
};

type SidebarProps = {
  items: NavItem[];
};

export function Sidebar({ items }: SidebarProps) {
  const { data: diagnostics } = useApi<{
    trackers?: { count?: number; warning_count?: number; warnings?: string[] };
    system?: { hostname?: string; platform?: string };
  }>("/api/tools/diagnostics", { interval: 60000 });
  const { data: health } = useApi<{ status?: string }>("/api/health", { interval: 30000 });
  const trackerWarnings = diagnostics?.trackers?.warnings || [];
  const trackerCount = diagnostics?.trackers?.count ?? 0;
  const warningCount = diagnostics?.trackers?.warning_count ?? 0;
  const status = health?.status === "ok" ? "Online" : "Degraded";

  return (
    <aside className="w-60 border-r border-slate-900/80 p-6 space-y-8 bg-ink-950">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">[ LOTBOOK ]</h1>
        <p className="tag text-xs text-emerald-300">Copyright © 2025</p>
        <p className="tag text-xs text-emerald-300">Seperet LLC</p>
        <p className="tag text-xs text-emerald-300">https://seperet.com</p>
        <p className="text-sm text-slate-400 mt-2">
          Markets • Risk • World
        </p>
      </div>
      <nav className="space-y-2">
        {items.map(({ label, icon: Icon, path }) => (
          <NavLink key={label} to={path}>
            {({ isActive }) => (
              <motion.div
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left ${
                  isActive
                    ? "bg-slate-900/70 text-white"
                    : "text-slate-300 hover:bg-slate-900/40"
                }`}
                whileHover={{ x: 4 }}
                transition={{ type: "spring", stiffness: 120, damping: 12 }}
              >
                <Icon size={18} />
                <span className="text-sm">{label}</span>
              </motion.div>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="glass-panel rounded-2xl p-5">
        <p className="tag text-xs text-emerald-300">SYSTEM STATUS</p>
        <h3 className="text-lg font-semibold mt-2">{status}</h3>
        <p className="text-sm text-slate-400 mt-1">
          Trackers: {trackerCount} • Warnings: {warningCount}
        </p>
        {trackerWarnings.length ? (
          <p className="text-[11px] text-slate-500 mt-2">
            {trackerWarnings[0]}
          </p>
        ) : (
          <p className="text-[11px] text-slate-500 mt-2">
            {diagnostics?.system?.hostname
              ? `${diagnostics.system.hostname} • ${diagnostics.system.platform || "system"}`
              : "No tracker warnings."}
          </p>
        )}
      </div>
    </aside>
  );
}
