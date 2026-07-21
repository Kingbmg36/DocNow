import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { X, CheckCircle2, ArrowLeft, ArrowRight } from "lucide-react";

/**
 * Generic schema-driven questionnaire wizard.
 *
 * Props:
 *  - code: questionnaire code (e.g. "patient_intake")
 *  - contextId: optional (e.g. consultation_id for post-consult)
 *  - onClose: () => void
 *  - onSubmitted: (responseDoc) => void
 *  - dismissible: boolean (default true) — when false, no close button (blocks user)
 *  - mode: "modal" (default) | "inline"
 */
export default function QuestionnaireRunner({
  code, contextId, onClose, onSubmitted, dismissible = true, mode = "modal",
}) {
  const [schema, setSchema] = useState(null);
  const [step, setStep] = useState(0);
  const [responses, setResponses] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/questionnaires/${code}`);
        setSchema(data);
        // Prefill from any prior response
        try {
          const { data: prev } = await api.get(`/questionnaires/${code}/response/me${contextId ? `?context_id=${contextId}` : ""}`);
          if (prev && prev.responses) setResponses(prev.responses);
        } catch { /* ignore */ }
      } catch (e) {
        toast.error(formatApiError(e.response?.data?.detail) || "Failed to load questionnaire");
      } finally { setLoading(false); }
    })();
  }, [code, contextId]);

  const set = (k, v) => setResponses((r) => ({ ...r, [k]: v }));

  const submit = async () => {
    setSaving(true);
    try {
      // Normalize numeric/scale values
      const payload = { ...responses };
      schema.sections.forEach((s) => {
        s.fields.forEach((f) => {
          if (f.type === "number" || f.type === "scale") {
            if (payload[f.key] === "" || payload[f.key] === undefined) payload[f.key] = null;
            else if (payload[f.key] !== null) payload[f.key] = Number(payload[f.key]);
          }
        });
      });
      const { data } = await api.post(`/questionnaires/${code}/submit`, { responses: payload, context_id: contextId || null });
      toast.success(`${schema.title} saved`);
      onSubmitted?.(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setSaving(false); }
  };

  if (loading || !schema) {
    return mode === "modal" ? (
      <Overlay>
        <div className="bg-white rounded-3xl p-10 grid place-items-center">
          <div className="size-8 rounded-full border-2 border-teal-600 border-t-transparent animate-spin" />
        </div>
      </Overlay>
    ) : <div className="card-soft text-slate-500 text-sm">Loading questionnaire…</div>;
  }

  const sec = schema.sections[step];
  const total = schema.sections.length;
  const last = step === total - 1;

  const body = (
    <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl" data-testid={`qx-${code}`}>
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <div className="overline mb-0.5">Questionnaire · Step {step + 1} of {total}</div>
          <h2 className="font-display text-xl truncate">{schema.title} · {sec.title}</h2>
          <p className="text-xs text-slate-500 mt-1 truncate">{schema.subtitle}</p>
        </div>
        {dismissible && (
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700 ml-2" data-testid={`qx-close-${code}`}>
            <X className="size-5" />
          </button>
        )}
      </div>

      <div className="px-6 pt-3 flex items-center gap-1.5">
        {schema.sections.map((_, i) => (
          <div key={i} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-teal-600" : "bg-slate-200"}`} />
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
        {sec.fields.map((f) => (
          <FieldRow key={f.key} field={f} value={responses[f.key]} onChange={(v) => set(f.key, v)} sectionKey={sec.key} />
        ))}
      </div>

      <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between gap-3 bg-slate-50/40">
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="btn-ghost-pill disabled:opacity-50 disabled:cursor-not-allowed"
          data-testid={`qx-back-${code}`}
        >
          <ArrowLeft className="size-4" /> Back
        </button>
        {!last ? (
          <button onClick={() => setStep((s) => s + 1)} className="btn-primary" data-testid={`qx-next-${code}`}>
            Next <ArrowRight className="size-4" />
          </button>
        ) : (
          <button onClick={submit} disabled={saving} className="btn-primary disabled:opacity-60" data-testid={`qx-submit-${code}`}>
            {saving ? "Submitting…" : <>Submit <CheckCircle2 className="size-4" /></>}
          </button>
        )}
      </div>
    </div>
  );

  return mode === "modal" ? <Overlay>{body}</Overlay> : body;
}

