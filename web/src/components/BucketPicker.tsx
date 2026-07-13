import type { Bucket } from "../api";

const BUCKETS: Bucket[] = ["day", "week", "month"];

export default function BucketPicker(
  { value, onChange }: { value: Bucket; onChange: (b: Bucket) => void },
) {
  return (
    <div style={{ display: "inline-flex", gap: 4 }}>
      {BUCKETS.map((b) => (
        <button key={b} onClick={() => onChange(b)}
                style={{ fontWeight: value === b ? 700 : 400 }}>
          {b}
        </button>
      ))}
    </div>
  );
}
