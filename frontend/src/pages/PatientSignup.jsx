import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { Stethoscope, ArrowRight, Phone, Sparkles, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

const NIGERIAN_STATES = [
  "Abia","Adamawa","Akwa Ibom","Anambra","Bauchi","Bayelsa","Benue","Borno","Cross River",
  "Delta","Ebonyi","Edo","Ekiti","Enugu","FCT - Abuja","Gombe","Imo","Jigawa","Kaduna","Kano",
  "Katsina","Kebbi","Kogi","Kwara","Lagos","Nasarawa","Niger","Ogun","Ondo","Osun","Oyo",
  "Plateau","Rivers","Sokoto","Taraba","Yobe","Zamfara",
];

export default function PatientSignup() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1 phone, 2 OTP, 3 profile
  const [phone, setPhone] = useState("+234");
  const [code, setCode] = useState("");
  const [devOtp, setDevOtp] = useState(null);
  const [regToken, setRegToken] = useState(null);
  const [profile, setProfile] = useState({
    full_name: "",
    dob: "",
    gender: "Female",
    state: "Lagos",
    language: "English",
  });
  const [consents, setConsents] = useState({
    care_delivery: true,
    analytics: false,
    model_training: false,
    research: false,
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const sendOtp = async (e) => {
    e?.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await api.post("/auth/otp/send", { phone: phone.trim() });
      setDevOtp(data.dev_otp || null);
      if (data.dev_otp) setCode(data.dev_otp);  // auto-fill for dev
      if (data.user_exists) {
        toast.info("Welcome back — log in with your OTP");
      }
      setStep(2);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally { setLoading(false); }
  };

  const verifyOtp = async (e) => {
    e?.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await api.post("/auth/otp/verify", { phone: phone.trim(), code: code.trim() });
      if (data.new_user) {
        setRegToken(data.registration_token);
        setStep(3);
      } else {
        if (data.access_token) localStorage.setItem("mdn_token", data.access_token);
        await refresh();
        toast.success(`Welcome back, ${data.user.full_name?.split(" ")[0] || ""}`);
        navigate("/patient", { replace: true });
      }
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally { setLoading(false); }
  };

  const completeSignup = async (e) => {
    e?.preventDefault();
    setError("");
    if (!profile.full_name.trim() || !profile.dob) {
      setError("Please enter your name and date of birth");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post(
        "/auth/register/patient",
        { phone: phone.trim(), ...profile, consents },
        { headers: { "X-Registration-Token": regToken } },
      );
      if (data.access_token) localStorage.setItem("mdn_token", data.access_token);
      await refresh();
      toast.success("Account created");
      navigate("/patient", { replace: true });
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2" data-testid="patient-signup-page">
      <div className="grain-bg p-8 lg:p-14 flex flex-col">
        <Link to="/" className="flex items-center gap-2" data-testid="brand-link">
          <div className="size-9 rounded-xl bg-gradient-to-br from-teal-600 to-blue-700 grid place-items-center text-white">
            <Stethoscope className="size-5" />
          </div>
          <span className="font-display text-xl">DocNow.NG</span>
        </Link>

        <div className="my-auto max-w-md mx-auto w-full">
          <div className="flex items-center gap-2 mb-6">
            {[1,2,3].map((s) => (
              <div key={s} className={`h-1.5 flex-1 rounded-full ${step >= s ? "bg-teal-600" : "bg-slate-200"}`} />
            ))}
          </div>

          {step === 1 && (
            <form onSubmit={sendOtp} className="space-y-5">
              <div>
                <div className="overline mb-2">Get started · 60 seconds</div>
                <h1 className="font-display text-4xl tracking-tight leading-tight">Sign in or sign up with your phone</h1>
                <p className="mt-3 text-slate-600 text-sm">We'll send a one-time code. No password to remember.</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Phone number</label>
                <div className="relative mt-1">
                  <Phone className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-slate-400" />
                  <input
                    data-testid="signup-phone-input"
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    required
                    className="w-full rounded-xl border border-slate-200 pl-10 pr-4 py-3 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                    placeholder="+234 801 234 5678"
                  />
                </div>
                <div className="text-xs text-slate-400 mt-1">Format: +234XXXXXXXXXX (E.164)</div>
              </div>
              {error && <div data-testid="signup-error" className="rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm px-4 py-3">{error}</div>}
              <button type="submit" disabled={loading} data-testid="send-otp-button" className="btn-primary w-full disabled:opacity-60">
                {loading ? "Sending code…" : <>Send code <ArrowRight className="size-4" /></>}
              </button>
              <p className="text-xs text-slate-500 text-center">
                Are you a <Link to="/login" className="text-teal-700 font-medium" data-testid="goto-email-login">doctor or admin</Link>? Use email sign-in.
              </p>
            </form>
          )}

          {step === 2 && (
            <form onSubmit={verifyOtp} className="space-y-5">
              <div>
                <div className="overline mb-2">Verify</div>
                <h1 className="font-display text-3xl tracking-tight leading-tight">Enter the code we sent</h1>
                <p className="mt-2 text-slate-600 text-sm">Sent to <span className="font-mono">{phone}</span></p>
                {devOtp && (
                  <div className="mt-3 rounded-xl bg-amber-50 border border-amber-100 text-amber-900 text-xs p-3" data-testid="dev-otp-hint">
                    <Sparkles className="size-3.5 inline mr-1" /> Dev mock OTP: <span className="font-mono font-bold">{devOtp}</span> · auto-filled
                  </div>
                )}
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">6-digit code</label>
                <input
                  data-testid="otp-code-input"
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                  className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3 text-center font-mono text-2xl tracking-widest outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                  placeholder="000000"
                />
              </div>
              {error && <div data-testid="otp-error" className="rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm px-4 py-3">{error}</div>}
              <button type="submit" disabled={loading} data-testid="verify-otp-button" className="btn-primary w-full disabled:opacity-60">
                {loading ? "Verifying…" : "Verify and continue"}
              </button>
              <button type="button" onClick={() => setStep(1)} className="text-sm text-slate-500 mx-auto block" data-testid="otp-change-phone">Change phone number</button>
            </form>
          )}

          {step === 3 && (
            <form onSubmit={completeSignup} className="space-y-4">
              <div>
                <div className="overline mb-2">Gate 1 · 60 seconds</div>
                <h1 className="font-display text-3xl tracking-tight leading-tight">Tell us about yourself</h1>
                <p className="mt-2 text-slate-600 text-sm">Just the basics. Medical details come later, only when you need them.</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Full name</label>
                <input data-testid="signup-fullname-input" value={profile.full_name} onChange={(e) => setProfile({...profile, full_name: e.target.value})} required
                  className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-slate-700">Date of birth</label>
                  <input data-testid="signup-dob-input" type="date" max={new Date().toISOString().slice(0,10)} value={profile.dob} onChange={(e) => setProfile({...profile, dob: e.target.value})} required
                    className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-700">Gender</label>
                  <select data-testid="signup-gender-select" value={profile.gender} onChange={(e) => setProfile({...profile, gender: e.target.value})}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 bg-white outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100">
                    <option>Female</option><option>Male</option><option>Other</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-slate-700">State</label>
                  <select data-testid="signup-state-select" value={profile.state} onChange={(e) => setProfile({...profile, state: e.target.value})}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 bg-white outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100">
                    {NIGERIAN_STATES.map(s => <option key={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-700">Language</label>
                  <select data-testid="signup-language-select" value={profile.language} onChange={(e) => setProfile({...profile, language: e.target.value})}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 bg-white outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100">
                    {["English","Yoruba","Igbo","Hausa","Pidgin"].map(l => <option key={l}>{l}</option>)}
                  </select>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 p-4 space-y-2.5">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-800">
                  <ShieldCheck className="size-4 text-teal-700" /> Consent (you can change any time)
                </div>
                <Consent k="care_delivery" required label="I agree to use DocNow.NG for healthcare access (required)" consents={consents} setConsents={setConsents} />
                <Consent k="analytics" label="Use anonymous analytics to improve the product" consents={consents} setConsents={setConsents} />
                <Consent k="model_training" label="Use my de-identified data to improve AI triage" consents={consents} setConsents={setConsents} />
                <Consent k="research" label="Share anonymized data with public-health research partners" consents={consents} setConsents={setConsents} />
              </div>

              {error && <div data-testid="register-error" className="rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm px-4 py-3">{error}</div>}
              <button type="submit" disabled={loading} data-testid="complete-signup-button" className="btn-primary w-full disabled:opacity-60">
                {loading ? "Creating account…" : "Create my account"}
              </button>
            </form>
          )}
        </div>
      </div>

      <div className="hidden lg:block bg-gradient-to-br from-teal-700 to-blue-900 relative overflow-hidden">
        <div className="absolute inset-0 opacity-30" style={{ backgroundImage: "radial-gradient(circle at 30% 20%, white, transparent 50%)" }} />
        <div className="relative h-full flex items-end p-14">
          <div className="text-white max-w-md">
            <div className="text-xs uppercase tracking-[0.2em] text-teal-200 font-bold mb-3">Designed for Nigeria</div>
            <p className="font-display text-3xl leading-snug">
              Phone OTP. No passwords. Your medical profile fills itself as you use the app — never in one big form.
            </p>
            <p className="mt-4 text-white/70 text-sm">
              Care-delivery consent is required. Everything else is optional and can be changed any time.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Consent({ k, label, required, consents, setConsents }) {
  return (
    <label className="flex items-start gap-2.5 text-sm text-slate-700 cursor-pointer">
      <input
        type="checkbox"
        data-testid={`consent-${k}`}
        checked={consents[k]}
        disabled={required}
        onChange={(e) => setConsents({ ...consents, [k]: e.target.checked })}
        className="mt-0.5 size-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
      />
      <span className="leading-snug">{label}</span>
    </label>
  );
}
