import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import DashboardShell from "@/components/DashboardShell";
import UrgencyBadge from "@/components/UrgencyBadge";
import Gate2Modal from "@/components/Gate2Modal";
import Gate3Panel from "@/components/Gate3Panel";
import CompletenessRing from "@/components/CompletenessRing";
import QuestionnaireRunner from "@/components/QuestionnaireRunner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { toast } from "sonner";
import {
  LayoutDashboard, PlusCircle, History, ClipboardList, Pill, Activity, Sparkles,
  Stethoscope, ArrowRight, Trash2, MessageSquare, Star, CalendarClock, Video, Phone, Zap,
  ClipboardEdit,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid,
} from "recharts";

const TABS = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "start", label: "Start Consultation", icon: PlusCircle },
  { key: "appointments", label: "Appointments", icon: CalendarClock },
  { key: "history", label: "History", icon: History },
  { key: "care_plans", label: "Care Plans", icon: ClipboardList },
  { key: "prescriptions", label: "Prescriptions", icon: Pill },
  { key: "vitals", label: "Vitals", icon: Activity },
  { key: "tips", label: "Health Tips", icon: Sparkles },
];

export default function PatientDashboard() {
  const { refresh, user } = useAuth();
  const [tab, setTab] = useState("overview");
  const [completion, setCompletion] = useState(null);
  const [signals, setSignals] = useState(null);
  const [showGate2, setShowGate2] = useState(false);
  const [intakeStatus, setIntakeStatus] = useState(null); // { completed, completed_at }
  const [showIntake, setShowIntake] = useState(false);

  const loadProfile = async () => {
    try {
      const { data } = await api.get("/profile/me");
      setCompletion(data.completion);
      setSignals(data.signals);
    } catch (e) { console.error("[loadProfile]", e); }
  };

  const loadIntakeStatus = async () => {
    try {
      const { data } = await api.get("/questionnaires/mine");
      const intake = (data.items || []).find((i) => i.code === "patient_intake");
      setIntakeStatus(intake || null);
      // Auto-prompt once per user per browser if not yet completed
      const dismissKey = `mdn_intake_dismissed_${user?.id || "anon"}`;
      const dismissed = localStorage.getItem(dismissKey);
      if (intake && !intake.completed && !dismissed) {
        setShowIntake(true);
      }
    } catch (e) { console.error("[loadIntakeStatus]", e); }
  };

  useEffect(() => { loadProfile(); loadIntakeStatus(); /* eslint-disable-next-line */ }, []);

  // Resume after a Paystack redirect. Live checkout sends the patient to
  // callback_url (FRONTEND_URL/patient?reference=…&trxref=…). We confirm here; the
  // webhook is the authoritative fulfiller, so this is idempotent UX confirmation.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const reference = params.get("reference") || params.get("trxref");
    if (!reference) return;
    let pending = {};
    try { pending = JSON.parse(localStorage.getItem("mdn_pending_payment") || "{}"); } catch { /* ignore */ }
    (async () => {
      try {
        await api.post("/payments/verify", { reference });
        const scheduled = pending.path === "scheduled";
        toast.success(scheduled ? "Appointment confirmed" : "Payment successful — case is in the queue");
        setTab(scheduled ? "appointments" : "history");
      } catch (e) {
        toast.error(formatApiError(e.response?.data?.detail) || "We couldn't confirm your payment yet. Check History or contact support.");
      } finally {
        localStorage.removeItem("mdn_pending_payment");
        window.history.replaceState({}, "", window.location.pathname); // avoid re-verify on refresh
      }
    })();
    /* eslint-disable-next-line */
  }, []);

  const dismissIntake = () => {
    localStorage.setItem(`mdn_intake_dismissed_${user?.id || "anon"}`, "1");
    setShowIntake(false);
  };

  const onIntakeSubmitted = async () => {
    setShowIntake(false);
    await loadProfile();
    await loadIntakeStatus();
    toast.success("Health profile saved");
  };

  const tryStart = () => {
    if (completion && !completion.gate_2_done) {
      setShowGate2(true);
    } else {
      setTab("start");
    }
  };

  const onGate2Complete = async () => {
    await loadProfile();
    await refresh();
    setShowGate2(false);
    setTab("start");
  };

  // Intercept tab change to "start"
  const handleTabChange = (key) => {
    if (key === "start" && completion && !completion.gate_2_done) {
      setShowGate2(true);
      return;
    }
    setTab(key);
  };

  return (
    <DashboardShell tabs={TABS} currentTab={tab} onTabChange={handleTabChange}>
      {tab === "overview" && (
        <Overview
          setTab={setTab}
          tryStart={tryStart}
          completion={completion}
          signals={signals}
          intakeStatus={intakeStatus}
          openIntake={() => setShowIntake(true)}
        />
      )}
      {tab === "start" && <StartConsultation onDone={(target) => setTab(target || "history")} />}
      {tab === "appointments" && <AppointmentsView />}
      {tab === "history" && <HistoryView />}
      {tab === "care_plans" && <CarePlansView />}
      {tab === "prescriptions" && <PrescriptionsView />}
      {tab === "vitals" && <VitalsView />}
      {tab === "tips" && <TipsView />}
      {showGate2 && <Gate2Modal onClose={() => setShowGate2(false)} onComplete={onGate2Complete} />}
      {showIntake && (
        <QuestionnaireRunner
          code="patient_intake"
          onClose={dismissIntake}
          onSubmitted={onIntakeSubmitted}
        />
      )}
    </DashboardShell>
  );
}

