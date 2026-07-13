import { useState } from "react";
import { fetchCatchphrasesTimeline, fetchWordContext, fetchYou, fetchYouHotDays } from "../api";
import type { SentenceCount } from "../api";
import BlobField from "../components/BlobField";
import Heatmap from "../components/Heatmap";
import Spine from "../components/Spine";
import { Stat, statGridStyle } from "../components/StatGrid";
import { useFetch } from "../lib/useFetch";

const SECTIONS = [
  { id: "you-stats", label: "Your stats" },
  { id: "you-universe", label: "Universe" },
  { id: "you-vernacular", label: "Vernacular" },
  { id: "you-evolution", label: "Catchphrases by year" },
  { id: "you-catchphrases", label: "All-time catchphrases" },
  { id: "you-heatmap", label: "When you text" },
  { id: "you-busiest", label: "Busiest days" },
];

export default function You() {
  const stats = useFetch(fetchYou, []);
  const evolution = useFetch(fetchCatchphrasesTimeline, []);
  const hotDays = useFetch(fetchYouHotDays, []);
  const [word, setWord] = useState<string | null>(null);
  const [sentences, setSentences] = useState<SentenceCount[] | null>(null);

  if (!stats) return <p>Loading…</p>;
  const fav = (xs: { emoji?: string; kind?: string; count: number }[]) =>
    xs.length ? `${xs[0].emoji ?? xs[0].kind} ×${xs[0].count}` : "—";

  const pickWord = (w: string) => {
    if (word === w) { setWord(null); setSentences(null); return; }
    setWord(w);
    setSentences(null);
    fetchWordContext(w).then(setSentences).catch(() => setSentences([]));
  };

  const maxHot = Math.max(1, ...(hotDays ?? []).map((d) => d.count));

  return (
    <>
      <Spine sections={SECTIONS} />
      <h1 id="you-stats">You</h1>
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

      <h2 id="you-universe">Your universe</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Each blob is a person, sized by how much you texted around that moment.
        Drag the timeline or press play.
      </p>
      <BlobField />

      <h2 id="you-vernacular">Your vernacular</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Click a word to see how you actually use it.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {stats.top_words.map((w) => (
          <button key={w.word} onClick={() => pickWord(w.word)}
                  style={{ fontSize: 13, padding: "3px 10px", borderRadius: 999,
                           font: "inherit", color: "inherit",
                           background: word === w.word
                             ? "rgba(91,143,249,0.22)" : "transparent",
                           border: word === w.word
                             ? "1px solid rgba(91,143,249,0.7)"
                             : "1px solid rgba(128,128,128,0.3)",
                           transition: "background .18s ease, border-color .18s ease" }}>
            {w.word} <span style={{ opacity: 0.55 }}>×{w.count}</span>
          </button>
        ))}
      </div>
      <div style={{ display: "grid",
                    gridTemplateRows: word ? "1fr" : "0fr",
                    transition: "grid-template-rows .3s ease" }}>
        <div style={{ overflow: "hidden" }}>
          <div style={{ margin: "12px 0 4px", padding: "10px 14px",
                        border: "1px solid rgba(128,128,128,0.25)",
                        borderRadius: 8, fontSize: 14 }}>
            {word && !sentences && <span style={{ opacity: 0.6 }}>Looking…</span>}
            {sentences?.length === 0 && (
              <span style={{ opacity: 0.6 }}>No full sentences found.</span>
            )}
            {sentences?.map((s) => (
              <div key={s.text}
                   style={{ display: "flex", justifyContent: "space-between",
                            gap: 12, padding: "5px 0" }}>
                <span>“{s.text}”</span>
                <span style={{ opacity: 0.55,
                               fontVariantNumeric: "tabular-nums" }}>
                  ×{s.count}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <h2 id="you-evolution">Your catchphrases, year by year</h2>
      <div style={{ display: "flex", gap: 10, overflowX: "auto",
                    paddingBottom: 8 }}>
        {(evolution ?? []).map((y) => (
          <div key={y.bucket}
               style={{ minWidth: 220, maxWidth: 260, padding: "10px 12px",
                        border: "1px solid rgba(128,128,128,0.25)",
                        borderRadius: 10 }}>
            <div style={{ fontWeight: 650, marginBottom: 6 }}>{y.bucket}</div>
            {y.sentences.map((s, i) => (
              <div key={s.text}
                   style={{ display: "flex", justifyContent: "space-between",
                            gap: 8, fontSize: 13, padding: "3px 0",
                            opacity: 1 - i * 0.1 }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis",
                               whiteSpace: "nowrap" }}>“{s.text}”</span>
                <span style={{ opacity: 0.55,
                               fontVariantNumeric: "tabular-nums" }}>
                  ×{s.count}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {stats.top_sentences.length > 0 && (
        <>
          <h2 id="you-catchphrases">All-time catchphrases</h2>
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

      <h2 id="you-heatmap">When you text</h2>
      <Heatmap cells={stats.heatmap} />

      <h2 id="you-busiest">Busiest days ever</h2>
      {(hotDays ?? []).map((d) => (
        <div key={d.date}
             style={{ display: "flex", alignItems: "center", gap: 12,
                      padding: "7px 8px", fontSize: 14,
                      borderBottom: "1px solid rgba(128,128,128,0.15)" }}>
          <span style={{ fontVariantNumeric: "tabular-nums", width: 90 }}>
            {d.date}
          </span>
          <span style={{ flex: 1 }}>
            <span style={{ display: "block", background: "#5B8FF9", height: 7,
                           borderRadius: 4,
                           width: `${(d.count / maxHot) * 100}%` }} />
          </span>
          <span style={{ fontSize: 12, opacity: 0.65, width: 220,
                         textAlign: "right" }}>
            {d.count.toLocaleString()} msgs · {d.sent.toLocaleString()} sent
            {d.top_contact ? ` · mostly ${d.top_contact}` : ""}
          </span>
        </div>
      ))}
    </>
  );
}
