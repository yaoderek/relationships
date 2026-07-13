import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchGroupMemberSeries, fetchGroupMemberStats, fetchGroupStats } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import { Stat, statGridStyle } from "../components/StatGrid";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

export default function GroupMember() {
  const params = useParams();
  const gid = Number(params.id);
  const pid = Number(params.pid);
  const [bucket, setBucket] = useState<Bucket>("week");
  const group = useFetch(() => fetchGroupStats(gid), [gid]);
  const stats = useFetch(() => fetchGroupMemberStats(gid, pid), [gid, pid]);
  const series = useFetch(() => fetchGroupMemberSeries(gid, pid, bucket),
                          [gid, pid, bucket]);
  if (!stats) return <p>Loading…</p>;
  const fav = (xs: { word?: string; emoji?: string; kind?: string; count: number }[]) =>
    xs.length ? `${xs[0].word ?? xs[0].emoji ?? xs[0].kind} ×${xs[0].count}` : "—";
  return (
    <>
      <p style={{ fontSize: 13, opacity: 0.7 }}>
        <Link to={`/groups/${gid}`}>← {group?.name ?? "group"}</Link>
      </p>
      <h1>{stats.display_name}</h1>
      <div style={statGridStyle}>
        <Stat label="Messages in this chat" value={stats.count.toLocaleString()} />
        <Stat label="Share of voice" value={fmtPercent(stats.share)} />
        <Stat label="Avg message length"
              value={`${Math.round(stats.avg_chars ?? 0)} chars`} />
        <Stat label="Left the gc on read"
              value={`${stats.sessions_ghosted.toLocaleString()} of ${stats.sessions_total.toLocaleString()} convos`} />
        <Stat label="Convos they killed"
              value={stats.sessions_ended.toLocaleString()} />
        <Stat label="Most common word" value={fav(stats.top_words)} />
        <Stat label="Most common reaction" value={fav(stats.top_reactions_given)} />
        <Stat label="Favorite emoji" value={fav(stats.top_emojis)} />
        <Stat label="Tapbacks received"
              value={stats.tapbacks_received.toLocaleString()} />
      </div>
      <BucketPicker value={bucket} onChange={setBucket} />
      {series && (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={series}>
            <CartesianGrid strokeOpacity={0.15} vertical={false} />
            <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
            <YAxis tickLine={false} axisLine={false} width={44} />
            <Tooltip />
            <Line dataKey="count" name="Messages" dot={false}
                  stroke="#5B8FF9" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      )}
      {stats.top_words.length > 1 && (
        <>
          <h2>Top words</h2>
          <p>
            {stats.top_words.map((w) => `${w.word} (${w.count})`).join(" · ")}
          </p>
        </>
      )}
    </>
  );
}
