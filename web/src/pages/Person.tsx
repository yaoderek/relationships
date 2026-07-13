import { useState } from "react";
import { useParams } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchPersonHeatmap, fetchPersonSeries, fetchPersonStats, fetchPersonTrends } from "../api";
import type { Bucket, PersonTrend } from "../api";
import BucketPicker from "../components/BucketPicker";
import Dropdown from "../components/Dropdown";
import Heatmap from "../components/Heatmap";
import HotDays from "../components/HotDays";
import StatGrid from "../components/StatGrid";
import { fmtDuration, fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

type TrendMetric = {
  key: string;
  label: string;
  you: (t: PersonTrend) => number | null;
  them: ((t: PersonTrend) => number | null) | null;
  fmt: (x: number) => string;
};

const raw = (x: number) => (Number.isInteger(x) ? x.toLocaleString() : x.toFixed(1));

const TREND_METRICS: TrendMetric[] = [
  { key: "messages", label: "Messages", fmt: raw,
    you: (t) => t.sent, them: (t) => t.received },
  { key: "reply_time", label: "Reply time (median)", fmt: fmtDuration,
    you: (t) => t.median_reply_me, them: (t) => t.median_reply_them },
  { key: "texts_per_reply", label: "Texts per reply", fmt: raw,
    you: (t) => t.texts_per_reply_me, them: (t) => t.texts_per_reply_them },
  { key: "double_texts", label: "Double texts", fmt: raw,
    you: (t) => t.double_texts_me, them: (t) => t.double_texts_them },
  { key: "initiation", label: "You start convos", fmt: fmtPercent,
    you: (t) => t.initiation_me, them: null },
];

export default function Person() {
  const pid = Number(useParams().id);
  const [bucket, setBucket] = useState<Bucket>("week");
  const [metricKey, setMetricKey] = useState("messages");
  const [includeGroups, setIncludeGroups] = useState(false);
  const stats = useFetch(() => fetchPersonStats(pid), [pid]);
  const trends = useFetch(() => fetchPersonTrends(pid, bucket), [pid, bucket]);
  const groupSeries = useFetch(
    () => includeGroups ? fetchPersonSeries(pid, bucket, true)
                        : Promise.resolve(null),
    [pid, bucket, includeGroups],
  );
  const heatmap = useFetch(() => fetchPersonHeatmap(pid), [pid]);
  if (!stats) return <p>Loading…</p>;

  const first = stats.display_name.split(" ")[0];
  const metric = TREND_METRICS.find((m) => m.key === metricKey)!;
  const useGroupData = metricKey === "messages" && includeGroups && groupSeries;
  const data = useGroupData
    ? groupSeries.map((s) => ({ bucket: s.bucket, you: s.sent, them: s.received }))
    : (trends ?? []).map((t) => ({
        bucket: t.bucket, you: metric.you(t),
        them: metric.them ? metric.them(t) : null,
      }));

  return (
    <>
      <h1>{stats.display_name}</h1>
      <StatGrid stats={stats} />
      <div style={{ display: "flex", alignItems: "center", gap: 12,
                    flexWrap: "wrap", marginBottom: 4 }}>
        <Dropdown
          value={metricKey}
          options={TREND_METRICS.map((m) => ({ value: m.key, label: m.label }))}
          onChange={setMetricKey}
        />
        <BucketPicker value={bucket} onChange={setBucket} />
        {metricKey === "messages" && (
          <label style={{ fontSize: 13 }}>
            <input type="checkbox" checked={includeGroups}
                   onChange={(e) => setIncludeGroups(e.target.checked)} />
            {" "}include group messages
          </label>
        )}
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeOpacity={0.15} vertical={false} />
          <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
          <YAxis tickLine={false} axisLine={false} width={52}
                 tickFormatter={(v: number) => metric.fmt(v)} />
          <Tooltip formatter={(v) => metric.fmt(Number(v))} />
          <Legend />
          <Area type="monotone" dataKey="you" name="You" fill="#61DDAA"
                stroke="#61DDAA" fillOpacity={0.25} strokeWidth={2} connectNulls
                animationDuration={600} animationEasing="ease-out" />
          {metric.them && (
            <Area type="monotone" dataKey="them" name={first} fill="#5B8FF9"
                  stroke="#5B8FF9" fillOpacity={0.25} strokeWidth={2} connectNulls
                  animationDuration={600} animationEasing="ease-out" />
          )}
        </AreaChart>
      </ResponsiveContainer>
      <h2>When you talk</h2>
      {heatmap && <Heatmap cells={heatmap} />}
      <h2>Vernacular</h2>
      <WordChips label={first} words={stats.top_words_them} />
      <WordChips label="You" words={stats.top_words_me} />
      <h2>Hottest days</h2>
      <HotDays personId={pid} />
    </>
  );
}

function WordChips({ label, words }:
  { label: string; words: { word: string; count: number }[] }) {
  if (words.length === 0) return null;
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 8,
                  flexWrap: "wrap", marginBottom: 10 }}>
      <span style={{ fontSize: 12, opacity: 0.6, minWidth: 36 }}>{label}</span>
      {words.map((w) => (
        <span key={w.word}
              style={{ fontSize: 13, padding: "3px 10px", borderRadius: 999,
                       border: "1px solid rgba(128,128,128,0.3)" }}>
          {w.word} <span style={{ opacity: 0.55 }}>×{w.count}</span>
        </span>
      ))}
    </div>
  );
}
