import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { fetchDrift, fetchLanguageSearch, fetchSignature, fetchSignatureScopes, fetchTopics, fetchVoice } from "../api";
import type { SearchHit, VoicePoint } from "../api";
import Dropdown from "../components/Dropdown";
import Leaderboard from "../components/Leaderboard";
import Spine from "../components/Spine";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

const SECTIONS = [
  { id: "lang-signature", label: "Signature phrases" },
  { id: "lang-topics", label: "Topics" },
  { id: "lang-voice", label: "Voice map" },
  { id: "lang-drift", label: "Style drift" },
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
  const topics = useFetch(fetchTopics, []);
  const voice = useFetch(fetchVoice, []);
  const drift = useFetch(fetchDrift, []);
  const scopes = useFetch(fetchSignatureScopes, []);
  const [scope, setScope] = useState("you");
  const signature = useFetch(() => fetchSignature(scope), [scope]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [voiceView, setVoiceView] = useState("map");
  const [voiceQuery, setVoiceQuery] = useState("");

  const voiceMatch = voiceQuery.trim()
    ? (voice ?? []).find((v) =>
        v.name.toLowerCase().includes(voiceQuery.trim().toLowerCase())) ?? null
    : null;

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
      <h1 id="lang-signature">Language</h1>
      <p style={{ fontSize: 13, opacity: 0.7, marginTop: -8 }}>
        What your words say about you — powered by embeddings of every message.
        If everything below is empty, run{" "}
        <code>uv run python scripts/language.py</code> and reload.
      </p>

      <h2>Signature phrases</h2>
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

      <h2 id="lang-topics">What you talk about</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Every message clustered by meaning, with the people who dominate each
        topic.
      </p>
      <div style={{ display: "grid", gap: 10,
                    gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
        {(topics ?? []).map((t, i) => (
          <div key={t.cluster_id}
               style={{ padding: "12px 14px", borderRadius: 10,
                        border: "1px solid rgba(128,128,128,0.25)" }}>
            <div style={{ display: "flex", justifyContent: "space-between",
                          gap: 8 }}>
              <span style={{ fontWeight: 650 }}>{t.label}</span>
              <span style={{ opacity: 0.6, fontSize: 13 }}>
                {fmtPercent(t.share)}
              </span>
            </div>
            <div style={{ background: PALETTE[i % PALETTE.length], height: 6,
                          borderRadius: 3, margin: "8px 0",
                          width: `${Math.max(4, t.share * 100 * 3)}%` }} />
            <div style={{ fontSize: 12, opacity: 0.7 }}>
              {t.people.map((p) =>
                `${p.name.split(" ")[0]} ${fmtPercent(p.share)}`).join(" · ")}
            </div>
          </div>
        ))}
      </div>

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

      <h2 id="lang-drift">How your voice drifts</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: -6 }}>
        Monthly distance between your texting style and the previous month
        (drift) and your all-time average voice (novelty).
      </p>
      {drift && drift.length > 0 && (
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={drift} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeOpacity={0.15} vertical={false} />
            <XAxis dataKey="month" tickLine={false} minTickGap={40} />
            <YAxis tickLine={false} axisLine={false} width={52}
                   tickFormatter={(v: number) => v.toFixed(2)} />
            <Tooltip formatter={(v) => Number(v).toFixed(3)} />
            <Area type="monotone" dataKey="novelty" name="Novelty vs all-time"
                  stroke="#5B8FF9" fill="#5B8FF9" fillOpacity={0.2}
                  strokeWidth={2} connectNulls />
            <Area type="monotone" dataKey="drift" name="Month-to-month drift"
                  stroke="#61DDAA" fill="#61DDAA" fillOpacity={0.2}
                  strokeWidth={2} connectNulls />
          </AreaChart>
        </ResponsiveContainer>
      )}

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
