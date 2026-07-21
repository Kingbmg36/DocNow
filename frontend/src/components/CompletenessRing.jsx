export default function CompletenessRing({ percent = 0, size = 56, label }) {
  const stroke = 6;
  const radius = (size - stroke) / 2;
  const circ = 2 * Math.PI * radius;
  const dash = (Math.min(100, Math.max(0, percent)) / 100) * circ;
  return (
    <div className="flex items-center gap-3" data-testid="completeness-ring">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="rotate-[-90deg]">
        <circle cx={size/2} cy={size/2} r={radius} stroke="#e2e8f0" strokeWidth={stroke} fill="none" />
        <circle cx={size/2} cy={size/2} r={radius} stroke="#0D9488" strokeWidth={stroke} fill="none"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" />
      </svg>
      <div className="leading-tight">
        <div className="font-display text-xl">{percent}%</div>
        <div className="text-xs text-slate-500 uppercase tracking-widest">{label || "Profile"}</div>
      </div>
    </div>
  );
}
