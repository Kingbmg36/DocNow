import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import DashboardShell from "@/components/DashboardShell";
import UrgencyBadge from "@/components/UrgencyBadge";
import QuestionnaireRunner from "@/components/QuestionnaireRunner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { toast } from "sonner";
import {
  LayoutDashboard, ListChecks, History, Pill, BadgeDollarSign, Star, ArrowRight, BriefcaseMedical,
  CalendarClock, Video, Phone, ClipboardEdit, RefreshCw,
} from "lucide-react";

const TABS = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "queue", label: "Queue", icon: ListChecks },
  { key: "appointments", label: "Appointments", icon: CalendarClock },
  { key: "assigned", label: "My Cases", icon: BriefcaseMedical },
  { key: "history", label: "History", icon: History },
  { key: "prescriptions", label: "Prescriptions", icon: Pill },
  { key: "earnings", label: "Earnings", icon: BadgeDollarSign },
  { key: "ratings", label: "Ratings", icon: Star },
];

export default function DoctorDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = useState("overview");
  const [qxItems, setQxItems] = useState(null);
  const [activeQx, setActiveQx] = useState(null); // code or null
  const [licenseMeta, setLicenseMeta] = useState(user?.license_document || null);
  const [uploadingLicense, setUploadingLicense] = useState(false);

  const uploadLicense = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingLicense(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/doctors/license", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setLicenseMeta(data.license_document);
      toast.success("License uploaded — our team will review it shortly");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Upload failed");
    } finally {
      setUploadingLicense(false);
      e.target.value = ""; // allow re-selecting the same file
    }
  };

  const loadQx = async () => {
    try {
      const { data } = await api.get("/questionnaires/mine");
      setQxItems(data.items || []);
      const onboarding = (data.items || []).find((i) => i.code === "doctor_onboarding");
      const refresh = (data.items || []).find((i) => i.code === "doctor_refresh");
      const dismissKey = `mdn_dx_onboarding_dismissed_${user?.id || ""}`;
      if (onboarding && !onboarding.completed && !localStorage.getItem(dismissKey)) {
        setActiveQx("doctor_onboarding");
      } else if (refresh && refresh.needs_refresh) {
        setActiveQx("doctor_refresh");
      }
    } catch (e) { console.error("[loadQx]", e); }
  };

  useEffect(() => { if (user?.status === "approved") loadQx(); /* eslint-disable-next-line */ }, [user?.status]);

  const onboarding = (qxItems || []).find((i) => i.code === "doctor_onboarding");
  const refresh = (qxItems || []).find((i) => i.code === "doctor_refresh");

  if (user?.status !== "approved") {
    return (
      <DashboardShell tabs={[{ key: "overview", label: "Overview", icon: LayoutDashboard }]} currentTab="overview" onTabChange={() => {}}>
        <div className="card-elevated max-w-xl mx-auto text-center space-y-3 fade-up" data-testid="doctor-pending-banner">
          <div className="size-16 mx-auto rounded-full bg-amber-50 grid place-items-center text-amber-600">
            <BriefcaseMedical className="size-7" />
          </div>
          <h2 className="font-display text-2xl">Your account is under review</h2>
          <p className="text-sm text-slate-600">DocNow.NG admins verify license details before doctors go live. You'll be notified once approved.</p>
          <div className="text-xs text-slate-500">Status: <span className="capitalize font-medium">{user?.status}</span></div>

          <div className="pt-2">
            {licenseMeta ? (
              <div className="rounded-xl border border-teal-100 bg-teal-50/50 p-3 text-sm text-teal-800" data-testid="license-uploaded">
                ✓ License uploaded: {licenseMeta.filename} · <span className="capitalize">{(licenseMeta.status || "pending_review").replace(/_/g, " ")}</span>
                <div className="mt-2">
                  <label className="text-xs underline cursor-pointer text-teal-700">
                    Replace file
                    <input type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={uploadLicense} disabled={uploadingLicense} />
                  </label>
                </div>
              </div>
            ) : (
              <label className="btn-primary inline-flex cursor-pointer" data-testid="upload-license-button">
                {uploadingLicense ? "Uploading…" : "Upload license document"}
                <input type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={uploadLicense} disabled={uploadingLicense} />
              </label>
            )}
            <p className="text-xs text-slate-400 mt-2">PDF, JPG or PNG · up to 10 MB — speeds up verification.</p>
          </div>
        </div>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell tabs={TABS} currentTab={tab} onTabChange={setTab}>
      {tab === "overview" && (
        <>
          {onboarding && !onboarding.completed && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 flex items-center justify-between gap-4 flex-wrap mb-6" data-testid="doctor-onboarding-banner">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <div className="size-10 rounded-xl bg-white text-amber-700 grid place-items-center shrink-0">
                  <ClipboardEdit className="size-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs uppercase tracking-widest text-amber-800 font-bold">Complete your onboarding</div>
                  <div className="font-display text-lg leading-tight mt-0.5">Required before you can accept consultations</div>
                  <p className="text-xs text-slate-700 mt-1 max-w-xl">
                    MDCN number, specialty, availability and telemedicine attestations. Takes about 3 minutes.
                  </p>
                </div>
              </div>
              <button onClick={() => setActiveQx("doctor_onboarding")} className="btn-primary shrink-0" data-testid="doctor-onboarding-cta">
                Complete now <ArrowRight className="size-4" />
              </button>
            </div>
          )}
          {refresh && refresh.needs_refresh && (
            <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5 flex items-center justify-between gap-4 flex-wrap mb-6" data-testid="doctor-refresh-banner">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <div className="size-10 rounded-xl bg-white text-blue-700 grid place-items-center shrink-0">
                  <RefreshCw className="size-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs uppercase tracking-widest text-blue-800 font-bold">Profile refresh due</div>
                  <div className="font-display text-lg leading-tight mt-0.5">Keep your practice details current</div>
                  <p className="text-xs text-slate-700 mt-1">90 seconds — confirm fee, availability, and any new certifications.</p>
                </div>
              </div>
              <button onClick={() => setActiveQx("doctor_refresh")} className="btn-primary shrink-0" data-testid="doctor-refresh-cta">
                Refresh now <ArrowRight className="size-4" />
              </button>
            </div>
          )}
          <DoctorOverview setTab={setTab} />
        </>
      )}
      {tab === "queue" && <Queue />}
      {tab === "appointments" && <DoctorAppointments />}
      {tab === "assigned" && <Assigned />}
      {tab === "history" && <DoctorHistory />}
      {tab === "prescriptions" && <DoctorPrescriptions />}
      {tab === "earnings" && <Earnings />}
      {tab === "ratings" && <Ratings />}
      {activeQx && (
        <QuestionnaireRunner
          code={activeQx}
          onClose={() => {
            if (activeQx === "doctor_onboarding") {
              localStorage.setItem(`mdn_dx_onboarding_dismissed_${user?.id || ""}`, "1");
            }
            setActiveQx(null);
          }}
          onSubmitted={async () => {
            setActiveQx(null);
            await loadQx();
            toast.success("Saved");
          }}
        />
      )}
    </DashboardShell>
  );
}

