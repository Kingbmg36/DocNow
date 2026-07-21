import { useEffect, useState, useRef } from "react";
import { Bell, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";

export default function NotificationsBell() {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const { data } = await api.get("/notifications");
      setItems(data.items || []);
      setUnread(data.unread || 0);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const openItem = async (n) => {
    if (!n.read) {
      try { await api.post(`/notifications/${n.id}/read`); } catch { /* ignore */ }
    }
    setOpen(false);
    if (n.link) navigate(n.link);
    load();
  };

  const markAll = async () => {
    try { await api.post("/notifications/read-all"); } catch { /* ignore */ }
    load();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        data-testid="notifications-bell"
        className="relative size-10 rounded-full border border-slate-200 grid place-items-center hover:bg-slate-50 transition-colors"
        aria-label="Notifications"
      >
        <Bell className="size-4 text-slate-700" />
        {unread > 0 && (
          <span data-testid="notifications-unread-badge"
            className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] rounded-full size-5 grid place-items-center font-bold">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-12 w-80 max-w-[90vw] bg-white border border-slate-100 rounded-2xl shadow-xl z-50 overflow-hidden" data-testid="notifications-panel">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
            <div className="font-medium text-sm">Notifications</div>
            <div className="flex items-center gap-2">
              {unread > 0 && (
                <button onClick={markAll} className="text-xs text-teal-700 hover:underline" data-testid="mark-all-read">Mark all read</button>
              )}
              <button onClick={() => setOpen(false)} aria-label="Close"><X className="size-4 text-slate-400" /></button>
            </div>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-slate-500">No notifications</div>
            ) : items.map((n) => (
              <button
                key={n.id}
                onClick={() => openItem(n)}
                data-testid={`notification-row-${n.id}`}
                className={`block w-full text-left px-4 py-3 border-b border-slate-100 hover:bg-slate-50 transition-colors ${!n.read ? "bg-teal-50/40" : ""}`}
              >
                <div className="text-sm font-medium text-slate-800 line-clamp-1">{n.title}</div>
                {n.body && <div className="text-xs text-slate-600 mt-0.5 line-clamp-2">{n.body}</div>}
                <div className="text-[10px] text-slate-400 mt-1">{new Date(n.created_at).toLocaleString()}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
