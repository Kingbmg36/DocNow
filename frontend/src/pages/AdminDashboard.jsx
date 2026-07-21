import { useEffect, useState } from "react";
import DashboardShell from "@/components/DashboardShell";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import {
  LayoutDashboard, Users, ShieldCheck, ClipboardList, Wallet, BarChart3, MessageSquareWarning, Star,
  MessageCircle, Send, CheckCircle2,
} from "lucide-react";

const TABS = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "users", label: "Users", icon: Users },
  { key: "approvals", label: "Doctor Approvals", icon: ShieldCheck },
  { key: "consultations", label: "Consultations", icon: ClipboardList },
  { key: "payments", label: "Payments", icon: Wallet },
  { key: "analytics", label: "Analytics", icon: BarChart3 },
  { key: "feedback", label: "Feedback", icon: MessageSquareWarning },
  { key: "whatsapp", label: "WhatsApp", icon: MessageCircle },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState("overview");
  return (
    <DashboardShell tabs={TABS} currentTab={tab} onTabChange={setTab}>
      {tab === "overview" && <Overview />}
      {tab === "users" && <UsersView />}
      {tab === "approvals" && <Approvals />}
      {tab === "consultations" && <ConsultationsView />}
      {tab === "payments" && <PaymentsView />}
      {tab === "analytics" && <Analytics />}
      {tab === "feedback" && <FeedbackView />}
      {tab === "whatsapp" && <WhatsAppView />}
    </DashboardShell>
  );
}

function Overview() {
  const [a, setA] = useState(null);
  useEffect(() => { (async () => { const { data } = await api.get("/admin/analytics"); setA(data); })(); }, []);
  if (!a) return <div className="text-slate-500">Loading…</div>;
  return (
    <div className="space-y-6 fade-up" data-testid="admin-overview">
      <h2 className="font-display text-2xl">Platform health</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
        <Tile label="Patients" value={a.patients} />
        <Tile label="Doctors" value={`${a.approved_doctors}/${a.doctors}`} sub="approved/total" />
        <Tile label="Cases queued" value={a.queued_cases} />
        <Tile label="Completed" value={a.completed_cases} />
        <Tile label="Pending doctors" value={a.pending_doctors} tone="amber" />
        <Tile label="Total revenue" value={`₦${a.total_revenue.toLocaleString()}`} />
        <Tile label="Platform share" value={`₦${a.platform_revenue.toLocaleString()}`} />
        <Tile label="Total cases" value={a.total_cases} />
      </div>
    </div>
  );
}

