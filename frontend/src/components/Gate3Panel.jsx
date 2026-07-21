import { useEffect, useState } from "react";
import api from "@/lib/api";
import { CheckCircle2, Lock, Sparkles } from "lucide-react";
import SectionModal from "./SectionModal";

export default function Gate3Panel({ onCompleted }) {
  const [sections, setSections] = useState([]);
  const [open, setOpen] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get("/profile/sections/mine");
      setSections(data.sections);
    } catch (e) { /* ignore */ }
  };
  useEffect(() => { load(); }, []);

  const unlocked = sections.filter((s) => s.unlocked);
  const locked = sections.filter((s) => !s.unlocked);

  if (sections.length === 0) return null;

  return (
    <div className="card-soft" data-testid="gate3-panel">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="overline mb-1">Your health profile</div>
          <h3 className="font-display text-xl">Sections to complete</h3>
          <p className="text-xs text-slate-500 mt-1">
            Sections unlock as you use DocNow.NG. Completing them helps your doctor and improves recommendations.
          </p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <span className="font-medium text-slate-800">{unlocked.filter(s => s.completed).length}</span> / {sections.length} completed
        </div>
      </div>

      {unlocked.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-3" data-testid="gate3-unlocked-grid">
          {unlocked.map((s) => (
            <button
              key={s.key}
              onClick={() => setOpen(s)}
              data-testid={`gate3-card-${s.key}`}
              className="rounded-2xl border border-slate-200 p-4 text-left hover:border-teal-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs uppercase tracking-widest text-teal-700 font-bold">Section {s.section_number}</div>
                {s.completed ? (
                  <span className="inline-flex items-center gap-1 text-xs text-green-700 font-medium">
                    <CheckCircle2 className="size-3.5" /> Completed
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-amber-700 font-medium">
                    <Sparkles className="size-3.5" /> New
                  </span>
                )}
              </div>
              <div className="font-display text-lg mt-1">{s.title}</div>
              <div className="text-xs text-slate-500 mt-1">{s.subtitle}</div>
            </button>
          ))}
        </div>
      )}

      {locked.length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">Locked — unlock by using the app</div>
          <div className="flex flex-wrap gap-2">
            {locked.map((s) => (
              <span key={s.key} data-testid={`gate3-locked-${s.key}`} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500">
                <Lock className="size-3" /> {s.title}
              </span>
            ))}
          </div>
        </div>
      )}

      {open && (
        <SectionModal
          section={open}
          onClose={() => setOpen(null)}
          onSaved={async () => {
            setOpen(null);
            await load();
            onCompleted?.();
          }}
        />
      )}
    </div>
  );
}
