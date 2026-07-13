import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchGroupHeatmap, fetchGroupSeries, fetchGroupStats } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import GroupTimeSeries from "../components/GroupTimeSeries";
import Heatmap from "../components/Heatmap";
import Leaderboard from "../components/Leaderboard";
import Spine from "../components/Spine";
import { Stat, statGridStyle } from "../components/StatGrid";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

export default function GroupDetail() {
  const gid = Number(useParams().id);
  const navigate = useNavigate();
  const [bucket, setBucket] = useState<Bucket>("week");
  const stats = useFetch(() => fetchGroupStats(gid), [gid]);
  const series = useFetch(() => fetchGroupSeries(gid, bucket), [gid, bucket]);
  const heatmap = useFetch(() => fetchGroupHeatmap(gid), [gid]);
  if (!stats) return <p>Loading…</p>;
  return (
    <>
      <Spine sections={[
        { id: "g-stats", label: "Stats" },
        { id: "g-voice", label: "Share of voice" },
        { id: "g-heatmap", label: "When it's active" },
      ]} />
      <h1 id="g-stats">{stats.name}</h1>
      <div style={statGridStyle}>
        <Stat label="Your share" value={fmtPercent(stats.my_share)} />
        <Stat label="Sessions" value={stats.session_count.toLocaleString()} />
        {stats.busiest_day && (
          <Stat label="Busiest day"
                value={`${stats.busiest_day.date} (${stats.busiest_day.count})`} />
        )}
      </div>
      <BucketPicker value={bucket} onChange={setBucket} />
      {series && <GroupTimeSeries data={series} />}
      <h2 id="g-voice">Share of voice</h2>
      <Leaderboard
        rows={stats.members.map((m) => ({
          key: m.person_id ?? 0, name: m.display_name, total: m.count,
          subtitle: `${fmtPercent(m.share)} · ${m.tapbacks_received} tapbacks · `
            + `avg ${Math.round(m.avg_chars ?? 0)} chars`,
        }))}
        onSelect={(pid) => navigate(`/groups/${gid}/members/${pid}`)}
      />
      <h2 id="g-heatmap">When it's active</h2>
      {heatmap && <Heatmap cells={heatmap} />}
    </>
  );
}
