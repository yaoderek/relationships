import { useState } from "react";
import { useParams } from "react-router-dom";
import { fetchPersonHeatmap, fetchPersonSeries, fetchPersonStats } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import Heatmap from "../components/Heatmap";
import HotDays from "../components/HotDays";
import StatGrid from "../components/StatGrid";
import TimeSeries from "../components/TimeSeries";
import { useFetch } from "../lib/useFetch";

export default function Person() {
  const pid = Number(useParams().id);
  const [bucket, setBucket] = useState<Bucket>("week");
  const [includeGroups, setIncludeGroups] = useState(false);
  const stats = useFetch(() => fetchPersonStats(pid), [pid]);
  const series = useFetch(() => fetchPersonSeries(pid, bucket, includeGroups),
                          [pid, bucket, includeGroups]);
  const heatmap = useFetch(() => fetchPersonHeatmap(pid), [pid]);
  if (!stats) return <p>Loading…</p>;
  return (
    <>
      <h1>{stats.display_name}</h1>
      <StatGrid stats={stats} />
      <BucketPicker value={bucket} onChange={setBucket} />
      <label style={{ marginLeft: 12, fontSize: 13 }}>
        <input type="checkbox" checked={includeGroups}
               onChange={(e) => setIncludeGroups(e.target.checked)} />
        {" "}include group messages
      </label>
      {series && <TimeSeries data={series} />}
      <h2>When you talk</h2>
      {heatmap && <Heatmap cells={heatmap} />}
      <h2>Vernacular</h2>
      <WordChips label="Them" words={stats.top_words_them} />
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
      <span style={{ fontSize: 12, opacity: 0.6, width: 36 }}>{label}</span>
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
