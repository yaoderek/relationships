import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchPersons } from "../api";
import type { PersonSummary } from "../api";
import Dropdown from "../components/Dropdown";
import Leaderboard from "../components/Leaderboard";
import { fmtDuration, fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

type SortMetric = {
  key: keyof PersonSummary;
  label: string;
  fmt: (x: number) => string;
};

const count = (x: number) => x.toLocaleString();
const oneDecimal = (x: number) => x.toFixed(1);

const SORT_METRICS: SortMetric[] = [
  { key: "total", label: "Total messages", fmt: count },
  { key: "median_response_seconds_them", label: "Their reply time (median)", fmt: fmtDuration },
  { key: "median_response_seconds_me", label: "Your reply time (median)", fmt: fmtDuration },
  { key: "initiation_rate_me", label: "You start convos", fmt: fmtPercent },
  { key: "avg_reply_block_them", label: "Texts per reply (them)", fmt: oneDecimal },
  { key: "avg_reply_block_me", label: "Texts per reply (you)", fmt: oneDecimal },
  { key: "double_texts_them", label: "Their double texts", fmt: count },
  { key: "double_texts_me", label: "Your double texts", fmt: count },
  { key: "ghosts_by_them", label: "They left you on read", fmt: count },
  { key: "ghosts_by_me", label: "You left them on read", fmt: count },
  { key: "avg_session_seconds", label: "Avg convo duration", fmt: fmtDuration },
  { key: "avg_session_messages", label: "Msgs per convo", fmt: oneDecimal },
  { key: "streak_days", label: "Current streak (days)", fmt: count },
];

const DAY_MS = 86400000;

function decorate(p: PersonSummary): string {
  if (p.streak_days >= 3) return `${p.display_name} 🔥${p.streak_days}`;
  const daysSince = (Date.now() - new Date(p.last_ts).getTime()) / DAY_MS;
  if (daysSince > 30) return `${p.display_name} 😴`;
  return p.display_name;
}

export default function People() {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortMetric["key"]>("total");
  const persons = useFetch(fetchPersons, []);
  const metric = SORT_METRICS.find((m) => m.key === sortKey)!;
  const value = (p: PersonSummary) => p[metric.key] as number | null;
  // Rank within the top 100 by volume so tiny chats don't dominate ratio metrics.
  const rows = (persons ?? [])
    .slice(0, 100)
    .sort((a, b) => (value(b) ?? -Infinity) - (value(a) ?? -Infinity));
  return (
    <>
      <h1>People</h1>
      <div style={{ display: "flex", alignItems: "center", gap: 8,
                    margin: "4px 0 12px" }}>
        <span style={{ fontSize: 13, opacity: 0.7 }}>sort by</span>
        <Dropdown
          value={sortKey}
          options={SORT_METRICS.map((m) => ({ value: m.key, label: m.label }))}
          onChange={(v) => setSortKey(v as SortMetric["key"])}
        />
      </div>
      {persons && (
        <Leaderboard
          rows={rows.map((p) => {
            const v = value(p);
            return {
              key: p.person_id, name: decorate(p),
              total: v ?? 0,
              display: v == null ? "—" : metric.fmt(v),
              subtitle: `${p.total.toLocaleString()} msgs · `
                + `${p.first_ts.slice(0, 10)} → ${p.last_ts.slice(0, 10)}`,
            };
          })}
          onSelect={(id) => navigate(`/person/${id}`)}
        />
      )}
    </>
  );
}
