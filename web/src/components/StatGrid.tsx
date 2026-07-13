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
  const num = (x: number | null, digits = 1) =>
    x == null ? "—" : x.toFixed(digits);
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
      <Stat label="Texts per reply (you)" value={num(stats.avg_reply_block_me)} />
      <Stat label="Texts per reply (them)" value={num(stats.avg_reply_block_them)} />
      <Stat label="Reply ratio (them : you)"
            value={stats.reply_block_ratio == null ? "—"
                   : `${num(stats.reply_block_ratio, 2)} : 1`} />
      <Stat label="Your double texts"
            value={stats.double_texts_me.toLocaleString()} />
      <Stat label="Their double texts"
            value={stats.double_texts_them.toLocaleString()} />
      <Stat label="They left you on read"
            value={stats.ghosts_by_them.toLocaleString()} />
      <Stat label="You left them on read"
            value={stats.ghosts_by_me.toLocaleString()} />
      <Stat label="Avg convo duration"
            value={fmtDuration(stats.avg_session_seconds)} />
      <Stat label="Msgs per convo" value={num(stats.avg_session_messages)} />
      <Stat label="Their favorite emoji" value={fav(stats.top_emojis_them)} />
      <Stat label="Their top tapback" value={fav(stats.tapbacks_from_them)} />
    </div>
  );
}
