import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { X, CheckCircle2 } from "lucide-react";

export default function SectionModal({ section, onClose, onSaved }) {
  const [form, setForm] = useState(() => {
    const init = {};
    section.fields.forEach((f) => {
      init[f.key] = section.values?.[f.key] ?? (f.type === "multiselect" ? [] : f.type === "bool" ? false : "");
    });
    return init;
  });
  const [loading, setLoading] = useState(false);

  const set = (k, v) => setForm({ ...form, [k]: v });

  const save = async () => {
    setLoading(true);
    // Convert empty strings to null so backend can store cleanly
    const payload = {};
    section.fields.forEach((f) => {
      const v = form[f.key];
      if (f.type === "number" || f.type === "scale") {
        payload[f.key] = v === "" || v === null ? null : Number(v);
      } else if (f.type === "bool") {
        payload[f.key] = !!v;
      } else {
        payload[f.key] = v ?? null;
      }
    });
    try {
      await api.post(`/profile/sections/${section.key}`, payload);
      toast.success(`${section.title} saved`);
      onSaved?.();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm grid place-items-center p-4" data-testid={`section-modal-${section.key}`}>
      <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <div className="overline mb-0.5">Section {section.section_number}</div>
            <h2 className="font-display text-xl">{section.title}</h2>
            <p className="text-xs text-slate-500 mt-1">{section.subtitle}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700" data-testid={`section-close-${section.key}`}>
            <X className="size-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {section.fields.map((f) => (
            <FieldRow key={f.key} field={f} value={form[f.key]} onChange={(v) => set(f.key, v)} sectionKey={section.key} />
          ))}
        </div>
        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between bg-slate-50/40">
          <button onClick={onClose} className="btn-ghost-pill" data-testid={`section-skip-${section.key}`}>Skip for now</button>
          <button onClick={save} disabled={loading} className="btn-primary disabled:opacity-60" data-testid={`section-save-${section.key}`}>
            {loading ? "Saving…" : <>Save <CheckCircle2 className="size-4" /></>}
          </button>
        </div>
      </div>
    </div>
  );
}

function FieldRow({ field, value, onChange, sectionKey }) {
  const tid = `field-${sectionKey}-${field.key}`;
  const baseInput = "mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100";
  switch (field.type) {
    case "text":
      return (
        <Wrap field={field}>
          <input data-testid={tid} value={value || ""} onChange={(e) => onChange(e.target.value)} className={baseInput} />
        </Wrap>
      );
    case "textarea":
      return (
        <Wrap field={field}>
          <textarea data-testid={tid} value={value || ""} onChange={(e) => onChange(e.target.value)} rows={3} className={baseInput} />
        </Wrap>
      );
    case "number":
      return (
        <Wrap field={field}>
          <input data-testid={tid} type="number" min={field.min} max={field.max} step="any" value={value ?? ""} onChange={(e) => onChange(e.target.value)} className={baseInput} />
        </Wrap>
      );
    case "date":
      return (
        <Wrap field={field}>
          <input data-testid={tid} type="date" value={value || ""} onChange={(e) => onChange(e.target.value)} className={baseInput} />
        </Wrap>
      );
    case "select":
      return (
        <Wrap field={field}>
          <select data-testid={tid} value={value || ""} onChange={(e) => onChange(e.target.value)} className={baseInput + " bg-white"}>
            <option value="">— select —</option>
            {field.options.map((o) => (<option key={o} value={o}>{o}</option>))}
          </select>
        </Wrap>
      );
    case "multiselect": {
      const arr = Array.isArray(value) ? value : [];
      return (
        <Wrap field={field}>
          <div className="mt-1 flex flex-wrap gap-2">
            {field.options.map((o) => {
              const on = arr.includes(o);
              return (
                <button
                  key={o}
                  type="button"
                  data-testid={`${tid}-${o.toLowerCase().replace(/\s+/g, "-")}`}
                  onClick={() => onChange(on ? arr.filter((x) => x !== o) : [...arr, o])}
                  className={["rounded-full border px-3 py-1.5 text-xs transition-all",
                    on ? "border-teal-600 bg-teal-50 text-teal-800" : "border-slate-200 text-slate-600 hover:border-slate-300"].join(" ")}
                >
                  {o}
                </button>
              );
            })}
          </div>
        </Wrap>
      );
    }
    case "scale": {
      const min = field.min ?? 0, max = field.max ?? 5;
      const steps = [];
      for (let i = min; i <= max; i++) steps.push(i);
      return (
        <Wrap field={field}>
          <div className="mt-1 flex gap-2">
            {steps.map((s) => {
              const on = value === s || value === String(s);
              return (
                <button key={s} type="button" data-testid={`${tid}-${s}`} onClick={() => onChange(s)}
                  className={["size-10 rounded-xl border text-sm font-medium transition-all",
                    on ? "border-teal-600 bg-teal-600 text-white" : "border-slate-200 text-slate-600 hover:border-slate-300"].join(" ")}
                >{s}</button>
              );
            })}
          </div>
        </Wrap>
      );
    }
    case "bool":
      return (
        <Wrap field={field}>
          <div className="mt-1 flex gap-2">
            {[{v: true, l: "Yes"}, {v: false, l: "No"}].map((opt) => {
              const on = value === opt.v;
              return (
                <button key={opt.l} type="button" data-testid={`${tid}-${opt.l.toLowerCase()}`} onClick={() => onChange(opt.v)}
                  className={["rounded-xl border px-5 py-2 text-sm font-medium transition-all",
                    on ? "border-teal-600 bg-teal-50 text-teal-800" : "border-slate-200 text-slate-600 hover:border-slate-300"].join(" ")}
                >{opt.l}</button>
              );
            })}
          </div>
        </Wrap>
      );
    default:
      return null;
  }
}

function Wrap({ field, children }) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-700">{field.label}</label>
      {children}
    </div>
  );
}
