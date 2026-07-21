import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth.jsx";
import { formatApiError } from "@/lib/api";
import { Stethoscope, ArrowRight, User, BriefcaseMedical } from "lucide-react";
import { toast } from "sonner";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState("patient");
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    phone: "",
    age: "",
    gender: "Female",
    country: "Nigeria",
    state: "Lagos",
    specialty: "General Practitioner",
    license_number: "",
    years_experience: "",
    consultation_fee: "5000",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const payload = {
      role,
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      password: form.password,
      phone: form.phone || null,
    };
    if (role === "patient") {
      Object.assign(payload, {
        age: form.age ? parseInt(form.age) : null,
        gender: form.gender,
        country: form.country,
        state: form.state,
      });
    } else {
      Object.assign(payload, {
        specialty: form.specialty,
        license_number: form.license_number,
        years_experience: form.years_experience ? parseInt(form.years_experience) : null,
        consultation_fee: form.consultation_fee ? parseFloat(form.consultation_fee) : 5000,
      });
    }
    try {
      const user = await register(payload);
      toast.success("Account created");
      navigate(`/${user.role}`, { replace: true });
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grain-bg">
      <div className="max-w-3xl mx-auto p-6 lg:p-12">
        <Link to="/" className="flex items-center gap-2 mb-8" data-testid="brand-link">
          <div className="size-9 rounded-xl bg-gradient-to-br from-teal-600 to-blue-700 grid place-items-center text-white">
            <Stethoscope className="size-5" />
          </div>
          <span className="font-display text-xl">DocNow.NG</span>
        </Link>

        <div className="overline mb-3">Create your account</div>
        <h1 className="font-display text-4xl lg:text-5xl tracking-tight leading-tight">Join DocNow.NG</h1>
        <p className="mt-2 text-slate-600">Patients sign up instantly. Doctors are reviewed before going live.</p>

        <div className="mt-8 grid grid-cols-2 gap-3 max-w-md">
          {[
            { key: "patient", label: "I'm a patient", icon: User },
            { key: "doctor", label: "I'm a doctor", icon: BriefcaseMedical },
          ].map((r) => (
            <button
              key={r.key}
              type="button"
              onClick={() => setRole(r.key)}
              data-testid={`role-select-${r.key}`}
              className={[
                "rounded-2xl border p-4 text-left transition-all flex items-start gap-3",
                role === r.key ? "border-teal-600 bg-teal-50/40 ring-2 ring-teal-100" : "border-slate-200 bg-white hover:border-slate-300",
              ].join(" ")}
            >
              <r.icon className="size-5 text-teal-700" />
              <div>
                <div className="font-medium">{r.label}</div>
                <div className="text-xs text-slate-500">{r.key === "patient" ? "Symptoms, triage, consults." : "Practice & earn."}</div>
              </div>
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-8 card-soft space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Full name" testid="reg-fullname-input" value={form.full_name} onChange={set("full_name")} required />
            <Field label="Email" testid="reg-email-input" type="email" value={form.email} onChange={set("email")} required />
            <Field label="Password" testid="reg-password-input" type="password" value={form.password} onChange={set("password")} required hint="Min 6 characters" />
            <Field label="Phone" testid="reg-phone-input" value={form.phone} onChange={set("phone")} placeholder="+234…" />
          </div>

          {role === "patient" ? (
            <div className="grid sm:grid-cols-4 gap-4">
              <Field label="Age" testid="reg-age-input" type="number" value={form.age} onChange={set("age")} />
              <Select label="Gender" testid="reg-gender-select" value={form.gender} onChange={set("gender")} options={["Female", "Male", "Other"]} />
              <Field label="Country" testid="reg-country-input" value={form.country} onChange={set("country")} />
              <Field label="State" testid="reg-state-input" value={form.state} onChange={set("state")} />
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 gap-4">
              <Select label="Specialty" testid="reg-specialty-select" value={form.specialty} onChange={set("specialty")}
                options={["General Practitioner", "Pediatrician", "Cardiologist", "Dermatologist", "OB-GYN", "Psychiatrist", "Internal Medicine"]} />
              <Field label="License number" testid="reg-license-input" value={form.license_number} onChange={set("license_number")} required />
              <Field label="Years of experience" testid="reg-experience-input" type="number" value={form.years_experience} onChange={set("years_experience")} />
              <Field label="Consultation fee (NGN)" testid="reg-fee-input" type="number" value={form.consultation_fee} onChange={set("consultation_fee")} />
            </div>
          )}

          {error && (
            <div data-testid="register-error" className="rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm px-4 py-3">
              {error}
            </div>
          )}

          {role === "doctor" && (
            <div className="rounded-xl bg-blue-50/60 border border-blue-100 text-blue-900 text-xs px-4 py-3">
              Doctor accounts are reviewed by DocNow.NG admin. You'll have access to your dashboard immediately but won't appear in the patient queue until approved.
            </div>
          )}

          <button type="submit" disabled={loading} data-testid="register-submit-button" className="btn-primary w-full disabled:opacity-60">
            {loading ? "Creating account…" : <>Create account <ArrowRight className="size-4" /></>}
          </button>
        </form>

        <div className="mt-6 text-sm text-slate-500">
          Already have an account?{" "}
          <Link to="/login" className="text-teal-700 font-medium" data-testid="register-go-login">Sign in</Link>
        </div>
      </div>
    </div>
  );
}

function Field({ label, testid, hint, ...props }) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <input
        data-testid={testid}
        {...props}
        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
      />
      {hint && <div className="text-xs text-slate-400 mt-1">{hint}</div>}
    </div>
  );
}

function Select({ label, testid, value, onChange, options }) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <select
        data-testid={testid}
        value={value}
        onChange={onChange}
        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100 bg-white"
      >
        {options.map((o) => (<option key={o} value={o}>{o}</option>))}
      </select>
    </div>
  );
}