function DoctorOverview({ setTab }) {
  const { user } = useAuth();
  const [queue, setQueue] = useState([]);
  const [assigned, setAssigned] = useState([]);
  useEffect(() => {
    (async () => {
      const [q, a] = await Promise.all([api.get("/cases/queue"), api.get("/cases/assigned")]);
      setQueue(q.data); setAssigned(a.data);
    })();
  }, []);
  return (
    <div className="space-y-6 fade-up" data-testid="doctor-overview">
      <div className="grid md:grid-cols-3 gap-6">
        <StatCard label="Queued cases" value={queue.length} icon={ListChecks} onClick={() => setTab("queue")} />
        <StatCard label="Active consultations" value={assigned.length} icon={BriefcaseMedical} onClick={() => setTab("assigned")} />
        <StatCard label="Total earnings" value={`₦${(user?.earnings_total || 0).toLocaleString()}`} icon={BadgeDollarSign} />
      </div>
      <div className="card-soft">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-xl">Most urgent in queue</h3>
          <button onClick={() => setTab("queue")} className="btn-ghost-pill" data-testid="overview-open-queue">Open queue</button>
        </div>
        {queue.length === 0 ? <div className="text-sm text-slate-500 py-6 text-center">No cases waiting.</div> : (
          <ul className="divide-y divide-slate-100">
            {queue.slice(0, 5).map((c) => (
              <li key={c.id} className="py-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm text-slate-800 line-clamp-1">{c.symptoms}</div>
                  <div className="text-xs text-slate-500">{c.patient_name} · {new Date(c.created_at).toLocaleString()}</div>
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

function StatCard({ label, value, icon: Icon, onClick }) {
  return (
    <button onClick={onClick} disabled={!onClick} className="card-soft text-left w-full disabled:cursor-default">
      <div className="size-10 rounded-xl bg-teal-50 text-teal-700 grid place-items-center mb-3">
        <Icon className="size-5" strokeWidth={1.6} />
      </div>
      <div className="text-xs uppercase tracking-widest text-slate-500">{label}</div>
      <div className="font-display text-3xl mt-1">{value}</div>
    </button>
  );
}

function Queue() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const load = async () => { const { data } = await api.get("/cases/queue"); setItems(data); };
  useEffect(() => { load(); }, []);

  const accept = async (caseId) => {
    setLoading(true);
    try {
      const { data } = await api.post(`/consultations/accept/${caseId}`);
      toast.success("Case accepted");
      navigate(`/consultation/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-4 fade-up" data-testid="doctor-queue">
      <h2 className="font-display text-2xl">Patient queue</h2>
      {items.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-10">No cases in the queue right now.</div> : (
        <div className="grid gap-3">
          {items.map((c) => (
            <div key={c.id} className="card-soft flex items-start justify-between gap-4 flex-wrap" data-testid={`queue-row-${c.id}`}>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3 flex-wrap mb-1">
                  <span className="font-medium text-slate-800">{c.patient_name || "Patient"}</span>
                  <UrgencyBadge level={c.urgency} />
                </div>
                <div className="text-sm text-slate-700">{c.symptoms}</div>
                <div className="text-xs text-slate-500 mt-1">
                  Duration: {c.duration} · Severity: {c.severity} · {new Date(c.created_at).toLocaleString()}
                </div>
                {c.triage?.recommended_specialty && (
                  <div className="text-xs text-teal-700 mt-1">AI suggests: {c.triage.recommended_specialty}</div>
                )}
              </div>
              <button
                onClick={() => accept(c.id)}
                disabled={loading}
                className="btn-primary disabled:opacity-60"
                data-testid={`accept-case-${c.id}`}
              >
                Accept <ArrowRight className="size-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Assigned() {
  const [items, setItems] = useState([]);
  const navigate = useNavigate();
  useEffect(() => { (async () => { const { data } = await api.get("/cases/assigned"); setItems(data); })(); }, []);
  return (
    <div className="space-y-4 fade-up" data-testid="doctor-assigned">
      <h2 className="font-display text-2xl">My active cases</h2>
      {items.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-10">No active cases.</div> : (
        <div className="grid gap-3">
          {items.map((c) => (
            <button key={c.id} onClick={() => navigate(`/consultation/${c.consultation_id}`)}
              className="card-soft flex items-center justify-between gap-4 text-left w-full"
              data-testid={`assigned-row-${c.id}`}>
              <div>
                <div className="font-medium text-slate-800">{c.patient_name}</div>
                <div className="text-sm text-slate-700 line-clamp-1">{c.symptoms}</div>
                <div className="text-xs text-slate-500 mt-1">{new Date(c.created_at).toLocaleString()}</div>
              </div>
              <UrgencyBadge level={c.urgency} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function DoctorHistory() {
  const [items, setItems] = useState([]);
  const navigate = useNavigate();
  useEffect(() => { (async () => { const { data } = await api.get("/consultations/mine/history"); setItems(data); })(); }, []);
  return (
    <div className="space-y-4 fade-up" data-testid="doctor-history">
      <h2 className="font-display text-2xl">Consultation history</h2>
      {items.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-10">No consultations yet.</div> : (
        <div className="grid gap-3">
          {items.map((c) => (
            <button key={c.id} onClick={() => navigate(`/consultation/${c.id}`)} className="card-soft text-left w-full flex items-center justify-between">
              <div>
                <div className="font-medium text-slate-800">{c.patient_name}</div>
                <div className="text-xs text-slate-500">{new Date(c.created_at).toLocaleString()} · {c.status}</div>
              </div>
              <ArrowRight className="size-4 text-slate-400" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function DoctorAppointments() {
  const [items, setItems] = useState([]);
  const navigate = useNavigate();
  const load = async () => { const { data } = await api.get("/appointments/mine"); setItems(data); };
  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);

  const start = async (appt) => {
    try {
      const { data } = await api.post(`/appointments/${appt.id}/start`);
      toast.success("Consultation room opened");
      navigate(`/consultation/${data.consultation_id}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const fmt = (iso) => new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const upcoming = items.filter((a) => ["scheduled", "in_progress"].includes(a.status));
  const past = items.filter((a) => ["completed", "cancelled"].includes(a.status));

  return (
    <div className="space-y-6 fade-up" data-testid="doctor-appointments">
      <h2 className="font-display text-2xl">Scheduled appointments</h2>
      <div>
        <div className="overline mb-2">Upcoming</div>
        {upcoming.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-8">No scheduled appointments.</div> : (
          <div className="grid gap-3">
            {upcoming.map((a) => (
              <div key={a.id} className="card-soft flex items-center justify-between gap-4 flex-wrap" data-testid={`doctor-appt-row-${a.id}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    {a.mode === "video" ? <Video className="size-4 text-teal-700" /> : <Phone className="size-4 text-teal-700" />}
                    <span className="font-medium text-slate-800">{a.patient_name}</span>
                  </div>
                  <div className="text-sm text-slate-800">{fmt(a.scheduled_for)}</div>
                  <div className="text-xs text-slate-500 capitalize">Status: {a.status.replace("_", " ")}</div>
                </div>
                <button onClick={() => start(a)} className="btn-primary" data-testid={`start-appt-${a.id}`}>
                  {a.status === "in_progress" ? "Re-enter room" : "Start consultation"} <ArrowRight className="size-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      {past.length > 0 && (
        <div>
          <div className="overline mb-2">Past</div>
          <div className="grid gap-3">
            {past.slice(0, 10).map((a) => (
              <div key={a.id} className="card-soft opacity-75 text-sm">
                {a.patient_name} · <span className="capitalize">{a.mode}</span> · {fmt(a.scheduled_for)} · <span className="capitalize">{a.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function DoctorPrescriptions() {
  const [items, setItems] = useState([]);
  useEffect(() => { (async () => { const { data } = await api.get("/prescriptions/mine"); setItems(data); })(); }, []);
  return (
    <div className="space-y-4 fade-up" data-testid="doctor-prescriptions">
      <h2 className="font-display text-2xl">Prescriptions issued</h2>
      {items.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-10">No prescriptions issued yet.</div> : (
        <div className="grid lg:grid-cols-2 gap-5">
          {items.map((p) => (
            <div key={p.id} className="card-soft">
              <div className="flex items-center justify-between">
                <div>
                  <div className="overline mb-1">Code</div>
                  <div className="font-mono text-sm">{p.code}</div>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>{new Date(p.created_at).toLocaleDateString()}</div>
                  <div>For {p.patient_name}</div>
                </div>
              </div>
              <ul className="mt-3 text-sm text-slate-700">
                {p.items.map((it, i) => (
                  <li key={i} className="py-1.5 border-b border-slate-100 last:border-0">
                    <span className="font-medium">{it.medication}</span>
                    <span className="text-slate-500 text-xs ml-2">{it.dosage} · {it.frequency} · {it.duration}</span>
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

function Earnings() {
  const { user } = useAuth();
  const [history, setHistory] = useState([]);
  useEffect(() => { (async () => { const { data } = await api.get("/consultations/mine/history"); setHistory(data); })(); }, []);
  const completed = history.filter((h) => h.status === "completed").length;
  return (
    <div className="space-y-6 fade-up" data-testid="doctor-earnings">
      <h2 className="font-display text-2xl">Earnings</h2>
      <div className="grid md:grid-cols-3 gap-6">
        <StatCard label="Total earned" value={`₦${(user?.earnings_total || 0).toLocaleString()}`} icon={BadgeDollarSign} />
        <StatCard label="Completed consults" value={completed} icon={History} />
        <StatCard label="Avg. fee" value={`₦${(user?.consultation_fee || 0).toLocaleString()}`} icon={Pill} />
      </div>
      <div className="card-soft text-sm text-slate-600">
        DocNow.NG takes a 30% platform fee. You receive 70% of every successfully completed consultation.
      </div>
    </div>
  );
}

function Ratings() {
  const [items, setItems] = useState([]);
  const { user } = useAuth();
  useEffect(() => { (async () => { const { data } = await api.get("/feedback/doctor/me"); setItems(data); })(); }, []);
  return (
    <div className="space-y-6 fade-up" data-testid="doctor-ratings">
      <h2 className="font-display text-2xl">Patient feedback</h2>
      <div className="card-soft flex items-center gap-6">
        <div>
          <div className="text-xs uppercase tracking-widest text-slate-500">Average rating</div>
          <div className="font-display text-5xl">{user?.rating_avg?.toFixed(1) || "—"}</div>
        </div>
        <div className="text-sm text-slate-500">{user?.rating_count || 0} reviews</div>
      </div>
      {items.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-8">No reviews yet.</div> : (
        <div className="grid gap-3">
          {items.map((f) => (
            <div key={f.id} className="card-soft" data-testid={`review-row-${f.id}`}>
              <div className="flex items-center gap-1 text-amber-500">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star key={i} className={i < f.rating ? "size-4 fill-current" : "size-4 text-slate-300"} />
                ))}
                <span className="ml-2 text-xs text-slate-500">by {f.patient_name}</span>
              </div>
              {f.comment && <p className="text-sm text-slate-700 mt-2">{f.comment}</p>}
              <div className="text-xs text-slate-400 mt-1">{new Date(f.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
