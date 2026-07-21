import UrgencyBadge from "./UrgencyBadge";
import { AlertTriangle, Stethoscope, ListChecks, MessageCircleQuestion } from "lucide-react";

export default function TriageResultCard({ triage }) {
  if (!triage) return null;
  return (
    <div className="card-elevated space-y-6" data-testid="triage-result-card">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="overline mb-1">AI Triage Summary</div>
          <h3 className="font-display text-2xl">{triage.summary}</h3>
          {triage.urgency_reasoning && (
            <p className="text-sm text-slate-500 mt-2 max-w-prose">{triage.urgency_reasoning}</p>
          )}
        </div>
        <UrgencyBadge level={triage.urgency} />
      </div>

      {triage.red_flags && triage.red_flags.length > 0 && (
        <div className="rounded-xl bg-red-50/60 border border-red-100 p-4">
          <div className="flex items-center gap-2 text-red-800 font-medium text-sm mb-2">
            <AlertTriangle className="size-4" /> Red flags to watch
          </div>
          <ul className="text-sm text-red-900/80 space-y-1 list-disc list-inside">
            {triage.red_flags.map((rf, i) => <li key={i}>{rf}</li>)}
          </ul>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-xl bg-teal-50/50 border border-teal-100 p-4">
          <div className="flex items-center gap-2 text-teal-800 font-medium text-sm mb-2">
            <Stethoscope className="size-4" /> Recommended specialty
          </div>
          <p className="text-sm text-slate-800">{triage.recommended_specialty}</p>
        </div>
        <div className="rounded-xl bg-blue-50/50 border border-blue-100 p-4">
          <div className="flex items-center gap-2 text-blue-900 font-medium text-sm mb-2">
            <ListChecks className="size-4" /> Suggested next steps
          </div>
          <ul className="text-sm text-slate-700 space-y-1 list-disc list-inside">
            {(triage.next_steps || []).map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      </div>

      {triage.doctor_questions && triage.doctor_questions.length > 0 && (
        <div className="rounded-xl bg-slate-50 border border-slate-200 p-4">
          <div className="flex items-center gap-2 text-slate-800 font-medium text-sm mb-2">
            <MessageCircleQuestion className="size-4" /> Questions the doctor may ask
          </div>
          <ul className="text-sm text-slate-700 space-y-1 list-decimal list-inside">
            {triage.doctor_questions.map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        </div>
      )}

      <div className="text-xs text-slate-500 italic border-t border-slate-100 pt-4">
        {triage.disclaimer}
      </div>
    </div>
  );
}
