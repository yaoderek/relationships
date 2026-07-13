import { useState } from "react";
import { fetchCompare, fetchOverviewSeries, fetchPersons } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import ArcsChart from "../components/ArcsChart";
import Spine from "../components/Spine";
import TimeSeries from "../components/TimeSeries";
import { useFetch } from "../lib/useFetch";

export default function Overview() {
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
      <Spine sections={[
        { id: "ov-volume", label: "Message volume" },
        { id: "ov-arcs", label: "Relationship arcs" },
      ]} />
      <h1 id="ov-volume">Overview</h1>
      <BucketPicker value={bucket} onChange={setBucket} />
      {series && <TimeSeries data={series} />}
      <h2 id="ov-arcs">Relationship arcs — top 10 people, monthly</h2>
      {arcs && arcs.length > 0 && <ArcsChart data={arcs} />}
    </>
  );
}
