import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesPoint } from "../api";

export default function TimeSeries({ data }: { data: SeriesPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
        <YAxis tickLine={false} axisLine={false} width={44} />
        <Tooltip />
        <Area dataKey="received" stackId="1" name="Received"
              fill="#5B8FF9" stroke="#5B8FF9" fillOpacity={0.7} />
        <Area dataKey="sent" stackId="1" name="Sent"
              fill="#61DDAA" stroke="#61DDAA" fillOpacity={0.7} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
