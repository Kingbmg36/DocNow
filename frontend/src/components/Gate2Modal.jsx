import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { ShieldAlert, X, AlertTriangle, CheckCircle2 } from "lucide-react";

const GENOTYPES = ["AA", "AS", "SS", "AC", "SC"];
const BLOOD_GROUPS = ["A+","A-","B+","B-","AB+","AB-","O+","O-"];
const COMMON_CHRONIC = ["Hypertension", "Diabetes", "Asthma", "Sickle Cell", "Ulcer", "Epilepsy", "HIV", "Tuberculosis"];

export default function Gate2Modal({ onClose, onComplete }) {
  const [redFlagsCatalog, setRedFlagsCatalog] = useState([]);
  const [form, setForm] = useState({
    genotype: "AA",
    blood_group: "O+",
    height_cm: "",
    weight_kg: "",
    chronic_conditions: [],
    chronic_other: "",
    current_medications: "",
    allergies: "",
    emergency_contact: "",
    active_red_flags: [],
  });
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(1); // 1 vitals + history, 2 red flag screen

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/profile/red-flags");
        setRedFlagsCatalog(data.questions || []);
      } catch (e) { console.error(e); }
    })();
  }, []);

  const toggleChronic = (c) => {
    setForm((f) => ({
      ...f,
      chronic_conditions: f.chronic_conditions.includes(c)
        ? f.chronic_conditions.filter((x) => x !== c)
        : [...f.chronic_conditions, c],
    }));
  };

  const toggleRedFlag = (k) => {
    setForm((f) => ({
      ...f,
      active_red_flags: f.active_red_flags.includes(k)
        ? f.active_red_flags.filter((x) => x !== k)
        : [...f.active_red_flags, k],
    }));
  };

  const save = async () => {
    setLoading(true);
    const chronic = [
      ...form.chronic_conditions,
      ...form.chronic_other.split(",").map((s) => s.trim()).filter(Boolean),
    ];
    const payload = {
      genotype: form.genotype,
      blood_group: form.blood_group,
      height_cm: parseFloat(form.height_cm) || null,
      weight_kg: parseFloat(form.weight_kg) || null,
      chronic_conditions: chronic,
      current_medications: form.current_medications.split(",").map((s) => s.trim()).filter(Boolean),
      allergies: form.allergies.split(",").map((s) => s.trim()).filter(Boolean),
      emergency_contact: form.emergency_contact || null,
      active_red_flags: form.active_red_flags,
    };
    try {
      const { data } = await api.post("/profile/gate2", payload);
      toast.success("Medical profile saved");
      onComplete?.(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm grid place-items-center p-4" data-testid="gate2-modal">
      <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <div className="overline mb-0.5">Gate 2 · Clinical safety floor</div>
            <h2 className="font-display text-xl">Help your doctor help you faster</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close" data-testid="gate2-close">
            <X className="size-5" />
          </button>
        </div>

        <div className="px-6 py-3 border-b border-slate-100 flex items-center gap-3 text-xs">
          <div className="flex items-center gap-2 flex-1">
            {[1, 2].map((s) => (
              <div key={s} className="flex items-center gap-2 flex-1">
                <div className={[
                  "size-6 rounded-full grid place-items-center text-xs font-medium",
                  step > s ? "bg-teal-600 text-white" : step === s ? "bg-teal-100 text-teal-700 ring-2 ring-teal-300" : "bg-slate-100 text-slate-400",
                ].join(" ")}>{s}</div>
                <span className={step === s ? "text-slate-800 font-medium" : "text-slate-500"}>
                  {s === 1 ? "Medical essentials" : "Red flag screen"}
                </span>
                {s === 1 && <div className="flex-1 h-px bg-slate-200 mx-1" />}
              </div>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {step === 1 && (
            <>
              <div className="grid sm:grid-cols-2 gap-3">
                <Select label="Genotype" testid="gate2-genotype" value={form.genotype} onChange={(v) => setForm({...form, genotype: v})} options={GENOTYPES} />
                <Select label="Blood group" testid="gate2-blood-group" value={form.blood_group} onChange={(v) => setForm({...form, blood_group: v})} options={BLOOD_GROUPS} />
                <Number label="Height (cm)" testid="gate2-height" value={form.height_cm} onChange={(v) => setForm({...form, height_cm: v})} />
                <Number label="Weight (kg)" testid="gate2-weight" value={form.weight_kg} onChange={(v) => setForm({...form, weight_kg: v})} />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">Chronic conditions <span className="text-slate-400 font-normal">(pick all that apply)</span></label>
                <div className="mt-2 flex flex-wrap gap-2">
                  {COMMON_CHRONIC.map((c) => {
                    const on = form.chronic_conditions.includes(c);
                    return (
                      <button
                        type="button"
                        key={c}
                        data-testid={`gate2-chronic-${c.toLowerCase().replace(/\s+/g, "-")}`}
                        onClick={() => toggleChronic(c)}
                        className={[
                          "rounded-full border px-3 py-1.5 text-xs transition-all",
                          on ? "border-teal-600 bg-teal-50 text-teal-800" : "border-slate-200 text-slate-600 hover:border-slate-300",
                        ].join(" ")}
                      >
                        {c}
                      </button>
                    );
                  })}
                </div>
                <input
                  data-testid="gate2-chronic-other"
                  value={form.chronic_other}
                  onChange={(e) => setForm({...form, chronic_other: e.target.value})}
                  placeholder="Other (comma-separated)"
                  className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                />
              </div>

              <Field label="Current medications" testid="gate2-medications" value={form.current_medications}
                onChange={(v) => setForm({...form, current_medications: v})} placeholder="Comma-separated, e.g. Amlodipine 5mg, Metformin 500mg" />
              <Field label="Allergies" testid="gate2-allergies" value={form.allergies}
                onChange={(v) => setForm({...form, allergies: v})} placeholder="e.g. Penicillin, peanuts, sulfa drugs" />
              <Field label="Emergency contact (phone)" testid="gate2-emergency" value={form.emergency_contact}
                onChange={(v) => setForm({...form, emergency_contact: v})} placeholder="+234…" />
            </>
          )}

          {step === 2 && (
            <>
              <div className="rounded-2xl bg-red-50 border border-red-100 p-4 flex items-start gap-3">
                <ShieldAlert className="size-5 text-red-700 shrink-0 mt-0.5" />
                <div className="text-sm text-red-900">
                  <div className="font-semibold mb-0.5">Important — clinical safety screen</div>
                  <div>If you are currently experiencing any of these, tick them. If any are ticked, we may suggest going directly to a hospital.</div>
                </div>
              </div>

              <div className="space-y-2">
                {redFlagsCatalog.map((rf) => {
                  const on = form.active_red_flags.includes(rf.key);
                  return (
                    <label key={rf.key} data-testid={`red-flag-${rf.key}`}
                      className={[
                        "flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors",
                        on ? "border-red-300 bg-red-50/50" : "border-slate-200 hover:bg-slate-50",
                      ].join(" ")}>
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => toggleRedFlag(rf.key)}
                        className="mt-0.5 size-4 rounded border-slate-300 text-red-600 focus:ring-red-500"
                      />
                      <div className="text-sm flex-1">
                        <div className="text-slate-800">{rf.label}</div>
                        <div className="text-xs mt-0.5">
                          <span className={rf.severity === "Emergency" ? "text-red-600 font-medium" : "text-amber-700 font-medium"}>
                            {rf.severity}
                          </span>
                        </div>
                      </div>
                      {on && <AlertTriangle className="size-4 text-red-500 shrink-0 mt-1" />}
                    </label>
                  );
                })}
              </div>

              {form.active_red_flags.length > 0 ? (
                <div className="rounded-xl bg-red-50 border border-red-100 p-3 text-sm text-red-900" data-testid="red-flag-warning">
                  <AlertTriangle className="size-4 inline mr-1" />
                  You ticked {form.active_red_flags.length} red flag(s). If any feels life-threatening, please visit the nearest hospital immediately.
                </div>
              ) : (
                <div className="rounded-xl bg-green-50 border border-green-100 p-3 text-sm text-green-800">
                  <CheckCircle2 className="size-4 inline mr-1" /> No red flags reported. You can continue with a routine consultation.
                </div>
              )}
            </>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between gap-3 bg-slate-50/40">
          {step === 1 ? (
            <>
              <button onClick={onClose} className="btn-ghost-pill" data-testid="gate2-skip">Skip for now</button>
              <button onClick={() => setStep(2)} className="btn-primary" data-testid="gate2-next">Continue</button>
            </>
          ) : (
            <>
              <button onClick={() => setStep(1)} className="btn-ghost-pill" data-testid="gate2-back">Back</button>
              <button onClick={save} disabled={loading} className="btn-primary disabled:opacity-60" data-testid="gate2-save">
                {loading ? "Saving…" : "Save & continue"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, testid, value, onChange, placeholder }) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <input data-testid={testid} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
    </div>
  );
}

function Number({ label, testid, value, onChange }) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <input data-testid={testid} type="number" step="any" value={value} onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
    </div>
  );
}

function Select({ label, testid, value, onChange, options }) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <select data-testid={testid} value={value} onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 bg-white outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100">
        {options.map((o) => (<option key={o} value={o}>{o}</option>))}
      </select>
    </div>
  );
}
