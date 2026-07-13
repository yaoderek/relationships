import type { Bucket } from "../api";

const BUCKETS: Bucket[] = ["day", "week", "month"];

export default function BucketPicker(
  { value, onChange }: { value: Bucket; onChange: (b: Bucket) => void },
) {
  return (
    <div style={{ display: "inline-flex", gap: 6 }}>
      {BUCKETS.map((b) => (
        <button key={b} onClick={() => onChange(b)}
                style={{
                  fontSize: 13, padding: "5px 12px", borderRadius: 999,
                  font: "inherit", color: "inherit",
                  fontWeight: value === b ? 650 : 400,
                  background: value === b
                    ? "rgba(91,143,249,0.22)" : "transparent",
                  border: value === b
                    ? "1px solid rgba(91,143,249,0.7)"
                    : "1px solid rgba(128,128,128,0.3)",
                  transition: "background .18s ease, border-color .18s ease",
                }}>
          {b}
        </button>
      ))}
    </div>
  );
}
