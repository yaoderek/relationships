import { useState } from "react";
import { fetchOverviewSeries, fetchYou } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import CalendarHeatmap from "../components/CalendarHeatmap";
import Heatmap from "../components/Heatmap";
import Spine from "../components/Spine";
import { Stat, statGridStyle } from "../components/StatGrid";
import TimeSeries from "../components/TimeSeries";
import YouHotDays from "../components/YouHotDays";
import { useFetch } from "../lib/useFetch";

const SECTIONS = [
  { id: "ov-stats", label: "Your stats" },
  { id: "ov-volume", label: "Message volume" },
  { id: "ov-heatmap", label: "When you text" },
  { id: "ov-busiest", label: "Busiest days" },
];

export default function Overview() {
  const [bucket, setBucket] = useState<Bucket>("month");
  const series = useFetch(() => fetchOverviewSeries(bucket), [bucket]);
  const stats = useFetch(fetchYou, []);

  if (!stats) return <p>Loading…</p>;
  const fav = (xs: { emoji?: string; kind?: string; count: number }[]) =>
    xs.length ? `${xs[0].emoji ?? xs[0].kind} ×${xs[0].count}` : "—";

  return (
    <>
      <Spine sections={SECTIONS} />
      <h1 id="ov-stats">Overview</h1>
      <p style={{ fontSize: 13, opacity: 0.7, marginTop: -8 }}>
        Your texting style, across every chat.
      </p>
      <div style={statGridStyle}>
        <Stat label="Messages sent" value={stats.sent_total.toLocaleString()} />
        <Stat label="Avg message length"
              value={`${Math.round(stats.avg_chars ?? 0)} chars`} />
        <Stat label="Double texts" value={stats.double_texts.toLocaleString()} />
        <Stat label="Favorite emoji" value={fav(stats.top_emojis)} />
        <Stat label="Go-to reaction" value={fav(stats.reactions_given)} />
        {stats.busiest_day && (
          <Stat label="Busiest day ever"
                value={`${stats.busiest_day.date} (${stats.busiest_day.count})`} />
        )}
      </div>

      <h2 id="ov-volume">Message volume</h2>
      <BucketPicker value={bucket} onChange={setBucket} />
      {series && <TimeSeries data={series} />}

      <h2 id="ov-heatmap">When you text</h2>
      <Heatmap cells={stats.heatmap} />
      <CalendarHeatmap />

      <h2 id="ov-busiest">Busiest days ever</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Click a day to see what was going on.
      </p>
      <YouHotDays />
    </>
  );
}
