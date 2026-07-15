import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { fetchCatchphrasesTimeline, fetchLanguageSearch, fetchSignature, fetchSignatureScopes, fetchVoice, fetchWordContext, fetchYou } from "../api";
import type { SearchHit, SentenceCount, VoicePoint } from "../api";
import Dropdown from "../components/Dropdown";
import Leaderboard from "../components/Leaderboard";
import SessionMap from "../components/SessionMap";
import Spine from "../components/Spine";
import { useFetch } from "../lib/useFetch";

const SECTIONS = [
  { id: "lang-topicmap", label: "Topic map" },
  { id: "lang-vernacular", label: "Vernacular" },
  { id: "lang-signature", label: "Signature phrases" },
  { id: "lang-evolution", label: "Catchphrases by year" },
  { id: "lang-catchphrases", label: "All-time catchphrases" },
  { id: "lang-voice", label: "Voice map" },
  { id: "lang-search", label: "Semantic search" },
];

const PALETTE = ["#5B8FF9", "#61DDAA", "#F6BD16", "#7262FD", "#78D3F8",
                 "#9661BC", "#F6903D", "#008685", "#F08BB4", "#65789B",
                 "#6DC8EC", "#D3CBF6", "#DECFEA", "#FF9D4D"];

const VOICE_VIEWS = [
  { value: "map", label: "Voice map (2D)" },
  { value: "divergence", label: "Code-switching by person" },
  { value: "mirroring", label: "Mirroring by person" },
];

