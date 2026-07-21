import MarketingNav from "@/components/MarketingNav";
import Footer from "@/components/Footer";
import { Link } from "react-router-dom";
import {
  Activity, ShieldCheck, Sparkles, HeartPulse, Stethoscope, Pill,
  MessageSquare, ClipboardList, ArrowRight, CheckCircle2,
} from "lucide-react";

const DOCTOR_IMG = "https://images.unsplash.com/photo-1678695972687-033fa0bdbac9";
const CONSULT_IMG = "https://images.unsplash.com/photo-1666886573531-48d2e3c2b684";

export default function Landing() {
  return (
    <div className="min-h-screen flex flex-col" data-testid="landing-page">
      <MarketingNav />

      {/* HERO */}
      <section className="grain-bg pt-28 pb-20 lg:pt-36 lg:pb-28">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 grid lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7 fade-up">
            <div className="overline mb-4">Healthcare access · Nigeria first</div>
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl leading-[1.05] tracking-tight">
              See a verified doctor in minutes — <span className="italic text-teal-700">guided by trustworthy AI</span>.
            </h1>
            <p className="mt-6 text-lg text-slate-600 max-w-2xl leading-relaxed">
              DocNow.NG connects patients across Africa to licensed doctors. Describe your symptoms,
              receive AI-assisted triage, get a consultation, prescription, and a clear care plan you can follow at home.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/signup" className="btn-primary" data-testid="hero-cta-register">
                Start a consultation <ArrowRight className="size-4" />
              </Link>
              <Link to="/login" className="btn-ghost-pill" data-testid="hero-cta-login">
                I have an account
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-teal-600" /> NDPA-aligned</span>
              <span className="inline-flex items-center gap-1.5"><CheckCircle2 className="size-3.5 text-teal-600" /> Verified doctors only</span>
              <span className="inline-flex items-center gap-1.5"><HeartPulse className="size-3.5 text-teal-600" /> Not a diagnostic tool</span>
            </div>
          </div>

          <div className="lg:col-span-5 relative fade-up" style={{ animationDelay: "120ms" }}>
            <div className="relative rounded-3xl overflow-hidden border border-slate-100 shadow-2xl">
              <img src={DOCTOR_IMG} alt="Doctor" className="w-full h-[520px] object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-slate-900/40 via-transparent" />
              <div className="absolute bottom-5 left-5 right-5 bg-white/85 backdrop-blur-xl rounded-2xl p-4 border border-white">
                <div className="flex items-center gap-2 text-xs text-teal-700 font-medium uppercase tracking-wider mb-1">
                  <Sparkles className="size-3.5" /> Live triage
                </div>
                <p className="text-sm text-slate-800 leading-snug">
                  "Fever for 3 days, body aches…" → Urgency:&nbsp;
                  <span className="font-semibold text-amber-700">Moderate</span> · Recommended: GP
                </p>
              </div>
            </div>
            <div className="hidden lg:block absolute -left-10 top-10 size-24 rounded-full bg-teal-200/40 blur-3xl" />
          </div>
        </div>
      </section>

      {/* TRUST STRIP */}
      <section className="border-y border-slate-100 bg-white py-6">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          {[
            { k: "5,000+", v: "Symptoms triaged" },
            { k: "120+", v: "Verified doctors" },
            { k: "<5 min", v: "Avg. wait time" },
            { k: "98%", v: "Care plan satisfaction" },
          ].map((s, i) => (
            <div key={i}>
              <div className="font-display text-3xl text-slate-900">{s.k}</div>
              <div className="text-xs text-slate-500 uppercase tracking-widest mt-1">{s.v}</div>
            </div>
          ))}
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="py-24">
        <div className="max-w-7xl mx-auto px-6 lg:px-12">
          <div className="max-w-2xl">
            <div className="overline mb-3">How it works</div>
            <h2 className="font-display text-3xl lg:text-5xl leading-tight">
              Built for the way Nigerians actually seek care.
            </h2>
          </div>
          <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { icon: MessageSquare, title: "Describe symptoms", body: "Share what you feel — duration, severity, history. Mobile-first and fast." },
              { icon: Sparkles, title: "AI-assisted triage", body: "GPT-5.2 produces a structured summary with urgency, red flags & suggested specialty." },
              { icon: Stethoscope, title: "Verified doctor", body: "A licensed doctor accepts the case, reviews triage, and chats with you." },
              { icon: ClipboardList, title: "Care plan & Rx", body: "Receive prescription, follow-up plan, warning signs and recommended tests." },
            ].map((s, i) => (
              <div key={i} className="card-soft hover:shadow-lg transition-shadow">
                <div className="size-11 rounded-xl bg-teal-50 grid place-items-center text-teal-700 mb-4">
                  <s.icon className="size-5" strokeWidth={1.6} />
                </div>
                <div className="font-display text-xl mb-2">{s.title}</div>
                <p className="text-sm text-slate-600 leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* DOCTORS BLOCK */}
      <section id="doctors" className="py-24 bg-gradient-to-b from-teal-50/40 to-transparent">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 grid lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-6">
            <div className="rounded-3xl overflow-hidden border border-slate-100 shadow-xl">
              <img src={CONSULT_IMG} alt="Doctor consultation" className="w-full h-[480px] object-cover" />
            </div>
          </div>
          <div className="lg:col-span-6">
            <div className="overline mb-3">For doctors</div>
            <h2 className="font-display text-3xl lg:text-5xl leading-tight">
              Practice from anywhere. Get paid fairly.
            </h2>
            <p className="mt-5 text-slate-600 leading-relaxed">
              Pick cases from a live queue. AI triage briefs you in seconds. Issue digital prescriptions, complete consultations, and earn <span className="font-medium text-slate-800">70% of every fee</span> — transparent revenue split, no surprises.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-slate-700">
              {[
                "Verified license & approval workflow",
                "AI-prepared patient summary before every consult",
                "Built-in prescription & care plan generator",
                "Ratings and earnings dashboard",
              ].map((b, i) => (
                <li key={i} className="flex items-start gap-2.5">
                  <CheckCircle2 className="size-5 text-teal-600 shrink-0 mt-0.5" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
            <Link to="/register" className="btn-primary mt-8" data-testid="doctors-cta">
              Apply as a doctor <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* TRUST */}
      <section id="trust" className="py-24">
        <div className="max-w-7xl mx-auto px-6 lg:px-12">
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { icon: ShieldCheck, t: "Compliance-first", b: "NDPA, GDPR-ready and HIPAA-inspired controls. Audit logging on every action." },
              { icon: Pill, t: "Doctor-issued only", b: "Prescriptions and care plans always require a licensed clinician — never AI alone." },
              { icon: Activity, t: "African realities", b: "Built around malaria, typhoid, hypertension, sickle cell — common conditions, real workflows." },
            ].map((b, i) => (
              <div key={i} className="card-soft">
                <div className="size-11 rounded-xl bg-blue-50 grid place-items-center text-blue-800 mb-4">
                  <b.icon className="size-5" strokeWidth={1.6} />
                </div>
                <div className="font-display text-xl mb-2">{b.t}</div>
                <p className="text-sm text-slate-600 leading-relaxed">{b.b}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-12">
          <div className="rounded-3xl bg-gradient-to-br from-teal-700 to-blue-900 text-white p-10 lg:p-14 relative overflow-hidden">
            <div className="absolute inset-0 opacity-20"
                 style={{ backgroundImage: "radial-gradient(circle at 80% 10%, white, transparent 40%)" }} />
            <div className="relative">
              <div className="text-xs uppercase tracking-[0.2em] text-teal-200 font-bold mb-3">Get started</div>
              <h3 className="font-display text-3xl lg:text-5xl max-w-2xl leading-tight">
                Healthcare you can reach, in the language of care.
              </h3>
              <p className="mt-4 text-white/80 max-w-xl">
                Create an account and start your first consultation in under 3 minutes.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Link to="/signup" data-testid="cta-bottom-register" className="inline-flex items-center justify-center gap-2 rounded-full bg-white text-teal-800 px-6 py-3 text-sm font-medium hover:bg-teal-50">
                  Create patient account <ArrowRight className="size-4" />
                </Link>
                <Link to="/login" data-testid="cta-bottom-login" className="inline-flex items-center justify-center gap-2 rounded-full border border-white/30 text-white px-6 py-3 text-sm font-medium hover:bg-white/10">
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
