import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCompare, fetchOverviewSeries, fetchPersons } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import ArcsChart from "../components/ArcsChart";
import Leaderboard from "../components/Leaderboard";
import TimeSeries from "../components/TimeSeries";
import { useFetch } from "../lib/useFetch";

export default function Overview() {
  const navigate = useNavigate();
  const [bucket, setBucket] = useState<Bucket>("month");
  const series = useFetch(() => fetchOverviewSeries(bucket), [bucket]);
  const persons = useFetch(fetchPersons, []);
  const topIds = (persons ?? []).slice(0, 10).map((p) => p.person_id).join(",");
  const arcs = useFetch(
    () => topIds ? fetchCompare(topIds.split(",").map(Number), "month")
                 : Promise.resolve([]),
    [topIds],
  );
  return (
    <>
      <h1>Overview</h1>
      <BucketPicker value={bucket} onChange={setBucket} />
      {series && <TimeSeries data={series} />}
      <h2>Relationship arcs — top 10 people, monthly</h2>
      {arcs && arcs.length > 0 && <ArcsChart data={arcs} />}
      <h2>Top people (1:1 messages)</h2>
      {persons && (
        <Leaderboard
          rows={persons.slice(0, 25).map((p) => ({
            key: p.person_id, name: p.display_name, total: p.total,
            subtitle: `${p.first_ts.slice(0, 10)} → ${p.last_ts.slice(0, 10)}`,
          }))}
          onSelect={(id) => navigate(`/person/${id}`)}
        />
      )}
    </>
  );
}
