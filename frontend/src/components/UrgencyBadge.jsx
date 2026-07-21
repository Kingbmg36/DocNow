import { cn } from "@/lib/utils";

const COLORS = {
  Emergency: "bg-red-50 text-red-700 border-red-200",
  High: "bg-orange-50 text-orange-700 border-orange-200",
  Moderate: "bg-amber-50 text-amber-700 border-amber-200",
  Low: "bg-green-50 text-green-700 border-green-200",
};

export default function UrgencyBadge({ level, className }) {
  const cls = COLORS[level] || "bg-slate-50 text-slate-700 border-slate-200";
  return (
    <span
      data-testid={`urgency-badge-${(level || "unknown").toLowerCase()}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold tracking-wide uppercase",
        cls,
        className
      )}
    >
      <span className="size-1.5 rounded-full bg-current opacity-70" />
      {level || "Unknown"}
    </span>
  );
}
