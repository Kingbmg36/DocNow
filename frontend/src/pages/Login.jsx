import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth.jsx";
import { formatApiError } from "@/lib/api";
import { Stethoscope, ArrowRight } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await login(email, password);
      toast.success(`Welcome back, ${user.full_name}`);
      const from = location.state?.from?.pathname || `/${user.role}`;
      navigate(from, { replace: true });
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="grain-bg p-8 lg:p-14 flex flex-col">
        <Link to="/" className="flex items-center gap-2" data-testid="brand-link">
          <div className="size-9 rounded-xl bg-gradient-to-br from-teal-600 to-blue-700 grid place-items-center text-white">
            <Stethoscope className="size-5" />
          </div>
          <span className="font-display text-xl">DocNow.NG</span>
        </Link>
        <div className="my-auto max-w-md mx-auto w-full">
          <div className="overline mb-3">Welcome back</div>
          <h1 className="font-display text-4xl lg:text-5xl tracking-tight leading-tight">Sign in to continue care</h1>
          <p className="mt-3 text-slate-600">Patients, doctors and admins use the same sign-in.</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <div>
              <label htmlFor="email" className="text-sm font-medium text-slate-700">Email</label>
              <input
                id="email"
                data-testid="login-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label htmlFor="password" className="text-sm font-medium text-slate-700">Password</label>
              <input
                id="password"
                data-testid="login-password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div data-testid="login-error" className="rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm px-4 py-3">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="btn-primary w-full disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? "Signing in…" : <>Sign in <ArrowRight className="size-4" /></>}
            </button>
          </form>

          <div className="mt-6 text-sm text-slate-500">
            New as a doctor?{" "}
            <Link to="/register" className="text-teal-700 font-medium" data-testid="login-go-register">Apply here</Link>
            <span className="mx-2">·</span>
            Patient?{" "}
            <Link to="/signup" className="text-teal-700 font-medium" data-testid="login-go-signup">Sign in with phone</Link>
          </div>

          <div className="mt-10 rounded-2xl bg-white border border-slate-100 p-4 text-xs text-slate-600">
            <div className="font-medium text-slate-800 mb-1">Demo accounts</div>
            <div>Doctor: doctor@medinest.africa / Doctor@123</div>
            <div>Admin: admin@medinest.africa / Admin@123</div>
            <div className="mt-1">Patient: use <Link to="/signup" className="text-teal-700 font-medium">phone OTP</Link> with <span className="font-mono">+2348012345678</span> (dev mock code visible on screen)</div>
          </div>
        </div>
      </div>

      <div className="hidden lg:block bg-gradient-to-br from-teal-700 to-blue-900 relative overflow-hidden">
        <div className="absolute inset-0 opacity-30"
             style={{ backgroundImage: "radial-gradient(circle at 30% 20%, white, transparent 50%)" }} />
        <div className="relative h-full flex items-end p-14">
          <div className="text-white max-w-md">
            <div className="text-xs uppercase tracking-[0.2em] text-teal-200 font-bold mb-3">A note on safety</div>
            <p className="font-display text-3xl leading-snug">
              DocNow.NG is not a diagnostic tool. It connects you to a licensed clinician, faster.
            </p>
            <p className="mt-4 text-white/70 text-sm">
              For emergencies, please visit the nearest hospital or call your local emergency line immediately.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
