import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CompareSeries } from "../api";

const PALETTE = ["#5B8FF9", "#61DDAA", "#F6BD16", "#7262FD", "#78D3F8",
                 "#9661BC", "#F6903D", "#008685", "#F08BB4", "#65789B"];

export function mergeSeries(all: CompareSeries[]): Record<string, unknown>[] {
  const buckets = new Map<string, Record<string, unknown>>();
  for (const person of all) {
    for (const pt of person.series) {
      const row = buckets.get(pt.bucket) ?? { bucket: pt.bucket };
      row[person.display_name] = pt.total;
      buckets.set(pt.bucket, row);
    }
  }
  return [...buckets.values()]
    .sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)));
}

export default function ArcsChart({ data }: { data: CompareSeries[] }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={mergeSeries(data)}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
        <YAxis tickLine={false} axisLine={false} width={44} />
        <Tooltip />
        <Legend />
        {data.map((p, i) => (
          <Line key={p.person_id} dataKey={p.display_name} dot={false}
                stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
