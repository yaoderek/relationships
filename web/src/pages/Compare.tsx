import { useState } from "react";
import { fetchCompare, fetchPersons } from "../api";
import type { Bucket } from "../api";
import ArcsChart from "../components/ArcsChart";
import BucketPicker from "../components/BucketPicker";
import Spine from "../components/Spine";
import { useFetch } from "../lib/useFetch";

export default function Compare() {
  const persons = useFetch(fetchPersons, []);
  const [selected, setSelected] = useState<number[]>([]);
  const [bucket, setBucket] = useState<Bucket>("month");
  const data = useFetch(
    () => selected.length ? fetchCompare(selected, bucket) : Promise.resolve([]),
    [selected.join(","), bucket],
  );
  const toggle = (id: number) =>
    setSelected((s) => s.includes(id) ? s.filter((x) => x !== id)
                       : s.length < 5 ? [...s, id] : s);
  return (
    <>
      <Spine sections={[{ id: "compare-top", label: "Compare" }]} />
      <h1 id="compare-top">Compare (pick up to 5)</h1>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
        {(persons ?? []).slice(0, 100).map((p) => (
          <button key={p.person_id} onClick={() => toggle(p.person_id)}
                  style={{ fontWeight: selected.includes(p.person_id) ? 700 : 400 }}>
            {p.display_name}
          </button>
        ))}
      </div>
      <BucketPicker value={bucket} onChange={setBucket} />
      {data && data.length > 0 && <ArcsChart data={data} />}
    </>
  );
}