export default function Language() {
  const navigate = useNavigate();
  const stats = useFetch(fetchYou, []);
  const evolution = useFetch(fetchCatchphrasesTimeline, []);
  const voice = useFetch(fetchVoice, []);
  const scopes = useFetch(fetchSignatureScopes, []);
  const [scope, setScope] = useState("you");
  const signature = useFetch(() => fetchSignature(scope), [scope]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [voiceView, setVoiceView] = useState("map");
  const [voiceQuery, setVoiceQuery] = useState("");
  const [word, setWord] = useState<string | null>(null);
  const [sentences, setSentences] = useState<SentenceCount[] | null>(null);

  const voiceMatch = voiceQuery.trim()
    ? (voice ?? []).find((v) =>
        v.name.toLowerCase().includes(voiceQuery.trim().toLowerCase())) ?? null
    : null;

  const pickWord = (w: string) => {
    if (word === w) { setWord(null); setSentences(null); return; }
    setWord(w);
    setSentences(null);
    fetchWordContext(w).then(setSentences).catch(() => setSentences([]));
  };

  const search = () => {
    if (!query.trim() || searching) return;
    setSearching(true);
    setHits(null);
    fetchLanguageSearch(query.trim())
      .then(setHits)
      .catch(() => setHits([]))
      .finally(() => setSearching(false));
  };

  const maxScore = Math.max(1, ...(signature?.phrases ?? []).map((p) => p.score));
  const scopeOptions = [
    { value: "you", label: "You (vs everyone)" },
    ...(scopes ?? [])
      .filter((s) => s.scope !== "you")
      .map((s) => ({
        value: s.scope,
        label: s.scope.startsWith("year:") ? `Year ${s.label}` : `With ${s.label}`,
      })),
  ];

  return (
    <>
      <Spine sections={SECTIONS} />
      <h1 id="lang-topicmap">Language</h1>
      <p style={{ fontSize: 13, opacity: 0.7, marginTop: -8 }}>
        What your words say about you — powered by embeddings of every message.
        If everything below is empty, run{" "}
        <code>uv run python scripts/language.py</code> and reload.
      </p>

      <h2>Topic map</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Every substantial conversation, embedded as a whole transcript and
        grouped into topic communities. Slide resolution to split broad
        domains into niches, scrub years to watch topics come and go.
      </p>
      <SessionMap />

      <h2 id="lang-vernacular">Your vernacular</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Click a word to see how you actually use it.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {(stats?.top_words ?? []).map((w) => (
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

      <h2 id="lang-signature">Signature phrases</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Phrases statistically over-represented in a scope versus everything
        else — not just frequent, but *distinctively* yours.
      </p>
      <div style={{ margin: "8px 0 12px" }}>
        <Dropdown value={scope} options={scopeOptions} onChange={setScope} />
      </div>
      {signature?.phrases.map((p) => (
        <div key={p.phrase}
             style={{ display: "flex", alignItems: "center", gap: 12,
                      padding: "5px 8px", fontSize: 14 }}>
          <span style={{ width: 220, overflow: "hidden",
                         textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            “{p.phrase}”
          </span>
          <span style={{ flex: 1 }}>
            <span style={{ display: "block", background: "#5B8FF9", height: 7,
                           borderRadius: 4,
                           width: `${(p.score / maxScore) * 100}%`,
                           transition: "width .5s cubic-bezier(.22,1,.36,1)" }} />
          </span>
          <span style={{ fontSize: 12, opacity: 0.6, width: 60,
                         textAlign: "right",
                         fontVariantNumeric: "tabular-nums" }}>
            ×{p.count}
          </span>
        </div>
      ))}

      <h2 id="lang-evolution">Your catchphrases, year by year</h2>
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

      {(stats?.top_sentences.length ?? 0) > 0 && (
        <>
          <h2 id="lang-catchphrases">All-time catchphrases</h2>
          {stats!.top_sentences.map((s) => (
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

      <h2 id="lang-voice">Voice</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Mirroring = how alike you two sound. Code-switching = how differently
        you talk to them compared to everyone else.
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 8,
                    flexWrap: "wrap", margin: "8px 0 12px" }}>
        <Dropdown value={voiceView} options={VOICE_VIEWS}
                  onChange={setVoiceView} />
        <input value={voiceQuery}
               onChange={(e) => setVoiceQuery(e.target.value)}
               placeholder="find a person…"
               style={{ padding: "6px 12px", fontSize: 13, font: "inherit",
                        color: "inherit", background: "transparent",
                        borderRadius: 8, width: 180,
                        border: "1px solid rgba(128,128,128,0.35)" }} />
        {voiceQuery.trim() && !voiceMatch && (
          <span style={{ fontSize: 12, opacity: 0.6 }}>no match</span>
        )}
      </div>
      {voiceMatch && (
        <div style={{ display: "inline-flex", gap: 16, padding: "8px 14px",
                      marginBottom: 10, borderRadius: 8, fontSize: 13,
                      border: "1px solid rgba(91,143,249,0.5)",
                      background: "rgba(91,143,249,0.10)" }}>
          <strong>{voiceMatch.name}</strong>
          <span>mirroring {voiceMatch.mirroring.toFixed(3)}</span>
          <span>code-switching {voiceMatch.divergence.toFixed(3)}</span>
          <span style={{ opacity: 0.6 }}>
            {voiceMatch.msgs.toLocaleString()} msgs
          </span>
        </div>
      )}
      {voice && voice.length > 0 && voiceView === "map" && (
        <>
          <div style={{ fontSize: 11, opacity: 0.55, marginBottom: 2 }}>
            ↑ code-switching
          </div>
          <ResponsiveContainer width="100%" height={380}>
            <ScatterChart margin={{ top: 16, right: 28, bottom: 8, left: 0 }}>
              <CartesianGrid strokeOpacity={0.15} />
              <XAxis type="number" dataKey="mirroring" name="mirroring"
                     domain={["auto", "auto"]} tickLine={false} tickMargin={8}
                     tickFormatter={(v: number) => v.toFixed(3)}
                     style={{ fontSize: 11 }} />
              <YAxis type="number" dataKey="divergence" name="code-switching"
                     domain={["auto", "auto"]} tickLine={false} axisLine={false}
                     width={58} tickMargin={6}
                     tickFormatter={(v: number) => v.toFixed(3)}
                     style={{ fontSize: 11 }} />
              <ZAxis dataKey="msgs" range={[140, 1100]} />
              <Tooltip content={({ payload }) => {
                const p = payload?.[0]?.payload as VoicePoint | undefined;
                if (!p) return null;
                return (
                  <div style={{ background: "Canvas", padding: "6px 10px",
                                border: "1px solid rgba(128,128,128,0.3)",
                                borderRadius: 8, fontSize: 12 }}>
                    <strong>{p.name}</strong><br />
                    mirroring {p.mirroring.toFixed(3)}<br />
                    code-switching {p.divergence.toFixed(3)}
                  </div>
                );
              }} />
              <Scatter data={voice}>
                {voice.map((v, i) => {
                  const highlighted = voiceMatch?.person_id === v.person_id;
                  return (
                    <Cell key={v.person_id}
                          fill={PALETTE[i % PALETTE.length]}
                          fillOpacity={voiceMatch ? (highlighted ? 1 : 0.2)
                                                  : 0.8}
                          stroke={highlighted ? "#fff" : "none"}
                          strokeWidth={highlighted ? 2.5 : 0} />
                  );
                })}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <div style={{ fontSize: 11, opacity: 0.55, textAlign: "right" }}>
            mirroring →
          </div>
        </>
      )}
      {voice && voice.length > 0 && voiceView !== "map" && (() => {
        const metric = voiceView as "divergence" | "mirroring";
        const values = voice.map((v) => v[metric]);
        const min = Math.min(...values);
        const range = Math.max(1e-9, Math.max(...values) - min);
        const rows = [...voice]
          .sort((a, b) => b[metric] - a[metric])
          .map((v) => ({
            key: v.person_id, name: v.name,
            total: (v[metric] - min) / range * 100 + 5,
            display: v[metric].toFixed(3),
            subtitle: `${v.msgs.toLocaleString()} msgs`,
          }));
        return <Leaderboard rows={rows} highlightKey={voiceMatch?.person_id}
                            onSelect={(id) => navigate(`/person/${id}`)} />;
      })()}

      <h2 id="lang-search">Semantic search</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Search everything ever said by meaning, not keywords.
      </p>
      <div style={{ display: "flex", gap: 8, margin: "8px 0 12px" }}>
        <input value={query} onChange={(e) => setQuery(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && search()}
               placeholder="e.g. apartment hunting stress"
               style={{ flex: 1, padding: "8px 12px", fontSize: 14,
                        font: "inherit", color: "inherit",
                        background: "transparent", borderRadius: 8,
                        border: "1px solid rgba(128,128,128,0.35)" }} />
        <button onClick={search}
                style={{ padding: "8px 18px", fontSize: 14, font: "inherit",
                         color: "inherit", background: "rgba(91,143,249,0.18)",
                         border: "1px solid rgba(91,143,249,0.5)",
                         borderRadius: 8 }}>
          {searching ? "…" : "Search"}
        </button>
      </div>
      {hits?.length === 0 && !searching && (
        <p style={{ opacity: 0.6, fontSize: 13 }}>No results.</p>
      )}
      {hits?.map((h) => (
        <div key={h.text}
             style={{ display: "flex", justifyContent: "space-between",
                      gap: 12, padding: "7px 10px", fontSize: 14,
                      borderBottom: "1px solid rgba(128,128,128,0.15)" }}>
          <span>“{h.text}”</span>
          <span style={{ opacity: 0.55, fontSize: 12, whiteSpace: "nowrap",
                         fontVariantNumeric: "tabular-nums" }}>
            ×{h.total}{h.mine > 0 ? ` (you ×${h.mine})` : ""}
          </span>
        </div>
      ))}
    </>
  );
}
