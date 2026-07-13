import { fetchYou } from "../api";
import Heatmap from "../components/Heatmap";
import { Stat, statGridStyle } from "../components/StatGrid";
import { useFetch } from "../lib/useFetch";

export default function You() {
  const stats = useFetch(fetchYou, []);
  if (!stats) return <p>Loading…</p>;
  const fav = (xs: { emoji?: string; kind?: string; count: number }[]) =>
    xs.length ? `${xs[0].emoji ?? xs[0].kind} ×${xs[0].count}` : "—";
  return (
    <>
      <h1>You</h1>
      <p style={{ fontSize: 13, opacity: 0.7, marginTop: -8 }}>
        Your texting style, across every chat.
      </p>
      <div style={statGridStyle}>
        <Stat label="Messages sent" value={stats.sent_total.toLocaleString()} />
        <Stat label="DMs / groups"
              value={`${stats.sent_in_dms.toLocaleString()} / ${stats.sent_in_groups.toLocaleString()}`} />
        <Stat label="Avg message length"
              value={`${Math.round(stats.avg_chars ?? 0)} chars`} />
        <Stat label="Texts per reply"
              value={stats.avg_texts_per_reply == null ? "—"
                     : stats.avg_texts_per_reply.toFixed(1)} />
        <Stat label="Double texts" value={stats.double_texts.toLocaleString()} />
        <Stat label="Emojis used" value={stats.emoji_total.toLocaleString()} />
        <Stat label="Favorite emoji" value={fav(stats.top_emojis)} />
        <Stat label="Go-to reaction" value={fav(stats.reactions_given)} />
        {stats.busiest_day && (
          <Stat label="Busiest day ever"
                value={`${stats.busiest_day.date} (${stats.busiest_day.count})`} />
        )}
      </div>
      <h2>Your vernacular</h2>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {stats.top_words.map((w) => (
          <span key={w.word}
                style={{ fontSize: 13, padding: "3px 10px", borderRadius: 999,
                         border: "1px solid rgba(128,128,128,0.3)" }}>
            {w.word} <span style={{ opacity: 0.55 }}>×{w.count}</span>
          </span>
        ))}
      </div>
      {stats.top_sentences.length > 0 && (
        <>
          <h2>Your catchphrases</h2>
          {stats.top_sentences.map((s) => (
            <div key={s.text}
                 style={{ display: "flex", justifyContent: "space-between",
                          gap: 12, padding: "7px 10px", fontSize: 14,
                          borderBottom: "1px solid rgba(128,128,128,0.15)" }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis",
                             whiteSpace: "nowrap" }}>“{s.text}”</span>
              <span style={{ opacity: 0.55, fontVariantNumeric: "tabular-nums" }}>
                ×{s.count}
              </span>
            </div>
          ))}
        </>
      )}
      <h2>When you text</h2>
      <Heatmap cells={stats.heatmap} />
    </>
  );
}
