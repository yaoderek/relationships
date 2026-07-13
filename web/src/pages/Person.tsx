import { useState } from "react";
import { useParams } from "react-router-dom";
import { fetchPersonHeatmap, fetchPersonSeries, fetchPersonStats } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import Heatmap from "../components/Heatmap";
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
    </>
  );
}
