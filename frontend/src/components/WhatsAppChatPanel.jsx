/**
 * WhatsAppChatPanel — doctor-facing slide-in panel for patient WA conversation.
 *
 * Polls /api/whatsapp/conversations/:patient_id every 5s during open consultation.
 * Doctor can send free-form text (only allowed inside the 24h customer-care window;
 * backend handles template fallback if needed — currently surfaces send error).
 */
import { useEffect, useRef, useState } from "react";
import { MessageCircle, Send, X, Phone, CheckCheck, Check, AlertCircle } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const STATUS_ICON = {
  stubbed: <AlertCircle className="size-3 text-amber-500" />,
  sent: <Check className="size-3 text-slate-400" />,
  delivered: <CheckCheck className="size-3 text-slate-400" />,
  read: <CheckCheck className="size-3 text-teal-500" />,
  failed: <AlertCircle className="size-3 text-red-500" />,
};

export default function WhatsAppChatPanel({ patientId, patientName, patientPhone, onClose }) {
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const scrollRef = useRef(null);

  const fetchMessages = async () => {
    try {
      const { data } = await api.get(`/whatsapp/conversations/${patientId}`);
      setMessages(data.messages || []);
    } catch (e) {
      console.error("[wa-chat fetch]", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMessages();
    const t = setInterval(fetchMessages, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages.length]);

  const handleSend = async () => {
    const txt = body.trim();
    if (!txt) return;
    setSending(true);
    try {
      await api.post(`/whatsapp/conversations/${patientId}/send`, { body: txt });
      setBody("");
      await fetchMessages();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Send failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-y-0 right-0 w-full sm:w-[420px] bg-white shadow-2xl border-l border-slate-200 flex flex-col z-50"
      data-testid="wa-chat-panel"
    >
      <header className="px-5 py-4 border-b border-slate-100 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="overline flex items-center gap-1.5 text-teal-700">
            <MessageCircle className="size-3.5" /> WhatsApp
          </div>
          <h3 className="font-display text-lg leading-tight truncate" data-testid="wa-chat-patient-name">{patientName}</h3>
          <div className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
            <Phone className="size-3" /> {patientPhone || "—"}
          </div>
        </div>
        <button
          onClick={onClose}
          className="size-8 rounded-lg hover:bg-slate-100 grid place-items-center text-slate-500"
          data-testid="wa-chat-close"
          aria-label="Close WhatsApp panel"
        >
          <X className="size-4" />
        </button>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-4 bg-gradient-to-b from-teal-50/30 to-white space-y-2"
        data-testid="wa-chat-thread"
      >
        {loading && (
          <div className="text-center text-xs text-slate-400 py-8">Loading conversation…</div>
        )}
        {!loading && messages.length === 0 && (
          <div className="text-center text-xs text-slate-500 py-12 max-w-xs mx-auto">
            <MessageCircle className="size-6 mx-auto text-slate-300 mb-2" />
            No WhatsApp messages yet with this patient. Send the first message to open a 24-hour care window.
          </div>
        )}
        {messages.map((m) => {
          const outbound = m.direction === "outbound";
          return (
            <div
              key={m.id || m.whatsapp_message_id}
              className={`flex ${outbound ? "justify-end" : "justify-start"}`}
              data-testid={`wa-chat-msg-${m.direction}`}
            >
              <div
                className={`max-w-[78%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                  outbound
                    ? "bg-teal-600 text-white rounded-br-sm"
                    : "bg-white text-slate-800 border border-slate-200 rounded-bl-sm"
                }`}
              >
                {m.template_name && outbound && (
                  <div className={`text-[10px] uppercase tracking-wider mb-1 opacity-70`}>
                    Template · {m.template_name.replace(/^docnow_/, "")}
                  </div>
                )}
                <div className="whitespace-pre-wrap break-words">{m.body || (m.payload?.text?.body) || "—"}</div>
                {outbound && (
                  <div className="flex items-center gap-1 justify-end mt-1 text-[10px] opacity-80">
                    {STATUS_ICON[m.status] || null}
                    <span>{m.status}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <footer className="border-t border-slate-100 p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Reply via WhatsApp…"
            rows={2}
            className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            data-testid="wa-chat-input"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <button
            onClick={handleSend}
            disabled={sending || !body.trim()}
            className="btn-primary shrink-0"
            data-testid="wa-chat-send"
            aria-label="Send WhatsApp message"
          >
            <Send className="size-4" />
          </button>
        </div>
        <p className="text-[10px] text-slate-400 mt-2 leading-snug">
          Free-form replies allowed for 24h after the patient's last message. Outside this
          window, an approved template is required.
        </p>
      </footer>
    </div>
  );
}