function Overlay({ children }) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm grid place-items-center p-4">
      {children}
    </div>
  );
}

function FieldRow({ field, value, onChange, sectionKey }) {
  const tid = `qxf-${sectionKey}-${field.key}`;
  const base = "mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100";
  const wrap = (children) => (
    <div>
      <label className="text-sm font-medium text-slate-700">{field.label}</label>
      {children}
    </div>
  );
  switch (field.type) {
    case "text":
      return wrap(<input data-testid={tid} value={value || ""} onChange={(e) => onChange(e.target.value)} className={base} />);
    case "textarea":
      return wrap(<textarea data-testid={tid} value={value || ""} onChange={(e) => onChange(e.target.value)} rows={3} className={base} />);
    case "number":
      return wrap(<input data-testid={tid} type="number" min={field.min} max={field.max} step="any" value={value ?? ""} onChange={(e) => onChange(e.target.value)} className={base} />);
    case "date":
      return wrap(<input data-testid={tid} type="date" value={value || ""} onChange={(e) => onChange(e.target.value)} className={base} />);
    case "select":
      return wrap(
        <select data-testid={tid} value={value || ""} onChange={(e) => onChange(e.target.value)} className={base + " bg-white"}>
          <option value="">— select —</option>
          {field.options.map((o) => (<option key={o} value={o}>{o}</option>))}
        </select>
      );
    case "multiselect": {
      const arr = Array.isArray(value) ? value : [];
      return wrap(
        <div className="mt-1 flex flex-wrap gap-2">
          {field.options.map((o) => {
            const on = arr.includes(o);
            return (
              <button key={o} type="button"
                data-testid={`${tid}-${o.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "")}`}
                onClick={() => onChange(on ? arr.filter((x) => x !== o) : [...arr, o])}
                className={["rounded-full border px-3 py-1.5 text-xs transition-all",
                  on ? "border-teal-600 bg-teal-50 text-teal-800" : "border-slate-200 text-slate-600 hover:border-slate-300"].join(" ")}>
                {o}
              </button>
            );
          })}
        </div>
      );
    }
    case "scale": {
      const min = field.min ?? 0, max = field.max ?? 5;
      const steps = [];
      for (let i = min; i <= max; i++) steps.push(i);
      return wrap(
        <div className="mt-1 flex gap-2 flex-wrap">
          {steps.map((s) => {
            const on = value === s || value === String(s);
            return (
              <button key={s} type="button" data-testid={`${tid}-${s}`} onClick={() => onChange(s)}
                className={["size-10 rounded-xl border text-sm font-medium transition-all",
                  on ? "border-teal-600 bg-teal-600 text-white" : "border-slate-200 text-slate-600 hover:border-slate-300"].join(" ")}>
                {s}
              </button>
            );
          })}
        </div>
      );
    }
    case "bool":
      return wrap(
        <div className="mt-1 flex gap-2">
          {[{v: true, l: "Yes"}, {v: false, l: "No"}].map((opt) => {
            const on = value === opt.v;
            return (
              <button key={opt.l} type="button"
                data-testid={`${tid}-${opt.l.toLowerCase()}`}
                onClick={() => onChange(opt.v)}
                className={["rounded-xl border px-5 py-2 text-sm font-medium transition-all",
                  on ? "border-teal-600 bg-teal-50 text-teal-800" : "border-slate-200 text-slate-600 hover:border-slate-300"].join(" ")}>
                {opt.l}
              </button>
            );
          })}
        </div>
      );
    default:
      return null;
  }
}
