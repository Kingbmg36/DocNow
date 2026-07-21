import { Link, useNavigate, useLocation } from "react-router-dom";
import { Stethoscope, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth.jsx";
import NotificationsBell from "./NotificationsBell";

export default function DashboardShell({ title, tabs, currentTab, onTabChange, children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#FDFCFB]">
      <header className="border-b border-slate-100 bg-white sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-5 lg:px-10 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="brand-link">
            <div className="size-9 rounded-xl bg-gradient-to-br from-teal-600 to-blue-700 grid place-items-center text-white">
              <Stethoscope className="size-5" strokeWidth={1.5} />
            </div>
            <div className="leading-tight">
              <div className="font-display text-lg font-medium">DocNow.NG</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">{user?.role}</div>
            </div>
          </Link>
          <div className="flex items-center gap-3">
            <NotificationsBell />
            <div className="text-right hidden sm:block">
              <div className="text-sm font-medium text-slate-800" data-testid="header-user-name">{user?.full_name}</div>
              <div className="text-xs text-slate-500">{user?.email}</div>
            </div>
            <button
              onClick={handleLogout}
              className="btn-ghost-pill"
              data-testid="logout-button"
              aria-label="Logout"
            >
              <LogOut className="size-4" /> Logout
            </button>
          </div>
        </div>
        {tabs && (
          <div className="max-w-[1400px] mx-auto px-5 lg:px-10 overflow-x-auto">
            <div className="flex items-center gap-1 -mb-px">
              {tabs.map((t) => {
                const active = currentTab === t.key;
                return (
                  <button
                    key={t.key}
                    onClick={() => onTabChange(t.key)}
                    data-testid={`tab-${t.key}`}
                    className={[
                      "px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors flex items-center gap-2",
                      active
                        ? "border-teal-600 text-teal-700"
                        : "border-transparent text-slate-500 hover:text-slate-800",
                    ].join(" ")}
                  >
                    {t.icon && <t.icon className="size-4" strokeWidth={1.7} />}
                    {t.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </header>

      <main className="flex-1 max-w-[1400px] w-full mx-auto px-5 lg:px-10 py-8">
        {title && <h1 className="font-display text-3xl lg:text-4xl mb-6 tracking-tight">{title}</h1>}
        {children}
      </main>

      <div className="bg-amber-50 border-t border-amber-100">
        <div className="max-w-[1400px] mx-auto px-5 lg:px-10 py-3 text-xs text-amber-900 text-center">
          ⚠ DocNow.NG does not provide medical diagnosis. If this is an emergency, visit the nearest hospital immediately.
        </div>
      </div>
    </div>
  );
}
