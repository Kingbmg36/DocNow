export default function Footer() {
  return (
    <footer className="border-t border-slate-100 bg-white">
      <div className="max-w-7xl mx-auto px-6 lg:px-12 py-12 grid md:grid-cols-4 gap-8 text-sm">
        <div>
          <div className="font-display text-lg font-medium">DocNow.NG</div>
          <p className="text-slate-500 mt-2 leading-relaxed">
            AI-assisted healthcare access for Africa. Built with care for Nigerian patients first.
          </p>
        </div>
        <div>
          <div className="overline mb-3">Product</div>
          <ul className="space-y-2 text-slate-600">
            <li>For patients</li>
            <li>For doctors</li>
            <li>Care plans</li>
            <li>Health vitals</li>
          </ul>
        </div>
        <div>
          <div className="overline mb-3">Compliance</div>
          <ul className="space-y-2 text-slate-600">
            <li>NDPA-aligned</li>
            <li>GDPR-ready</li>
            <li>HIPAA-inspired</li>
            <li>Audit logging</li>
          </ul>
        </div>
        <div>
          <div className="overline mb-3">Safety</div>
          <p className="text-slate-600 leading-relaxed">
            DocNow.NG does not provide medical diagnosis. If this is an emergency, visit the nearest hospital immediately.
          </p>
        </div>
      </div>
      <div className="border-t border-slate-100">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-5 text-xs text-slate-500 flex flex-wrap justify-between gap-2">
          <span>© {new Date().getFullYear()} DocNow.NG. Made in Lagos.</span>
          <span>Not a diagnostic tool. Consult a qualified clinician.</span>
        </div>
      </div>
    </footer>
  );
}
