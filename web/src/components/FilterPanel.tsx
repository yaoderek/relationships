import { useEffect, useRef, useState } from "react";

export type RangeDays = number | null;

const RANGES: { value: RangeDays; label: string }[] = [
  { value: null, label: "All time" },
  { value: 30, label: "Last 30 days" },
  { value: 90, label: "Last 90 days" },
  { value: 365, label: "Last year" },
  { value: 1095, label: "Last 3 years" },
];

export default function FilterPanel(
  { range, onRange, hideInactive, onHideInactive }:
  { range: RangeDays; onRange: (d: RangeDays) => void;
    hideInactive: boolean; onHideInactive: (v: boolean) => void },
) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const active = (range !== null ? 1 : 0) + (hideInactive ? 1 : 0);
  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "6px 12px", fontSize: 13, font: "inherit",
          border: "1px solid rgba(128,128,128,0.35)", borderRadius: 8,
          background: "transparent", color: "inherit",
        }}
      >
        Filters
        {active > 0 && (
          <span style={{ fontSize: 11, lineHeight: "16px", minWidth: 16,
                         textAlign: "center", borderRadius: 999,
                         background: "rgba(91,143,249,0.25)" }}>
            {active}
          </span>
        )}
      </button>
      <div
        role="dialog"
        style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 10,
          minWidth: 210, padding: 10,
          background: "Canvas", color: "CanvasText",
          border: "1px solid rgba(128,128,128,0.3)", borderRadius: 10,
          boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
          transformOrigin: "top left",
          opacity: open ? 1 : 0,
          transform: open ? "translateY(0) scale(1)" : "translateY(-4px) scale(0.98)",
          pointerEvents: open ? "auto" : "none",
          transition: "opacity .18s ease, transform .18s ease",
        }}
      >
        <div style={{ fontSize: 11, opacity: 0.55, textTransform: "uppercase",
                      letterSpacing: 0.5, marginBottom: 6 }}>
          Time range
        </div>
        {RANGES.map((r) => (
          <button key={String(r.value)}
                  className="dd-option"
                  onClick={() => onRange(r.value)}
                  style={{
                    display: "flex", alignItems: "center", gap: 8, width: "100%",
                    padding: "6px 8px", fontSize: 13, font: "inherit",
                    textAlign: "left", border: "none", borderRadius: 6,
                    background: "transparent", color: "inherit",
                    fontWeight: range === r.value ? 650 : 400,
                  }}>
            <span style={{ width: 14, opacity: 0.8 }} aria-hidden>
              {range === r.value ? "✓" : ""}
            </span>
            {r.label}
          </button>
        ))}
        <div style={{ height: 1, background: "rgba(128,128,128,0.2)",
                      margin: "8px 0" }} />
        <label className="dd-option"
               style={{ display: "flex", alignItems: "center", gap: 8,
                        padding: "6px 8px", fontSize: 13, borderRadius: 6,
                        cursor: "pointer" }}>
          <input type="checkbox" checked={hideInactive}
                 onChange={(e) => onHideInactive(e.target.checked)} />
          Hide inactive (30+ days quiet)
        </label>
      </div>
    </div>
  );
}