function Tile({ label, value, sub, tone }) {
  const toneCls = tone === "amber" ? "border-amber-200 bg-amber-50/40" : "border-slate-100";
  return (
    <div className={`card-soft border ${toneCls}`}>
      <div className="text-xs uppercase tracking-widest text-slate-500">{label}</div>
      <div className="font-display text-3xl mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

function UsersView() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("");
  useEffect(() => { (async () => { const { data } = await api.get(filter ? `/admin/users?role=${filter}` : "/admin/users"); setItems(data); })(); }, [filter]);
  return (
    <div className="space-y-4 fade-up" data-testid="admin-users">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-2xl">Users</h2>
        <select data-testid="users-role-filter" value={filter} onChange={(e) => setFilter(e.target.value)}
          className="rounded-xl border border-slate-200 px-3 py-2 bg-white text-sm">
          <option value="">All roles</option>
          <option value="patient">Patients</option>
          <option value="doctor">Doctors</option>
          <option value="admin">Admins</option>
        </select>
      </div>
      <div className="card-soft p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/60 text-slate-500 text-xs uppercase tracking-widest">
            <tr><th className="text-left p-3">Name</th><th className="text-left p-3">Email</th><th className="text-left p-3">Role</th><th className="text-left p-3">Status</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((u) => (
              <tr key={u.id} data-testid={`user-row-${u.id}`}>
                <td className="p-3">{u.full_name}</td>
                <td className="p-3 text-slate-500">{u.email}</td>
                <td className="p-3 capitalize">{u.role}</td>
                <td className="p-3"><StatusPill status={u.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const colors = {
    approved: "bg-green-50 text-green-700 border-green-200",
    pending: "bg-amber-50 text-amber-700 border-amber-200",
    suspended: "bg-red-50 text-red-700 border-red-200",
    rejected: "bg-slate-50 text-slate-600 border-slate-200",
  };
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${colors[status] || "bg-slate-50 text-slate-600 border-slate-200"}`}>{status}</span>;
}

function Approvals() {
  const [items, setItems] = useState([]);
  const load = async () => { const { data } = await api.get("/admin/doctors/pending"); setItems(data); };
  useEffect(() => { load(); }, []);
  const decide = async (id, action) => {
    try {
      await api.post(`/admin/doctors/${id}/decision`, { action });
      toast.success(`Doctor ${action}d`);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const viewLicense = async (id) => {
    try {
      const { data } = await api.get(`/doctors/${id}/license/file`, { responseType: "blob" });
      window.open(URL.createObjectURL(data), "_blank");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Could not open license"); }
  };
  return (
    <div className="space-y-4 fade-up" data-testid="admin-approvals">
      <h2 className="font-display text-2xl">Pending doctor approvals</h2>
      {items.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-8">No pending doctors.</div> : (
        <div className="grid gap-3">
          {items.map((d) => (
            <div key={d.id} className="card-soft flex items-start justify-between gap-4 flex-wrap" data-testid={`pending-doctor-${d.id}`}>
              <div>
                <div className="font-medium">{d.full_name}</div>
                <div className="text-xs text-slate-500">{d.email} · {d.phone}</div>
                <div className="text-sm mt-1">{d.specialty} · License {d.license_number} · {d.years_experience} yrs</div>
                {d.license_document ? (
                  <button onClick={() => viewLicense(d.id)} className="text-xs text-teal-700 underline mt-1" data-testid={`view-license-${d.id}`}>
                    📄 View license document · <span className="capitalize">{(d.license_document.status || "pending_review").replace(/_/g, " ")}</span>
                  </button>
                ) : (
                  <div className="text-xs text-amber-600 mt-1">⚠ No license document uploaded yet</div>
                )}
                {d.bio && <p className="text-sm text-slate-600 mt-1 max-w-prose">{d.bio}</p>}
              </div>
              <div className="flex gap-2">
                <button onClick={() => decide(d.id, "approve")} className="btn-primary" data-testid={`approve-doctor-${d.id}`}>Approve</button>
                <button onClick={() => decide(d.id, "reject")} className="btn-ghost-pill" data-testid={`reject-doctor-${d.id}`}>Reject</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConsultationsView() {
  const [items, setItems] = useState([]);
  useEffect(() => { (async () => { const { data } = await api.get("/admin/consultations"); setItems(data); })(); }, []);
  return (
    <div className="space-y-4 fade-up" data-testid="admin-consultations">
      <h2 className="font-display text-2xl">All consultations</h2>
      <div className="card-soft p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/60 text-slate-500 text-xs uppercase tracking-widest">
            <tr><th className="text-left p-3">Patient</th><th className="text-left p-3">Doctor</th><th className="text-left p-3">Status</th><th className="text-left p-3">Started</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((c) => (
              <tr key={c.id}>
                <td className="p-3">{c.patient_name}</td>
                <td className="p-3">{c.doctor_name}</td>
                <td className="p-3 capitalize">{c.status.replace("_", " ")}</td>
                <td className="p-3 text-slate-500">{new Date(c.started_at || c.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PaymentsView() {
  const [items, setItems] = useState([]);
  useEffect(() => { (async () => { const { data } = await api.get("/admin/payments"); setItems(data); })(); }, []);
  return (
    <div className="space-y-4 fade-up" data-testid="admin-payments">
      <h2 className="font-display text-2xl">Payments</h2>
      <div className="card-soft p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/60 text-slate-500 text-xs uppercase tracking-widest">
            <tr><th className="text-left p-3">Reference</th><th className="text-left p-3">Amount</th><th className="text-left p-3">Status</th><th className="text-left p-3">Doctor share</th><th className="text-left p-3">Date</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((p) => (
              <tr key={p.id}>
                <td className="p-3 font-mono text-xs">{p.reference}</td>
                <td className="p-3">₦{p.amount.toLocaleString()} {p.currency}</td>
                <td className="p-3"><StatusPill status={p.status} /></td>
                <td className="p-3">₦{p.doctor_share?.toLocaleString()}</td>
                <td className="p-3 text-slate-500">{new Date(p.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Analytics() {
  const [a, setA] = useState(null);
  useEffect(() => { (async () => { const { data } = await api.get("/admin/analytics"); setA(data); })(); }, []);
  if (!a) return null;
  return (
    <div className="space-y-6 fade-up" data-testid="admin-analytics">
      <h2 className="font-display text-2xl">Analytics</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
        {Object.entries(a).map(([k, v]) => (
          <Tile key={k} label={k.replace(/_/g, " ")} value={typeof v === "number" && k.includes("revenue") ? `₦${v.toLocaleString()}` : v} />
        ))}
      </div>
    </div>
  );
}

function FeedbackView() {
  const [items, setItems] = useState([]);
  useEffect(() => { (async () => { const { data } = await api.get("/feedback/all"); setItems(data); })(); }, []);
  return (
    <div className="space-y-4 fade-up" data-testid="admin-feedback">
      <h2 className="font-display text-2xl">All feedback</h2>
      {items.length === 0 ? <div className="card-soft text-sm text-slate-500 text-center py-8">No feedback yet.</div> : (
        <div className="grid gap-3">
          {items.map((f) => (
            <div key={f.id} className="card-soft">
              <div className="flex items-center gap-1 text-amber-500">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star key={i} className={i < f.rating ? "size-4 fill-current" : "size-4 text-slate-300"} />
                ))}
                <span className="ml-2 text-xs text-slate-500">from {f.patient_name}</span>
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



function WhatsAppView() {
  const [status, setStatus] = useState(null);
  const [broadcasts, setBroadcasts] = useState([]);
  const [customTip, setCustomTip] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [s, b] = await Promise.all([
        api.get("/whatsapp/status"),
        api.get("/whatsapp/broadcasts"),
      ]);
      setStatus(s.data);
      setBroadcasts(b.data.items || []);
    } catch (e) { console.error("[wa-admin]", e); }
  };
  useEffect(() => { load(); }, []);

  const broadcast = async (useCustom) => {
    setBusy(true);
    try {
      const { data } = await api.post("/whatsapp/broadcast/health-tip", {
        custom_tip: useCustom ? customTip.trim() : null,
      });
      toast.success(`Broadcast sent — ${data.sent} of ${data.eligible} patients`);
      if (useCustom) setCustomTip("");
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Broadcast failed");
    } finally { setBusy(false); }
  };

  const modeColor = status?.mode === "live" ? "text-green-600 bg-green-50 border-green-200" : "text-amber-700 bg-amber-50 border-amber-200";

  return (
    <div className="space-y-8 fade-up" data-testid="admin-whatsapp">
      <div>
        <div className="overline">Channel</div>
        <h2 className="font-display text-3xl tracking-tight">WhatsApp</h2>
        <p className="text-sm text-slate-500 mt-1">Channel health, weekly health-tip broadcast, and delivery audit.</p>
      </div>

      <div className="card-elevated" data-testid="wa-status-card">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="overline">Integration status</div>
            <h3 className="font-display text-xl mt-1">Meta WhatsApp Cloud API</h3>
          </div>
          {status && (
            <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${modeColor}`} data-testid="wa-mode-badge">
              {status.mode === "live" ? "● LIVE" : "● STUB"}
            </span>
          )}
        </div>
        <dl className="grid sm:grid-cols-2 gap-4 mt-5 text-sm">
          <div>
            <dt className="text-xs text-slate-500">Enabled</dt>
            <dd className="font-medium">{status?.enabled ? "Yes" : "No (stub mode)"}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Credentials configured</dt>
            <dd className="font-medium">{status?.has_credentials ? "Yes" : "Missing"}</dd>
          </div>
          {status?.message_counts_by_status && Object.entries(status.message_counts_by_status).map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-slate-500 capitalize">{k} messages</dt>
              <dd className="font-medium">{v}</dd>
            </div>
          ))}
        </dl>
        {status && !status.has_credentials && (
          <p className="text-xs text-amber-700 mt-4 leading-relaxed">
            Currently in stub mode — outbound calls log + persist to MongoDB but no real WhatsApp is sent.
            Set <code className="bg-amber-100 px-1 rounded">WHATSAPP_ENABLED=true</code> with Meta credentials in <code className="bg-amber-100 px-1 rounded">backend/.env</code> to go live.
          </p>
        )}
      </div>

      <div className="card-elevated" data-testid="wa-broadcast-card">
        <div className="overline flex items-center gap-1.5"><Send className="size-3.5" /> Broadcast</div>
        <h3 className="font-display text-xl mt-1">Weekly health tip</h3>
        <p className="text-sm text-slate-500 mt-1">
          Sends one tip to every patient who opted in. AI-generates the tip pool, or you can write a custom one below.
        </p>
        <div className="mt-5 space-y-3">
          <button
            onClick={() => broadcast(false)}
            disabled={busy}
            className="btn-primary"
            data-testid="wa-broadcast-ai-btn"
          >
            <Send className="size-4" /> Send AI-generated tip now
          </button>
          <div className="relative">
            <div className="absolute inset-0 flex items-center" aria-hidden="true">
              <div className="w-full border-t border-slate-200"></div>
            </div>
            <div className="relative flex justify-center">
              <span className="bg-white px-3 text-xs uppercase tracking-widest text-slate-400">or</span>
            </div>
          </div>
          <textarea
            value={customTip}
            onChange={(e) => setCustomTip(e.target.value)}
            placeholder="Write a custom tip (max 400 chars). E.g., 'Hydrate before noon, especially during harmattan.'"
            rows={3}
            maxLength={400}
            className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            data-testid="wa-custom-tip-input"
          />
          <button
            onClick={() => broadcast(true)}
            disabled={busy || !customTip.trim()}
            className="btn-ghost-pill"
            data-testid="wa-broadcast-custom-btn"
          >
            <Send className="size-4" /> Send custom tip
          </button>
        </div>
      </div>

      <div className="card-elevated" data-testid="wa-broadcast-history">
        <div className="overline flex items-center gap-1.5"><CheckCircle2 className="size-3.5" /> History</div>
        <h3 className="font-display text-xl mt-1">Recent broadcasts</h3>
        {broadcasts.length === 0 && <p className="text-sm text-slate-500 mt-3">No broadcasts yet.</p>}
        <div className="mt-4 divide-y divide-slate-100">
          {broadcasts.map((b) => (
            <div key={b.id} className="py-3 flex items-center justify-between gap-3 text-sm">
              <div>
                <div className="font-medium">{b.kind.replace(/_/g, " ")}</div>
                <div className="text-xs text-slate-500">{new Date(b.created_at).toLocaleString()} · {b.custom_tip ? "Custom" : "AI"}</div>
              </div>
              <div className="text-right text-xs">
                <div><span className="font-medium text-green-700">{b.sent}</span> sent</div>
                <div className="text-slate-500">{b.eligible} eligible · {b.failed} failed</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
