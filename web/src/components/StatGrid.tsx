import type { PersonStats } from "../api";
import { fmtDuration, fmtPercent } from "../lib/format";

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: 12, border: "1px solid rgba(128,128,128,0.25)",
                  borderRadius: 8 }}>
      <div style={{ fontSize: 12, opacity: 0.6 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
    </div>
  );
}

export const statGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
  gap: 8, margin: "16px 0",
} as const;

export default function StatGrid({ stats }: { stats: PersonStats }) {
  const fav = (xs: { emoji?: string; kind?: string; count: number }[]) =>
    xs.length ? `${xs[0].emoji ?? xs[0].kind} ×${xs[0].count}` : "—";
  return (
    <div style={statGridStyle}>
      <Stat label="Total messages" value={stats.total.toLocaleString()} />
      <Stat label="Sent / received"
            value={`${stats.sent.toLocaleString()} / ${stats.received.toLocaleString()}`} />
      <Stat label="You start convos" value={fmtPercent(stats.initiation_rate_me)} />
      <Stat label="Your reply time (median)"
            value={fmtDuration(stats.median_response_seconds_me)} />
      <Stat label="Their reply time (median)"
            value={fmtDuration(stats.median_response_seconds_them)} />
      <Stat label="Their favorite emoji" value={fav(stats.top_emojis_them)} />
      <Stat label="Their top tapback" value={fav(stats.tapbacks_from_them)} />
    </div>
  );
}
