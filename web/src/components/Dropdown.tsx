import { useEffect, useRef, useState } from "react";

type Option = { value: string; label: string };

export default function Dropdown(
  { value, options, onChange }:
  { value: string; options: Option[]; onChange: (v: string) => void },
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

  const current = options.find((o) => o.value === value);
  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "6px 12px", fontSize: 13, font: "inherit",
          border: "1px solid rgba(128,128,128,0.35)", borderRadius: 8,
          background: "transparent", color: "inherit",
        }}
      >
        {current?.label ?? value}
        <span aria-hidden style={{
          fontSize: 9, opacity: 0.6,
          transform: open ? "rotate(180deg)" : "none",
          transition: "transform .18s ease",
        }}>▼</span>
      </button>
      <div
        role="listbox"
        style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 10,
          minWidth: 230, padding: 4,
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
        {options.map((o) => (
          <button
            key={o.value}
            role="option"
            aria-selected={o.value === value}
            className="dd-option"
            onClick={() => { onChange(o.value); setOpen(false); }}
            style={{
              display: "flex", alignItems: "center", gap: 8, width: "100%",
              padding: "7px 10px", fontSize: 13, font: "inherit",
              textAlign: "left", border: "none", borderRadius: 6,
              background: "transparent", color: "inherit",
              fontWeight: o.value === value ? 650 : 400,
            }}
          >
            <span style={{ width: 14, opacity: 0.8 }} aria-hidden>
              {o.value === value ? "✓" : ""}
            </span>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
