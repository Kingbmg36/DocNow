import { Link } from "react-router-dom";
import { Stethoscope } from "lucide-react";
import { useAuth } from "@/lib/auth.jsx";

export default function MarketingNav() {
  const { user } = useAuth();
  return (
    <header className="fixed top-0 inset-x-0 z-40 backdrop-blur-xl bg-white/70 border-b border-slate-100">
      <div className="max-w-7xl mx-auto px-6 lg:px-12 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2" data-testid="brand-link">
          <div className="size-9 rounded-xl bg-gradient-to-br from-teal-600 to-blue-700 grid place-items-center text-white">
            <Stethoscope className="size-5" strokeWidth={1.5} />
          </div>
          <span className="font-display text-xl font-medium tracking-tight">DocNow.NG</span>
        </Link>
        <nav className="hidden md:flex items-center gap-8 text-sm text-slate-700">
          <a href="#how" className="hover:text-teal-700 transition-colors">How it works</a>
          <a href="#doctors" className="hover:text-teal-700 transition-colors">For doctors</a>
          <a href="#trust" className="hover:text-teal-700 transition-colors">Trust & safety</a>
        </nav>
        <div className="flex items-center gap-3">
          {user && user !== false ? (
            <Link
              to={`/${user.role}`}
              className="btn-primary"
              data-testid="nav-dashboard-link"
            >
              Open dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="btn-ghost-pill hidden sm:inline-flex" data-testid="nav-login">
                Sign in
              </Link>
              <Link to="/signup" className="btn-primary" data-testid="nav-register">
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
