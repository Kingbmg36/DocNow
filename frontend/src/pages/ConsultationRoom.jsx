import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { toast } from "sonner";
import {
  Stethoscope, ArrowLeft, Send, Pill, ClipboardCheck, Plus, X, Save, FileCheck2, Video, Phone, MessageCircle,
} from "lucide-react";
import TriageResultCard from "@/components/TriageResultCard";
import UrgencyBadge from "@/components/UrgencyBadge";
import QuestionnaireRunner from "@/components/QuestionnaireRunner";
import WhatsAppChatPanel from "@/components/WhatsAppChatPanel";

export default function ConsultationRoom() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [c, setC] = useState(null);
  const [text, setText] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState([{ medication: "", dosage: "", frequency: "", duration: "", instructions: "" }]);
  const [recommendedTests, setRecommendedTests] = useState("");
  const [busy, setBusy] = useState(false);
  const [callActive, setCallActive] = useState(false);
  const [showPostConsultQx, setShowPostConsultQx] = useState(false);
  const [showWAPanel, setShowWAPanel] = useState(false);
  const scrollRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/consultations/${id}`);
      setC(data);
      setNotes(data.notes || "");
      if (data.prescription) {
        setItems(data.prescription.items.length ? data.prescription.items : [{ medication: "", dosage: "", frequency: "", duration: "", instructions: "" }]);
        setRecommendedTests((data.prescription.recommended_tests || []).join(", "));
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      navigate(-1);
    }
  };
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [c?.messages?.length]);

  useEffect(() => {
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const send = async (e) => {
    e?.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api.post(`/consultations/${id}/messages`, { text });
      setText("");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const saveNotes = async () => {
    setBusy(true);
    try { await api.put(`/consultations/${id}/notes`, { notes }); toast.success("Notes saved"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const savePrescription = async () => {
    const cleaned = items.filter((i) => i.medication.trim());
    if (cleaned.length === 0) { toast.error("Add at least one medication"); return; }
    setBusy(true);
    try {
      await api.post(`/consultations/${id}/prescription`, {
        items: cleaned,
        recommended_tests: recommendedTests.split(",").map((t) => t.trim()).filter(Boolean),
      });
      toast.success("Prescription saved");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const completeConsult = async () => {
    setBusy(true);
    try {
      await api.post(`/consultations/${id}/complete`, { final_notes: notes });
      toast.success("Consultation complete — care plan generated");
      // Doctors get the post-consult clinical summary modal before leaving
      if (user.role === "doctor") {
        setShowPostConsultQx(true);
      } else {
        navigate("/patient");
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  if (!c) {
    return <div className="min-h-screen grid place-items-center"><div className="size-10 rounded-full border-2 border-teal-600 border-t-transparent animate-spin" /></div>;
  }

  const isDoctor = user.role === "doctor";
  const isCompleted = c.status === "completed";
  const mode = c.mode;

  return (
    <div className="min-h-screen flex flex-col bg-[#FDFCFB]" data-testid="consultation-room">
      <header className="border-b border-slate-100 bg-white sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-5 lg:px-10 h-16 flex items-center justify-between gap-4">
          <button onClick={() => navigate(-1)} className="btn-ghost-pill" data-testid="consult-back-button">
            <ArrowLeft className="size-4" /> Back
          </button>
          <div className="text-center min-w-0">
            <div className="font-display text-lg truncate">
              {isDoctor ? c.patient_name : c.doctor_name}
            </div>
            <div className="text-xs text-slate-500">
              {isCompleted ? "Completed" : "In consultation"} · started {new Date(c.started_at).toLocaleString()}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isDoctor && (
              <button
                onClick={() => setShowWAPanel(true)}
                className="btn-ghost-pill !px-3 relative"
                data-testid="open-wa-chat"
                aria-label="Open WhatsApp conversation"
                title="WhatsApp"
              >
                <MessageCircle className="size-4" />
                <span className="hidden sm:inline">WhatsApp</span>
              </button>
            )}
            <UrgencyBadge level={c.case?.urgency} />
          </div>
        </div>
      </header>

      {mode && !isCompleted && (
        <div className="border-b border-slate-100 bg-gradient-to-r from-teal-50 to-blue-50">
          <div className="max-w-[1400px] mx-auto px-5 lg:px-10 py-3 flex items-center justify-between gap-3 flex-wrap" data-testid="call-banner">
            <div className="flex items-center gap-2 text-sm text-slate-700">
              {mode === "video" ? <Video className="size-4 text-teal-700" /> : <Phone className="size-4 text-teal-700" />}
              <span className="font-medium capitalize">{mode}</span> appointment
              {callActive && <span className="ml-2 inline-flex items-center gap-1 text-xs text-green-700"><span className="size-2 rounded-full bg-green-500 animate-pulse" /> Connected (mock)</span>}
            </div>
            <button
              onClick={() => setCallActive((v) => !v)}
              data-testid="join-call-button"
              className={callActive ? "btn-ghost-pill" : "btn-primary"}
            >
              {callActive ? "End " : "Join "}{mode === "video" ? "video" : "call"}
              {!callActive && (mode === "video" ? <Video className="size-4" /> : <Phone className="size-4" />)}
            </button>
          </div>
        </div>
      )}

      <div className="max-w-[1400px] mx-auto w-full px-5 lg:px-10 py-6 grid lg:grid-cols-12 gap-6 flex-1">
        <div className="lg:col-span-7 flex flex-col">
          <div className="card-soft mb-4">
            <div className="overline mb-1">Symptoms</div>
            <p className="text-sm text-slate-800">{c.case?.symptoms}</p>
            <div className="text-xs text-slate-500 mt-1">Duration: {c.case?.duration} · Severity: {c.case?.severity}</div>
            {c.case?.notes && <p className="text-xs text-slate-500 mt-1">Patient notes: {c.case.notes}</p>}
          </div>

          {mode === "video" && callActive && !isCompleted && (
            <div className="rounded-2xl bg-slate-900 text-white aspect-video grid place-items-center mb-4" data-testid="video-stage">
              <div className="text-center px-6">
                <div className="size-16 mx-auto rounded-full bg-white/10 grid place-items-center mb-3">
                  <Video className="size-7" />
                </div>
                <div className="font-display text-xl">Video call (mock preview)</div>
                <div className="text-xs text-white/60 mt-1">In production, a real video provider (Daily.co / LiveKit) will render here.</div>
              </div>
            </div>
          )}

          <div className="card-soft flex flex-col flex-1 min-h-[400px]">
            <div className="overline mb-2">Chat</div>
            <div ref={scrollRef} className="flex-1 overflow-y-auto pr-2 space-y-3" data-testid="chat-messages">
              {(c.messages || []).length === 0 && (
                <div className="text-sm text-slate-400 text-center py-10">No messages yet — say hello.</div>
              )}
              {(c.messages || []).map((m) => {
                const mine = m.sender_id === user.id;
                return (
                  <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
                      mine ? "bg-gradient-to-br from-teal-600 to-blue-700 text-white" : "bg-slate-100 text-slate-800"
                    }`}>
                      <div className={`text-[10px] uppercase tracking-widest mb-0.5 ${mine ? "text-teal-100" : "text-slate-500"}`}>
                        {m.sender_role}
                      </div>
                      {m.text}
                    </div>
                  </div>
                );
              })}
            </div>
            {!isCompleted && (
              <form onSubmit={send} className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
                <input
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  data-testid="chat-input"
                  placeholder="Type a message…"
                  className="flex-1 rounded-full border border-slate-200 px-4 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                />
                <button type="submit" disabled={busy} className="btn-primary !px-4" data-testid="chat-send-button">
                  <Send className="size-4" />
                </button>
              </form>
            )}
          </div>
        </div>

        <div className="lg:col-span-5 space-y-5">
          {c.case?.triage && <TriageResultCard triage={c.case.triage} />}

          {isDoctor && !isCompleted && (
            <>
              <div className="card-soft space-y-3" data-testid="doctor-notes-card">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="overline mb-1">Consultation notes</div>
                    <h3 className="font-display text-lg">Private notes</h3>
                  </div>
                  <button onClick={saveNotes} className="btn-ghost-pill" data-testid="save-notes-button">
                    <Save className="size-4" /> Save
                  </button>
                </div>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={4}
                  data-testid="doctor-notes-textarea"
                  className="w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                  placeholder="Examination findings, assessment, plan…"
                />
              </div>

              <div className="card-soft space-y-3" data-testid="prescription-form">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="overline mb-1 flex items-center gap-1.5"><Pill className="size-3.5" /> Prescription</div>
                    <h3 className="font-display text-lg">Digital prescription</h3>
                  </div>
                  <button onClick={savePrescription} className="btn-ghost-pill" data-testid="save-prescription-button">
                    <Save className="size-4" /> Save
                  </button>
                </div>
                {items.map((it, idx) => (
                  <div key={idx} className="rounded-xl border border-slate-200 p-3 space-y-2 relative">
                    <button onClick={() => setItems(items.filter((_, i) => i !== idx))}
                      className="absolute top-2 right-2 text-slate-400 hover:text-red-600"
                      data-testid={`remove-rx-item-${idx}`}>
                      <X className="size-4" />
                    </button>
                    <input value={it.medication} onChange={(e) => setItems(items.map((x, i) => i === idx ? { ...x, medication: e.target.value } : x))}
                      placeholder="Medication name" data-testid={`rx-medication-${idx}`}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-teal-600 focus:ring-2 focus:ring-teal-100 outline-none" />
                    <div className="grid grid-cols-3 gap-2">
                      <input value={it.dosage} onChange={(e) => setItems(items.map((x, i) => i === idx ? { ...x, dosage: e.target.value } : x))}
                        placeholder="Dosage" data-testid={`rx-dosage-${idx}`}
                        className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
                      <input value={it.frequency} onChange={(e) => setItems(items.map((x, i) => i === idx ? { ...x, frequency: e.target.value } : x))}
                        placeholder="Frequency" data-testid={`rx-frequency-${idx}`}
                        className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
                      <input value={it.duration} onChange={(e) => setItems(items.map((x, i) => i === idx ? { ...x, duration: e.target.value } : x))}
                        placeholder="Duration" data-testid={`rx-duration-${idx}`}
                        className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
                    </div>
                    <input value={it.instructions} onChange={(e) => setItems(items.map((x, i) => i === idx ? { ...x, instructions: e.target.value } : x))}
                      placeholder="Instructions (optional)" data-testid={`rx-instructions-${idx}`}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
                  </div>
                ))}
                <button onClick={() => setItems([...items, { medication: "", dosage: "", frequency: "", duration: "", instructions: "" }])}
                  className="btn-ghost-pill" data-testid="add-rx-item-button">
                  <Plus className="size-4" /> Add medication
                </button>
                <div>
                  <label className="text-xs font-medium text-slate-700">Recommended tests (comma-separated)</label>
                  <input value={recommendedTests} onChange={(e) => setRecommendedTests(e.target.value)}
                    placeholder="e.g., Malaria parasite test, FBC"
                    data-testid="rx-tests-input"
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" />
                </div>
              </div>

              <button onClick={completeConsult} disabled={busy} className="btn-primary w-full disabled:opacity-60" data-testid="complete-consultation-button">
                <FileCheck2 className="size-4" /> Complete consultation & generate Care Plan
              </button>
            </>
          )}

          {c.prescription && (
            <div className="card-soft" data-testid="prescription-readonly-card">
              <div className="overline mb-1">Prescription</div>
              <div className="font-mono text-sm">{c.prescription.code}</div>
              <ul className="mt-2 text-sm divide-y divide-slate-100">
                {c.prescription.items.map((it, i) => (
                  <li key={i} className="py-2">
                    <span className="font-medium">{it.medication}</span>
                    <span className="text-xs text-slate-500 ml-2">{it.dosage} · {it.frequency} · {it.duration}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {isCompleted && c.care_plan && (
            <div className="card-soft" data-testid="care-plan-card">
              <div className="overline mb-1 flex items-center gap-1.5"><ClipboardCheck className="size-3.5" /> Care plan</div>
              <h3 className="font-display text-lg mb-1">{c.care_plan.consultation_summary}</h3>
              <p className="text-sm text-slate-700">{c.care_plan.doctor_advice}</p>
            </div>
          )}
        </div>
      </div>
      {showPostConsultQx && (
        <QuestionnaireRunner
          code="doctor_post_consult"
          contextId={c.id}
          dismissible={false}
          onClose={() => { setShowPostConsultQx(false); navigate("/doctor"); }}
          onSubmitted={() => { setShowPostConsultQx(false); navigate("/doctor"); }}
        />
      )}
      {showWAPanel && isDoctor && (
        <WhatsAppChatPanel
          patientId={c.patient_id}
          patientName={c.patient_name}
          patientPhone={c.patient_phone}
          onClose={() => setShowWAPanel(false)}
        />
      )}
    </div>
  );
}
