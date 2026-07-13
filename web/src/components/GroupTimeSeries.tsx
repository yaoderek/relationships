import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { GroupSeriesPoint } from "../api";

export default function GroupTimeSeries({ data }: { data: GroupSeriesPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
        <YAxis tickLine={false} axisLine={false} width={44} />
        <Tooltip />
        <Legend />
        <Line dataKey="total" name="All messages" dot={false}
              stroke="#5B8FF9" strokeWidth={2} />
        <Line dataKey="mine" name="Mine" dot={false}
              stroke="#61DDAA" strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