function Overview({ setTab, tryStart, completion, signals, intakeStatus, openIntake }) {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [carePlans, setCarePlans] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [c, cp] = await Promise.all([
          api.get("/cases/mine"),
          api.get("/care-plans/mine"),
        ]);
        setCases(c.data); setCarePlans(cp.data);
      } catch (e) { console.error(e); }
    })();
  }, []);

  const active = cases.find((c) => ["queued", "in_consultation", "assigned", "scheduled"].includes(c.status));
  const completed = cases.filter((c) => c.status === "completed").length;

  return (
    <div className="space-y-8 fade-up" data-testid="patient-overview">
      {intakeStatus && !intakeStatus.completed && (
        <div className="rounded-2xl border border-teal-200 bg-gradient-to-r from-teal-50 to-blue-50 p-5 flex items-center justify-between gap-4 flex-wrap" data-testid="intake-banner">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="size-10 rounded-xl bg-white text-teal-700 grid place-items-center shrink-0">
              <ClipboardEdit className="size-5" />
            </div>
            <div className="min-w-0">
              <div className="text-xs uppercase tracking-widest text-teal-800 font-bold">Build your health profile</div>
              <div className="font-display text-lg leading-tight mt-0.5">Six short sections — 5 minutes</div>
              <p className="text-xs text-slate-600 mt-1 max-w-xl">
                Helps your doctor, sharpens AI triage, and unlocks personalised care plans. You can pause and resume any time.
              </p>
            </div>
          </div>
          <button onClick={openIntake} className="btn-primary shrink-0" data-testid="intake-banner-cta">
            Start now <ArrowRight className="size-4" />
          </button>
        </div>
      )}
      {intakeStatus && intakeStatus.completed && (
        <div className="hidden" data-testid="intake-completed-flag" />
      )}
      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-3xl bg-gradient-to-br from-teal-700 to-blue-900 text-white p-8 relative overflow-hidden">
          <div className="absolute inset-0 opacity-25"
               style={{ backgroundImage: "radial-gradient(circle at 80% 20%, white, transparent 50%)" }} />
          <div className="relative">
            <div className="text-xs uppercase tracking-[0.2em] text-teal-200 font-bold mb-3">Hello, {user?.full_name?.split(" ")[0]}</div>
            <h2 className="font-display text-3xl lg:text-4xl leading-tight max-w-md">How are you feeling today?</h2>
            <p className="text-white/80 mt-3 max-w-md text-sm">Start a consultation in under 3 minutes — describe symptoms, get AI triage, see a doctor.</p>
            <button
              onClick={tryStart}
              data-testid="overview-start-cta"
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-white text-teal-800 px-6 py-3 text-sm font-medium hover:bg-teal-50"
            >
              Start consultation <ArrowRight className="size-4" />
            </button>
          </div>
        </div>
        <div className="card-soft" data-testid="profile-completeness-card">
          <div className="overline mb-3">Your profile</div>
          {completion ? (
            <>
              <CompletenessRing percent={completion.overall_percent} label="Complete" />
              <div className="mt-4 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">Gate 1 · Basics</span>
                  <span className={completion.gate_1_done ? "text-green-600 font-medium" : "text-amber-600"}>{completion.gate_1_progress}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">Gate 2 · Medical essentials</span>
                  <span className={completion.gate_2_done ? "text-green-600 font-medium" : "text-amber-600"}>{completion.gate_2_progress}%</span>
                </div>
              </div>
              {signals?.next_best_actions?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">Next best action</div>
                  <div className="text-sm font-medium text-slate-800">{signals.next_best_actions[0].title}</div>
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-slate-400">Loading…</div>
          )}
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card-soft" data-testid="active-case-card">
          <div className="overline mb-2">Active case</div>
          {active ? (
            <>
              <div className="flex items-center justify-between gap-2">
                <div className="font-display text-lg">{active.symptoms?.slice(0, 60)}</div>
                <UrgencyBadge level={active.urgency} />
              </div>
              <div className="text-xs text-slate-500 mt-1">Status: <span className="capitalize">{active.status.replace("_", " ")}</span></div>
            </>
          ) : (
            <div className="text-sm text-slate-500">No active case. Start one when you need care.</div>
          )}
        </div>
        <Stat icon={Stethoscope} label="Past consultations" value={completed} />
        <Stat icon={Activity} label="Track" value="Vitals" sub="Add today's reading" onClick={() => setTab("vitals")} />
      </div>

      {signals && (
        <div className="card-soft" data-testid="signals-strip">
          <div className="grid sm:grid-cols-3 gap-4 text-sm">
            <div>
              <div className="overline mb-1">Risk score</div>
              <div className="font-display text-2xl">{signals.risk_score}<span className="text-base text-slate-400">/100</span></div>
            </div>
            <div>
              <div className="overline mb-1">Triage priority</div>
              <div className="font-display text-2xl">{signals.triage_priority}</div>
            </div>
            <div>
              <div className="overline mb-1">Care segment</div>
              <div className="font-display text-2xl capitalize">{signals.care_segment.replace(/,/g, ", ")}</div>
            </div>
          </div>
        </div>
      )}

      <Gate3Panel />

      <div className="card-soft">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="overline mb-1">Recent activity</div>
            <h3 className="font-display text-xl">Your latest cases</h3>
          </div>
          <button className="btn-ghost-pill" onClick={() => setTab("history")} data-testid="overview-view-history">View all</button>
        </div>
        {cases.length === 0 ? (
          <EmptyState text="You haven't started a consultation yet." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {cases.slice(0, 5).map((c) => (
              <li key={c.id} className="py-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm text-slate-800 line-clamp-1">{c.symptoms}</div>
                  <div className="text-xs text-slate-500">{new Date(c.created_at).toLocaleString()} · {c.status.replace("_", " ")}</div>
                </div>
                <UrgencyBadge level={c.urgency} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value, sub, onClick }) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className="card-soft text-left disabled:cursor-default w-full"
    >
      <div className="size-10 rounded-xl bg-teal-50 text-teal-700 grid place-items-center mb-3">
        <Icon className="size-5" strokeWidth={1.6} />
      </div>
      <div className="text-xs uppercase tracking-widest text-slate-500">{label}</div>
      <div className="font-display text-3xl mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </button>
  );
}

function EmptyState({ text }) {
  return (
    <div className="py-10 text-center text-sm text-slate-500" data-testid="empty-state">{text}</div>
  );
}

// ============= START CONSULTATION WIZARD =============
import TriageResultCard from "@/components/TriageResultCard";

function StartConsultation({ onDone }) {
  const [step, setStep] = useState(1);
  const [symptoms, setSymptoms] = useState("");
  const [duration, setDuration] = useState("1-3 days");
  const [severity, setSeverity] = useState("moderate");
  const [notes, setNotes] = useState("");
  const [triage, setTriage] = useState(null);
  const [path, setPath] = useState(null); // 'urgent' | 'scheduled'
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [mode, setMode] = useState("video"); // 'video' | 'call'
  const [caseObj, setCaseObj] = useState(null);
  const [paymentRef, setPaymentRef] = useState(null);
  const [authUrl, setAuthUrl] = useState(null);
  const [payLive, setPayLive] = useState(false);
  const [loading, setLoading] = useState(false);

  const runTriage = async () => {
    if (!symptoms.trim()) { toast.error("Please describe your symptoms"); return; }
    setLoading(true);
    try {
      const { data } = await api.post("/triage", { symptoms, duration, severity, notes });
      setTriage(data);
      // Default path suggestion: Emergency/High → urgent, otherwise scheduled
      const suggested = ["Emergency", "High"].includes(data.urgency) ? "urgent" : "scheduled";
      setPath(suggested);
      setStep(2);
      if (suggested === "scheduled") loadSlots(data.recommended_specialty);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Triage failed");
    } finally { setLoading(false); }
  };

  const loadSlots = async (specialty) => {
    try {
      const { data } = await api.get(`/appointments/slots${specialty ? `?specialty=${encodeURIComponent(specialty)}` : ""}`);
      setSlots(data.slots || []);
      if (data.slots?.length) setSelectedSlot(data.slots[0]);
    } catch (e) {
      console.error(e);
    }
  };

  const choosePath = async (p) => {
    setPath(p);
    if (p === "scheduled" && slots.length === 0) {
      loadSlots(triage?.recommended_specialty);
    }
  };

  const submitCase = async () => {
    if (path === "scheduled" && !selectedSlot) { toast.error("Please pick a slot"); return; }
    setLoading(true);
    try {
      const { data: caseData } = await api.post("/cases", { symptoms, duration, severity, notes, triage });
      setCaseObj(caseData);
      // If scheduled, book the appointment first
      if (path === "scheduled") {
        await api.post("/appointments", {
          case_id: caseData.id,
          doctor_id: selectedSlot.doctor.id,
          scheduled_for: selectedSlot.scheduled_for,
          mode,
        });
      }
      const fee = path === "scheduled" ? (selectedSlot?.doctor?.consultation_fee || 5000) : 5000;
      const { data: pay } = await api.post("/payments/initialize", { case_id: caseData.id, amount: fee, currency: "NGN" });
      setPaymentRef(pay.reference);
      setAuthUrl(pay.authorization_url);
      setPayLive(!!pay.live);
      setStep(3);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed");
    } finally { setLoading(false); }
  };

  // Live mode: hand off to Paystack's hosted checkout. We persist the path so the
  // dashboard can show the right confirmation when Paystack redirects back.
  const payWithPaystack = () => {
    localStorage.setItem("mdn_pending_payment", JSON.stringify({ reference: paymentRef, path, mode }));
    window.location.href = authUrl;
  };

  // Stub/dev mode: no real checkout — verify directly.
  const confirmPayment = async () => {
    setLoading(true);
    try {
      await api.post("/payments/verify", { reference: paymentRef });
      toast.success(path === "scheduled" ? "Appointment confirmed" : "Payment successful — case is in the queue");
      setStep(4);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Payment failed");
    } finally { setLoading(false); }
  };

  const fmtSlot = (iso) => {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="max-w-3xl mx-auto fade-up" data-testid="start-consultation-wizard">
      <div className="flex items-center justify-between mb-6">
        {["Symptoms", "AI Triage & Path", "Payment", "Done"].map((s, i) => (
          <div key={i} className="flex items-center gap-2 flex-1">
            <div className={[
              "size-8 rounded-full grid place-items-center text-xs font-medium",
              step > i + 1 ? "bg-teal-600 text-white" :
              step === i + 1 ? "bg-teal-100 text-teal-700 ring-2 ring-teal-300" :
              "bg-slate-100 text-slate-400",
            ].join(" ")}>{i + 1}</div>
            <div className={`text-sm ${step === i + 1 ? "text-slate-800 font-medium" : "text-slate-500"}`}>{s}</div>
            {i < 3 && <div className="flex-1 h-px bg-slate-200 mx-2" />}
          </div>
        ))}
      </div>

      {step === 1 && (
        <div className="card-elevated space-y-5">
          <div>
            <div className="overline mb-2">Step 1</div>
            <h2 className="font-display text-2xl">Describe your symptoms</h2>
            <p className="text-sm text-slate-500 mt-1">Be specific — when did it start, where does it hurt, how severe.</p>
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">Symptoms</label>
            <textarea
              data-testid="triage-symptoms-input"
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              rows={5}
              className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
              placeholder="e.g., Fever for 3 days, body aches, mild headache, low appetite"
            />
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-slate-700">Duration</label>
              <select data-testid="triage-duration-select" value={duration} onChange={(e) => setDuration(e.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 bg-white focus:border-teal-600 focus:ring-2 focus:ring-teal-100">
                {["<1 day", "1-3 days", "3-7 days", "1-2 weeks", "more than 2 weeks"].map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Severity</label>
              <select data-testid="triage-severity-select" value={severity} onChange={(e) => setSeverity(e.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 bg-white focus:border-teal-600 focus:ring-2 focus:ring-teal-100">
                {["mild", "moderate", "severe"].map((d) => (<option key={d}>{d}</option>))}
              </select>
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">Additional notes (optional)</label>
            <textarea
              data-testid="triage-notes-input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
            />
          </div>
          <button onClick={runTriage} disabled={loading} data-testid="triage-run-button" className="btn-primary disabled:opacity-60">
            {loading ? "Analyzing…" : <>Run AI triage <Sparkles className="size-4" /></>}
          </button>
        </div>
      )}

      {step === 2 && triage && (
        <div className="space-y-5">
          <TriageResultCard triage={triage} />

          <div className="card-elevated" data-testid="path-chooser">
            <div className="overline mb-2">Step 2 · Choose how to consult</div>
            <h3 className="font-display text-xl mb-4">How would you like to see a doctor?</h3>
            <div className="grid sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => choosePath("urgent")}
                data-testid="path-urgent"
                className={[
                  "rounded-2xl border p-4 text-left transition-all",
                  path === "urgent" ? "border-teal-600 bg-teal-50/40 ring-2 ring-teal-100" : "border-slate-200 hover:border-slate-300",
                ].join(" ")}
              >
                <div className="flex items-center gap-2 mb-1.5 text-red-700">
                  <Zap className="size-4" />
                  <span className="text-xs uppercase tracking-widest font-bold">Urgent</span>
                </div>
                <div className="font-medium">Join the live queue</div>
                <div className="text-xs text-slate-500 mt-1">First available doctor picks up your case. Usually within minutes.</div>
              </button>
              <button
                type="button"
                onClick={() => choosePath("scheduled")}
                data-testid="path-scheduled"
                className={[
                  "rounded-2xl border p-4 text-left transition-all",
                  path === "scheduled" ? "border-teal-600 bg-teal-50/40 ring-2 ring-teal-100" : "border-slate-200 hover:border-slate-300",
                ].join(" ")}
              >
                <div className="flex items-center gap-2 mb-1.5 text-teal-700">
                  <CalendarClock className="size-4" />
                  <span className="text-xs uppercase tracking-widest font-bold">Schedule</span>
                </div>
                <div className="font-medium">Book a video or call appointment</div>
                <div className="text-xs text-slate-500 mt-1">Pick a time and mode. We confirm a doctor immediately.</div>
              </button>
            </div>

            {path === "scheduled" && (
              <div className="mt-6 space-y-4" data-testid="slot-picker">
                <div>
                  <div className="overline mb-2">Mode</div>
                  <div className="grid grid-cols-2 gap-2 max-w-md">
                    {[
                      { key: "video", label: "Video call", icon: Video },
                      { key: "call", label: "Voice call", icon: Phone },
                    ].map((m) => (
                      <button
                        key={m.key}
                        type="button"
                        onClick={() => setMode(m.key)}
                        data-testid={`mode-${m.key}`}
                        className={[
                          "rounded-xl border px-4 py-3 flex items-center gap-2 text-sm",
                          mode === m.key ? "border-teal-600 bg-teal-50/40 ring-2 ring-teal-100" : "border-slate-200 hover:border-slate-300",
                        ].join(" ")}
                      >
                        <m.icon className="size-4" /> {m.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="overline mb-2">Suggested slots {triage?.recommended_specialty ? `· ${triage.recommended_specialty}` : ""}</div>
                  {slots.length === 0 ? (
                    <div className="text-sm text-slate-500">Loading slots…</div>
                  ) : (
                    <div className="grid sm:grid-cols-2 gap-2">
                      {slots.map((s, i) => {
                        const active = selectedSlot?.scheduled_for === s.scheduled_for && selectedSlot?.doctor?.id === s.doctor.id;
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => setSelectedSlot(s)}
                            data-testid={`slot-option-${i}`}
                            className={[
                              "rounded-xl border p-3 text-left text-sm transition-all",
                              active ? "border-teal-600 bg-teal-50/40 ring-2 ring-teal-100" : "border-slate-200 hover:border-slate-300",
                            ].join(" ")}
                          >
                            <div className="font-medium text-slate-800">{fmtSlot(s.scheduled_for)}</div>
                            <div className="text-xs text-slate-500 mt-0.5">{s.doctor.full_name} · {s.doctor.specialty}</div>
                            <div className="text-xs text-slate-500">₦{(s.doctor.consultation_fee || 5000).toLocaleString()}</div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="mt-6 flex flex-wrap gap-3">
              <button onClick={() => setStep(1)} className="btn-ghost-pill" data-testid="triage-back-button">Back</button>
              <button
                onClick={submitCase}
                disabled={loading || !path || (path === "scheduled" && !selectedSlot)}
                className="btn-primary disabled:opacity-60"
                data-testid="triage-continue-button"
              >
                {loading ? "Submitting…" : <>Continue to payment <ArrowRight className="size-4" /></>}
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="card-elevated space-y-5" data-testid="payment-step">
          <div>
            <div className="overline mb-2">Step 3</div>
            <h2 className="font-display text-2xl">Consultation fee</h2>
            <p className="text-sm text-slate-500 mt-1">{path === "scheduled" ? "Confirm your appointment by paying the doctor's fee." : "A flat fee secures a verified doctor for your case."}</p>
          </div>
          {path === "scheduled" && selectedSlot && (
            <div className="rounded-xl border border-teal-100 bg-teal-50/40 p-4 text-sm" data-testid="appointment-summary">
              <div className="flex items-center gap-2 text-teal-800 font-medium mb-1">
                {mode === "video" ? <Video className="size-4" /> : <Phone className="size-4" />}
                {mode === "video" ? "Video" : "Voice"} appointment
              </div>
              <div className="text-slate-800">{fmtSlot(selectedSlot.scheduled_for)} · {selectedSlot.doctor.full_name}</div>
              <div className="text-xs text-slate-500">{selectedSlot.doctor.specialty}</div>
            </div>
          )}
          <div className="rounded-xl border border-slate-200 p-5 flex items-center justify-between">
            <div>
              <div className="text-xs text-slate-500 uppercase tracking-widest">Amount</div>
              <div className="font-display text-3xl">₦{((path === "scheduled" ? selectedSlot?.doctor?.consultation_fee : 5000) || 5000).toLocaleString()}</div>
              <div className="text-xs text-slate-500 mt-1">Doctor receives 70% · DocNow.NG 30%</div>
            </div>
            <div className="text-right text-xs text-slate-500">
              <div>Reference</div>
              <div className="font-mono text-slate-800">{paymentRef}</div>
            </div>
          </div>
          {payLive && authUrl ? (
            <>
              <div className="rounded-xl bg-teal-50 border border-teal-100 text-teal-900 text-xs p-3">
                You'll be redirected to Paystack's secure checkout to complete payment. Your card details never touch DocNow.NG.
              </div>
              <button onClick={payWithPaystack} disabled={loading} data-testid="pay-with-paystack-button" className="btn-primary disabled:opacity-60">
                Pay ₦{((path === "scheduled" ? selectedSlot?.doctor?.consultation_fee : 5000) || 5000).toLocaleString()} with Paystack
              </button>
            </>
          ) : (
            <>
              <div className="rounded-xl bg-amber-50 border border-amber-100 text-amber-900 text-xs p-3">
                Test mode — Paystack keys aren't configured, so this confirms the payment without a live charge.
              </div>
              <button onClick={confirmPayment} disabled={loading} data-testid="confirm-payment-button" className="btn-primary disabled:opacity-60">
                {loading ? "Verifying…" : "Confirm payment"}
              </button>
            </>
          )}
        </div>
      )}

      {step === 4 && (
        <div className="card-elevated text-center space-y-4" data-testid="case-submitted-success">
          <div className="size-16 mx-auto rounded-full bg-teal-50 grid place-items-center text-teal-700">
            {path === "scheduled" ? <CalendarClock className="size-7" /> : <Stethoscope className="size-7" />}
          </div>
          <h2 className="font-display text-2xl">
            {path === "scheduled" ? "Appointment confirmed" : "You're in the queue"}
          </h2>
          <p className="text-sm text-slate-600 max-w-md mx-auto">
            {path === "scheduled"
              ? `Your ${mode} appointment with ${selectedSlot?.doctor?.full_name} on ${fmtSlot(selectedSlot?.scheduled_for)} is confirmed. We'll notify you when the doctor opens the room.`
              : "A verified doctor will pick up your case shortly. You'll be able to chat in the consultation room."}
          </p>
          <button onClick={() => onDone(path === "scheduled" ? "appointments" : "history")} className="btn-primary" data-testid="goto-history-button">
            {path === "scheduled" ? "View my appointments" : "Go to consultation history"}
          </button>
        </div>
      )}
    </div>
  );
}

// ============= APPOINTMENTS =============
function AppointmentsView() {
  const [items, setItems] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    const { data } = await api.get("/appointments/mine");
    setItems(data);
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);

  const cancel = async (id) => {
    if (!window.confirm("Cancel this appointment?")) return;
    try {
      await api.post(`/appointments/${id}/cancel`);
      toast.success("Appointment cancelled");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const upcoming = (items || []).filter((a) => ["scheduled", "in_progress"].includes(a.status));
  const past = (items || []).filter((a) => ["completed", "cancelled"].includes(a.status));

  const fmt = (iso) => new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="space-y-6 fade-up" data-testid="appointments-view">
      <h2 className="font-display text-2xl">Appointments</h2>

      <div>
        <div className="overline mb-2">Upcoming</div>
        {items === null ? (
          <div className="card-soft text-sm text-slate-500 text-center py-8">Loading appointments…</div>
        ) : upcoming.length === 0 ? <EmptyState text="No upcoming appointments." /> : (
          <div className="grid gap-3">
            {upcoming.map((a) => (
              <div key={a.id} className="card-soft flex items-center justify-between gap-4 flex-wrap" data-testid={`appointment-row-${a.id}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    {a.mode === "video" ? <Video className="size-4 text-teal-700" /> : <Phone className="size-4 text-teal-700" />}
                    <span className="font-medium text-slate-800">{a.doctor_name}</span>
                    <span className="text-xs text-slate-500">· {a.specialty}</span>
                  </div>
                  <div className="text-sm text-slate-800">{fmt(a.scheduled_for)}</div>
                  <div className="text-xs text-slate-500 mt-0.5 capitalize">Status: {a.status.replace("_", " ")}</div>
                </div>
                <div className="flex items-center gap-2">
                  {a.status === "in_progress" && a.consultation_id && (
                    <button onClick={() => navigate(`/consultation/${a.consultation_id}`)} className="btn-primary" data-testid={`join-consult-${a.id}`}>
                      Join now <ArrowRight className="size-4" />
                    </button>
                  )}
                  {a.status === "scheduled" && (
                    <button onClick={() => cancel(a.id)} className="btn-ghost-pill" data-testid={`cancel-appt-${a.id}`}>Cancel</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {past.length > 0 && (
        <div>
          <div className="overline mb-2">Past</div>
          <div className="grid gap-3">
            {past.map((a) => (
              <div key={a.id} className="card-soft flex items-center justify-between gap-3 opacity-75" data-testid={`past-appointment-${a.id}`}>
                <div>
                  <div className="text-sm text-slate-800">{a.doctor_name} · <span className="capitalize">{a.mode}</span></div>
                  <div className="text-xs text-slate-500">{fmt(a.scheduled_for)} · <span className="capitalize">{a.status}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============= HISTORY =============
function HistoryView() {
  const [cases, setCases] = useState([]);
  const [consultations, setConsultations] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      const [c, h] = await Promise.all([api.get("/cases/mine"), api.get("/consultations/mine/history")]);
      setCases(c.data); setConsultations(h.data);
    })();
  }, []);

  return (
    <div className="space-y-6 fade-up" data-testid="history-view">
      <h2 className="font-display text-2xl">Consultation history</h2>
      {cases.length === 0 ? <EmptyState text="No cases yet." /> : (
        <div className="grid gap-3">
          {cases.map((c) => {
            const consult = consultations.find((cn) => cn.case_id === c.id);
            return (
              <div key={c.id} className="card-soft flex items-center justify-between gap-4 flex-wrap" data-testid={`case-row-${c.id}`}>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-800 line-clamp-1">{c.symptoms}</div>
                  <div className="text-xs text-slate-500 mt-1">{new Date(c.created_at).toLocaleString()} · {c.status.replace("_", " ")}</div>
                </div>
                <UrgencyBadge level={c.urgency} />
                {consult && (
                  <button onClick={() => navigate(`/consultation/${consult.id}`)} className="btn-ghost-pill" data-testid={`open-consultation-${consult.id}`}>
                    Open <ArrowRight className="size-4" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============= CARE PLANS =============
function CarePlansView() {
  const [plans, setPlans] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showFeedbackFor, setShowFeedbackFor] = useState(null);

  useEffect(() => { (async () => { const { data } = await api.get("/care-plans/mine"); setPlans(data); })(); }, []);

  return (
    <div className="space-y-6 fade-up" data-testid="care-plans-view">
      <h2 className="font-display text-2xl">Care plans</h2>
      {plans.length === 0 ? <EmptyState text="No care plans yet — complete a consultation to get one." /> : (
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="space-y-3">
            {plans.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelected(p)}
                data-testid={`care-plan-row-${p.id}`}
                className={[
                  "card-soft text-left w-full",
                  selected?.id === p.id ? "ring-2 ring-teal-200" : ""
                ].join(" ")}
              >
                <div className="text-xs text-slate-500">{new Date(p.created_at).toLocaleDateString()}</div>
                <div className="font-medium text-slate-800 mt-1 line-clamp-2">{p.consultation_summary}</div>
                <div className="text-xs text-slate-500 mt-1">By {p.doctor_name}</div>
              </button>
            ))}
          </div>
          <div className="lg:col-span-2">
            {selected ? (
              <div className="card-elevated space-y-5" data-testid="care-plan-detail">
                <div>
                  <div className="overline mb-1">Care Plan</div>
                  <h3 className="font-display text-2xl">Consultation Summary</h3>
                  <p className="text-sm text-slate-700 mt-2 leading-relaxed">{selected.consultation_summary}</p>
                </div>
                <Section title="Doctor advice" body={selected.doctor_advice} />
                <ListSection title="Warning signs" items={selected.warning_signs} tone="red" />
                <ListSection title="Recommended tests" items={selected.recommended_tests} tone="blue" />
                <Section title="Follow-up instructions" body={selected.follow_up} />
                <ListSection title="Health tips" items={selected.health_tips} tone="teal" />
                <button
                  onClick={() => setShowFeedbackFor(selected.consultation_id)}
                  className="btn-ghost-pill"
                  data-testid="open-feedback-button"
                >
                  <Star className="size-4" /> Rate consultation
                </button>
                {showFeedbackFor && (
                  <FeedbackForm consultationId={showFeedbackFor} onDone={() => setShowFeedbackFor(null)} />
                )}
              </div>
            ) : (
              <div className="card-soft text-slate-500 text-sm">Select a care plan to view details.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, body }) {
  return body ? (
    <div>
      <div className="overline mb-1">{title}</div>
      <p className="text-sm text-slate-700 leading-relaxed">{body}</p>
    </div>
  ) : null;
}

function ListSection({ title, items, tone }) {
  if (!items || items.length === 0) return null;
  const tones = {
    red: "bg-red-50/60 border-red-100 text-red-900",
    blue: "bg-blue-50/50 border-blue-100 text-blue-900",
    teal: "bg-teal-50/50 border-teal-100 text-teal-900",
  };
  return (
    <div className={`rounded-xl border p-4 ${tones[tone] || "bg-slate-50"}`}>
      <div className="font-medium text-sm mb-2">{title}</div>
      <ul className="text-sm space-y-1 list-disc list-inside">
        {items.map((it, i) => (<li key={i}>{it}</li>))}
      </ul>
    </div>
  );
}

function FeedbackForm({ consultationId, onDone }) {
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      await api.post("/feedback", { consultation_id: consultationId, rating, comment });
      toast.success("Feedback submitted");
      onDone();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="rounded-xl border border-slate-200 p-4 space-y-3" data-testid="feedback-form">
      <div className="font-medium text-sm">Rate this consultation</div>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((s) => (
          <button
            key={s}
            onClick={() => setRating(s)}
            data-testid={`rating-star-${s}`}
            className={s <= rating ? "text-amber-500" : "text-slate-300"}
            aria-label={`Rate ${s} stars`}
          >
            <Star className="size-6 fill-current" />
          </button>
        ))}
      </div>
      <textarea
        data-testid="feedback-comment"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        rows={3}
        placeholder="Optional comment"
        className="w-full rounded-xl border border-slate-200 px-3 py-2 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
      />
      <button onClick={submit} disabled={loading} className="btn-primary" data-testid="submit-feedback-button">
        {loading ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}

// ============= PRESCRIPTIONS =============
function PrescriptionsView() {
  const [items, setItems] = useState([]);
  useEffect(() => { (async () => { const { data } = await api.get("/prescriptions/mine"); setItems(data); })(); }, []);

  return (
    <div className="space-y-6 fade-up" data-testid="prescriptions-view">
      <h2 className="font-display text-2xl">Prescriptions</h2>
      {items.length === 0 ? <EmptyState text="No prescriptions yet." /> : (
        <div className="grid lg:grid-cols-2 gap-5">
          {items.map((p) => (
            <div key={p.id} className="card-soft" data-testid={`prescription-card-${p.id}`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="overline mb-1">Prescription</div>
                  <div className="font-mono text-sm text-slate-800">{p.code}</div>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>{new Date(p.created_at).toLocaleDateString()}</div>
                  <div>{p.doctor_name}</div>
                </div>
              </div>
              <ul className="mt-4 divide-y divide-slate-100">
                {p.items.map((it, i) => (
                  <li key={i} className="py-2.5">
                    <div className="font-medium text-slate-900">{it.medication}</div>
                    <div className="text-xs text-slate-500">{it.dosage} · {it.frequency} · {it.duration}</div>
                    {it.instructions && <div className="text-xs text-slate-600 mt-1">{it.instructions}</div>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============= VITALS =============
const VITAL_TYPES = [
  { key: "bp_systolic", label: "Blood pressure (systolic)", unit: "mmHg", color: "#0D9488" },
  { key: "bp_diastolic", label: "Blood pressure (diastolic)", unit: "mmHg", color: "#1E3A8A" },
  { key: "heart_rate", label: "Heart rate", unit: "bpm", color: "#0D9488" },
  { key: "weight", label: "Weight", unit: "kg", color: "#1E3A8A" },
  { key: "blood_sugar", label: "Blood sugar", unit: "mg/dL", color: "#0D9488" },
  { key: "temperature", label: "Temperature", unit: "°C", color: "#1E3A8A" },
];

function VitalsView() {
  const [items, setItems] = useState([]);
  const [type, setType] = useState("bp_systolic");
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const { data } = await api.get("/vitals/mine");
    setItems(data);
  };
  useEffect(() => { load(); }, []);

  const add = async (e) => {
    e.preventDefault();
    if (!value) return;
    const meta = VITAL_TYPES.find((v) => v.key === type);
    setLoading(true);
    try {
      await api.post("/vitals", { type, value: parseFloat(value), unit: meta.unit });
      setValue("");
      toast.success("Vital recorded");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setLoading(false); }
  };

  const remove = async (id) => {
    await api.delete(`/vitals/${id}`);
    load();
  };

  return (
    <div className="space-y-6 fade-up" data-testid="vitals-view">
      <h2 className="font-display text-2xl">Health vitals</h2>

      <form onSubmit={add} className="card-soft grid sm:grid-cols-12 gap-3 items-end">
        <div className="sm:col-span-5">
          <label className="text-sm font-medium text-slate-700">Type</label>
          <select data-testid="vital-type-select" value={type} onChange={(e) => setType(e.target.value)}
            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 bg-white">
            {VITAL_TYPES.map((v) => (<option key={v.key} value={v.key}>{v.label}</option>))}
          </select>
        </div>
        <div className="sm:col-span-4">
          <label className="text-sm font-medium text-slate-700">Value ({VITAL_TYPES.find((v) => v.key === type)?.unit})</label>
          <input data-testid="vital-value-input" type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} required
            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5"/>
        </div>
        <div className="sm:col-span-3">
          <button type="submit" disabled={loading} className="btn-primary w-full" data-testid="vital-add-button">Add reading</button>
        </div>
      </form>

      {VITAL_TYPES.map((t) => {
        const data = items
          .filter((i) => i.type === t.key)
          .slice()
          .reverse()
          .map((i) => ({ date: new Date(i.recorded_at).toLocaleDateString(), value: i.value }));
        if (data.length === 0) return null;
        return (
          <div key={t.key} className="card-soft">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="overline mb-1">{t.label}</div>
                <div className="text-xs text-slate-500">{data.length} readings · latest {data[data.length - 1].value} {t.unit}</div>
              </div>
            </div>
            <div className="h-56" data-testid={`vital-chart-${t.key}`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} />
                  <YAxis stroke="#94a3b8" fontSize={11} />
                  <Tooltip
                    contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", fontSize: 12 }}
                  />
                  <Line type="monotone" dataKey="value" stroke={t.color} strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        );
      })}

      <div className="card-soft">
        <div className="overline mb-3">All readings</div>
        {items.length === 0 ? <EmptyState text="No readings yet." /> : (
          <ul className="divide-y divide-slate-100">
            {items.map((i) => (
              <li key={i.id} className="py-2.5 flex items-center justify-between" data-testid={`vital-row-${i.id}`}>
                <div className="text-sm text-slate-800">
                  <span className="font-medium">{VITAL_TYPES.find((v) => v.key === i.type)?.label || i.type}</span>
                  <span className="ml-2 text-slate-500">{i.value} {i.unit}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500">{new Date(i.recorded_at).toLocaleString()}</span>
                  <button onClick={() => remove(i.id)} className="text-slate-400 hover:text-red-600" aria-label="Delete"
                    data-testid={`delete-vital-${i.id}`}>
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ============= TIPS =============
function TipsView() {
  const [tips, setTips] = useState([]);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/health-tips");
      setTips(data.tips);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6 fade-up" data-testid="tips-view">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-2xl">Today's health tips</h2>
        <button onClick={load} disabled={loading} className="btn-ghost-pill" data-testid="refresh-tips-button">
          {loading ? "Loading…" : <>Refresh <Sparkles className="size-4" /></>}
        </button>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {tips.map((t, i) => (
          <div key={i} className="card-soft" data-testid={`tip-card-${i}`}>
            <div className="overline mb-2">{t.category}</div>
            <div className="font-display text-lg mb-1">{t.title}</div>
            <p className="text-sm text-slate-600 leading-relaxed">{t.body}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-400 italic">These tips are general wellness suggestions and are not medical advice.</p>
    </div>
  );
}
