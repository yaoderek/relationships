import { useEffect, useMemo, useRef, useState } from "react";
import { fetchSemanticMap, fetchSemanticMapLayouts } from "../api";
import type { SemanticCommunity } from "../api";
import { useFetch } from "../lib/useFetch";

type Community = SemanticCommunity;

const W = 880;
const H = 560;
const FOV = 4.2;
const GAMMAS = [0.5, 1, 2, 4];
const AUTOROTATE_AFTER_MS = 3000;
// Keep in sync with UMAP_*_SWEEP in scripts/semantic.py
const UMAP_NEIGHBORS_SWEEP = [15, 20, 30, 40, 50];
const UMAP_MIN_DIST_SWEEP = [0.0, 0.05, 0.1, 0.2, 0.5];
const UMAP_DEFAULT_NEIGHBORS = 30;
const UMAP_DEFAULT_MIN_DIST = 0.05;

function layoutKey(n_neighbors: number, min_dist: number): string {
  return `${n_neighbors}:${min_dist}`;
}

const LAYOUT_TWEEN_MS = 900;

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

const PALETTE = [
  "#5b8ff9", "#61ddaa", "#f6bd16", "#7262fd", "#78d3f8", "#9661bc",
  "#f6903d", "#008685", "#f08bb4", "#65789b", "#bedd7a", "#d64541",
  "#4a90d9", "#c0a16b", "#6dc8ec", "#ff9d4d", "#269a99", "#ff99c3",
];

type P = {
  wx: number; wy: number; wz: number;  // centered 3D world coords
  c: [number, number, number, number];
  year: number;
  contact: string; date: string; n_msgs: number; snippet: string;
};

type Msg = { is_from_me: boolean; sender: string | null; text: string };

// Examples are stored as "Me: … · Daisy: … · Them: …" flattened transcripts
// (first names for known senders, "Them" for unresolved ones).
function parseExample(s: string): Msg[] {
  const msgs: Msg[] = [];
  for (const seg of s.split(" · ")) {
    const m = seg.match(/^([A-Za-z][\w.'\-]{0,20}): ([\s\S]*)$/);
    if (m) {
      msgs.push({
        is_from_me: m[1] === "Me",
        sender: m[1] === "Me" || m[1] === "Them" ? null : m[1],
        text: m[2],
      });
    } else if (msgs.length > 0) {
      msgs[msgs.length - 1].text += " · " + seg;
    }
  }
  return msgs.filter((m) => m.text.trim().length > 0);
}

function ExampleCarousel({ examples }: { examples: string[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [slide, setSlide] = useState(0);
  const parsed = useMemo(() => examples.map(parseExample), [examples]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setSlide(Math.round(el.scrollLeft / el.clientWidth));
  };
  const goTo = (i: number) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" });
  };

  return (
    <div>
      <div ref={scrollRef} onScroll={onScroll}
           style={{ display: "flex", overflowX: "auto",
                    scrollSnapType: "x mandatory", borderRadius: 10,
                    scrollbarWidth: "none" }}>
        {parsed.map((msgs, i) => (
          <div key={i}
               style={{ flex: "0 0 100%", scrollSnapAlign: "start",
                        padding: "10px 12px", boxSizing: "border-box",
                        background: "rgba(128,128,128,0.07)",
                        borderRadius: 10 }}>
            {msgs.map((m, j) => {
              const prev = msgs[j - 1];
              const next = msgs[j + 1];
              const gap = next && next.is_from_me === m.is_from_me ? 3 : 8;
              // iOS style: sender name above the first bubble of a run.
              const showName = !m.is_from_me && m.sender
                && (!prev || prev.is_from_me || prev.sender !== m.sender);
              return (
                <div key={j} style={{ marginBottom: gap }}>
                  {showName && (
                    <div style={{ fontSize: 10.5, opacity: 0.55,
                                  margin: "0 0 2px 12px" }}>
                      {m.sender}
                    </div>
                  )}
                  <div style={{ display: "flex",
                                justifyContent: m.is_from_me
                                  ? "flex-end" : "flex-start" }}>
                    <div className={`bubble ${m.is_from_me ? "bubble-me"
                                                           : "bubble-them"}`}
                         style={{ fontSize: 12.5 }}>
                      {m.text}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "center",
                    alignItems: "center", gap: 8, marginTop: 6 }}>
        <button onClick={() => goTo(Math.max(0, slide - 1))}
                style={{ font: "inherit", fontSize: 12, color: "inherit",
                         background: "transparent", border: "none",
                         cursor: "pointer", opacity: slide > 0 ? 0.7 : 0.2 }}>
          ←
        </button>
        {parsed.map((_, i) => (
          <span key={i} onClick={() => goTo(i)}
                style={{ width: 6, height: 6, borderRadius: 3,
                         cursor: "pointer",
                         background: i === slide
                           ? "rgba(128,128,128,0.9)"
                           : "rgba(128,128,128,0.3)" }} />
        ))}
        <button onClick={() => goTo(Math.min(parsed.length - 1, slide + 1))}
                style={{ font: "inherit", fontSize: 12, color: "inherit",
                         background: "transparent", border: "none",
                         cursor: "pointer",
                         opacity: slide < parsed.length - 1 ? 0.7 : 0.2 }}>
          →
        </button>
      </div>
    </div>
  );
}

function Bar({ frac, color }: { frac: number; color: string }) {
  return (
    <span style={{ display: "inline-block", width: 90, height: 6,
                   borderRadius: 3, background: "rgba(128,128,128,0.18)",
                   verticalAlign: "middle" }}>
      <span style={{ display: "block", width: `${Math.round(frac * 100)}%`,
                     height: "100%", borderRadius: 3, background: color }} />
    </span>
  );
}

function CommunityDetail({ c, year, yearCount, children_ }: {
  c: Community;
  year: number | null;
  yearCount: number | undefined;
  children_: Community[];
}) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const yearEntries = Object.entries(c.years).sort();
  const maxYear = Math.max(...yearEntries.map(([, n]) => n), 1);
  const section = { fontSize: 11, opacity: 0.55, margin: "10px 0 4px",
                    textTransform: "uppercase" as const,
                    letterSpacing: 0.5 };
  return (
    <div style={{ border: "1px solid rgba(128,128,128,0.25)",
                  borderRadius: 10, padding: "12px 16px", margin: "6px 0" }}>
      <div style={{ fontSize: 14 }}>
        <span style={{ fontWeight: 650 }}>{c.label}</span>
        <span style={{ opacity: 0.6 }}>
          {" — "}
          {year
            ? `${yearCount ?? 0} sessions in ${year} (${c.size} all-time)`
            : `${c.size} sessions`}
          {" · median "}{c.median_msgs} msgs/session
        </span>
      </div>

      <div style={{ display: "grid", gap: "0 28px",
                    gridTemplateColumns:
                      "repeat(auto-fit, minmax(240px, 1fr))" }}>
        <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <div style={section}>Distinctive phrases</div>
          <div style={{ fontSize: 12.5 }}>{c.phrases.join(" · ")}</div>

          <div style={section}>Who</div>
          {c.top_contacts.map(([name, share]) => (
            <div key={name} style={{ display: "flex", alignItems: "center",
                                     gap: 8, fontSize: 12.5,
                                     padding: "2px 0" }}>
              <span style={{ width: 150, overflow: "hidden",
                             textOverflow: "ellipsis",
                             whiteSpace: "nowrap" }}>{name}</span>
              <Bar frac={share} color="#5b8ff9" />
              <span style={{ opacity: 0.55, fontSize: 11.5,
                             fontVariantNumeric: "tabular-nums" }}>
                {Math.round(share * 100)}%
              </span>
            </div>
          ))}

          <div style={section}>Direction</div>
          <div style={{ fontSize: 12.5, display: "grid", gap: 3 }}>
            <span>
              you sent{" "}
              <strong>{Math.round(c.from_me_frac * 100)}%</strong> of the
              messages <Bar frac={c.from_me_frac} color="#61ddaa" />
            </span>
            <span>
              you started{" "}
              <strong>{Math.round(c.initiated_frac * 100)}%</strong> of the
              sessions <Bar frac={c.initiated_frac} color="#f6bd16" />
            </span>
          </div>

          <div style={{ flex: 1, display: "flex", flexDirection: "column",
                        minHeight: 96, marginTop: 4 }}>
            <div style={section}>Activity by year</div>
            <div style={{ flex: 1, display: "flex", gap: 8,
                          alignItems: "stretch", minHeight: 72 }}>
              {yearEntries.map(([y, n]) => (
                <div key={y}
                     style={{ flex: 1, display: "flex",
                              flexDirection: "column", textAlign: "center",
                              fontSize: 11,
                              opacity: year === null
                                || String(year) === y ? 1 : 0.35 }}>
                  <div style={{ flex: 1, display: "flex",
                                alignItems: "flex-end",
                                justifyContent: "center", minHeight: 0 }}>
                    <div style={{ width: "70%", maxWidth: 56,
                                  borderRadius: "4px 4px 0 0",
                                  height: `${Math.max(8, (n / maxYear) * 100)}%`,
                                  minHeight: 4,
                                  background: "#7262fd" }} />
                  </div>
                  <div style={{ opacity: 0.6, marginTop: 4 }}>'{y.slice(2)}</div>
                  <div style={{ opacity: 0.45 }}>{n}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div style={section}>Typical conversations</div>
          <ExampleCarousel examples={c.examples} />
        </div>
      </div>

      {children_.length > 0 && (
        <>
          <div style={section}>
            {children_.length} micro-communities inside (γ=4) — click to
            expand
          </div>
          {children_.sort((a, b) => b.size - a.size).map((m) => (
            <div key={m.cluster_id}
                 onClick={() => setExpanded(
                   expanded === m.cluster_id ? null : m.cluster_id)}
                 style={{ padding: "5px 0", fontSize: 12.5,
                          cursor: "pointer",
                          borderBottom: "1px solid rgba(128,128,128,0.12)" }}>
              <div style={{ display: "flex",
                            justifyContent: "space-between", gap: 12 }}>
                <span>
                  <span style={{ fontWeight: 600 }}>{m.label}</span>
                  <span style={{ opacity: 0.6 }}>
                    {" — "}{m.phrases.slice(0, 4).join(" · ")}
                  </span>
                </span>
                <span style={{ opacity: 0.55, whiteSpace: "nowrap",
                               fontVariantNumeric: "tabular-nums" }}>
                  {m.size} · {m.top_contacts[0]?.[0]}{" "}
                  {Math.round((m.top_contacts[0]?.[1] ?? 0) * 100)}%
                </span>
              </div>
              {expanded === m.cluster_id && (
                <div style={{ margin: "6px 0 4px", padding: "6px 10px",
                              background: "rgba(128,128,128,0.08)",
                              borderRadius: 6, fontSize: 12 }}>
                  <div style={{ opacity: 0.7 }}>
                    who: {m.top_contacts.map(([n, s]) =>
                      `${n} ${Math.round(s * 100)}%`).join(", ")}
                    {" · you sent "}{Math.round(m.from_me_frac * 100)}%
                    {" · you started "}{Math.round(m.initiated_frac * 100)}%
                    {" · active "}{Object.keys(m.years).join(", ")}
                  </div>
                  <div style={{ marginTop: 8 }}
                       onClick={(e) => e.stopPropagation()}>
                    <ExampleCarousel examples={m.examples} />
                  </div>
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export default function SessionMap() {
  const map = useFetch(fetchSemanticMap, []);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rotRef = useRef({ yaw: 0.6, pitch: 0.3 });
  const zoomRef = useRef(90);   // px per world unit
  const dragRef = useRef<{ px: number; py: number } | null>(null);
  const layoutCacheRef = useRef(new Map<string, [number, number, number][]>());
  // 0 means "never interacted", so auto-rotation starts immediately.
  const lastInteractRef = useRef(0);
  const [gammaIdx, setGammaIdx] = useState(1);        // default γ=1
  const [selected, setSelected] = useState<number | null>(null);
  const [yearIdx, setYearIdx] = useState(0);          // 0 = all years
  const [hover, setHover] = useState<P | null>(null);
  const [layoutsReady, setLayoutsReady] = useState(false);
  // Tween between layouts: flat [x,y,z,...] start/end position buffers.
  const animRef = useRef<{ from: Float32Array; to: Float32Array;
                           t0: number } | null>(null);

  const umapNeighbors = map?.umap_neighbors?.length
    ? map.umap_neighbors
    : UMAP_NEIGHBORS_SWEEP;
  const umapMinDist = map?.umap_min_dist?.length
    ? map.umap_min_dist
    : UMAP_MIN_DIST_SWEEP;
  const defaultNn = map?.umap_default_neighbors ?? UMAP_DEFAULT_NEIGHBORS;
  const defaultMd = map?.umap_default_min_dist ?? UMAP_DEFAULT_MIN_DIST;
  const [neighborsIdx, setNeighborsIdx] = useState(() =>
    Math.max(0, umapNeighbors.indexOf(defaultNn)));
  const [minDistIdx, setMinDistIdx] = useState(() =>
    Math.max(0, umapMinDist.indexOf(defaultMd)));

  useEffect(() => {
    if (!map?.umap_neighbors?.length) return;
    const ni = map.umap_neighbors.indexOf(map.umap_default_neighbors);
    const mi = (map.umap_min_dist ?? []).indexOf(map.umap_default_min_dist);
    if (ni >= 0) setNeighborsIdx(ni);
    if (mi >= 0) setMinDistIdx(mi);
  }, [map]);

  const nNeighbors = umapNeighbors[neighborsIdx] ?? defaultNn;
  const minDist = umapMinDist[minDistIdx] ?? defaultMd;

  // One stable array of point objects; layout changes mutate wx/wy/wz in
  // the draw loop (tweened), so React state and hover identity never churn.
  const pts: P[] | null = useMemo(() => {
    if (!map || map.points.length === 0) return null;
    return map.points.map((p) => ({
      wx: p.x3, wy: p.y3, wz: p.z3,
      c: p.c, year: Number(p.date.slice(0, 4)),
      contact: p.contact, date: p.date, n_msgs: p.n_msgs,
      snippet: p.snippet,
    }));
  }, [map]);

  // Preload every baked UMAP layout once so slider changes are instant.
  useEffect(() => {
    if (!map || map.points.length === 0) {
      setLayoutsReady(false);
      return;
    }
    layoutCacheRef.current.set(
      layoutKey(UMAP_DEFAULT_NEIGHBORS, UMAP_DEFAULT_MIN_DIST),
      map.points.map((p) => [p.x3, p.y3, p.z3] as [number, number, number]));
    let cancelled = false;
    fetchSemanticMapLayouts()
      .then(({ variants }) => {
        if (cancelled) return;
        for (const [key, layout] of Object.entries(variants)) {
          if (layout.length === map.points.length) {
            layoutCacheRef.current.set(key, layout);
          }
        }
        setLayoutsReady(true);
      })
      .catch(() => {
        if (!cancelled) setLayoutsReady(true);
      });
    return () => { cancelled = true; };
  }, [map]);

  // Slider change → tween the dots from wherever they are now to the
  // target layout. Attributes (color, community, hover) are unaffected.
  useEffect(() => {
    if (!pts || pts.length === 0) return;
    const target = layoutCacheRef.current.get(layoutKey(nNeighbors, minDist));
    if (!target || target.length !== pts.length) return;
    const n = pts.length;
    const from = new Float32Array(n * 3);
    const to = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      from[i * 3] = pts[i].wx;
      from[i * 3 + 1] = pts[i].wy;
      from[i * 3 + 2] = pts[i].wz;
      to[i * 3] = target[i][0];
      to[i * 3 + 1] = target[i][1];
      to[i * 3 + 2] = target[i][2];
    }
    animRef.current = { from, to, t0: performance.now() };
  }, [pts, nNeighbors, minDist, layoutsReady]);

  const years = useMemo(() => {
    if (!pts) return [];
    return [...new Set(pts.map((p) => p.year))].sort();
  }, [pts]);
  const year = yearIdx === 0 ? null : years[yearIdx - 1];

  const gamma = GAMMAS[gammaIdx];

  // Session counts per community for the active year filter, so chips show
  // year-specific numbers and communities absent that year drop out.
  const yearCounts = useMemo(() => {
    const m = new Map<number, number>();
    for (const p of pts ?? []) {
      if (year !== null && p.year !== year) continue;
      const cid = p.c[gammaIdx];
      if (cid >= 0) m.set(cid, (m.get(cid) ?? 0) + 1);
    }
    return m;
  }, [pts, gammaIdx, year]);

  const legend = useMemo(() => (map?.communities ?? [])
    .filter((c) => c.gamma === gamma
                   && (yearCounts.get(c.cluster_id) ?? 0) > 0)
    .sort((a, b) => (yearCounts.get(b.cluster_id) ?? 0)
                    - (yearCounts.get(a.cluster_id) ?? 0)),
    [map, gamma, yearCounts]);

  // Clear a selection that has no sessions in the newly chosen year, so the
  // map doesn't silently dim everything.
  useEffect(() => {
    if (selected !== null && !legend.some((c) => c.cluster_id === selected)) {
      setSelected(null);
    }
  }, [legend, selected]);

  // Micro-communities inside the selected community: γ=4 clusters whose
  // member sessions mostly fall inside it (majority overlap, so a single
  // stray session doesn't pull in an unrelated micro-community).
  const children: SemanticCommunity[] = useMemo(() => {
    if (!map || !pts || selected === null
        || gammaIdx === GAMMAS.length - 1) return [];
    const inside = new Map<number, number>();
    const total = new Map<number, number>();
    for (const p of pts) {
      const micro = p.c[3];
      if (micro < 0) continue;
      total.set(micro, (total.get(micro) ?? 0) + 1);
      if (p.c[gammaIdx] === selected) {
        inside.set(micro, (inside.get(micro) ?? 0) + 1);
      }
    }
    return map.communities.filter(
      (c) => c.gamma === 4
        && (inside.get(c.cluster_id) ?? 0)
           >= 0.5 * (total.get(c.cluster_id) ?? 1));
  }, [map, pts, selected, gammaIdx]);

  const colorOf = (cid: number) =>
    cid < 0 ? "rgba(128,128,128,0.45)" : PALETTE[cid % PALETTE.length];

  const visible = (p: P) => {
    if (selected !== null && p.c[gammaIdx] !== selected) return false;
    return true;
  };
  const inYear = (p: P) => year === null || p.year === year;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pts) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let alive = true;

    const draw = () => {
      if (!alive) return;
      raf = requestAnimationFrame(draw);

      // Advance the layout tween: ease every dot toward its new position.
      const anim = animRef.current;
      if (anim) {
        const k = Math.min(1, (performance.now() - anim.t0) / LAYOUT_TWEEN_MS);
        const e = easeInOutCubic(k);
        for (let i = 0; i < pts.length; i++) {
          pts[i].wx = anim.from[i * 3] + (anim.to[i * 3] - anim.from[i * 3]) * e;
          pts[i].wy = anim.from[i * 3 + 1]
            + (anim.to[i * 3 + 1] - anim.from[i * 3 + 1]) * e;
          pts[i].wz = anim.from[i * 3 + 2]
            + (anim.to[i * 3 + 2] - anim.from[i * 3 + 2]) * e;
        }
        if (k >= 1) animRef.current = null;
      }

      const rot = rotRef.current;
      const idle = performance.now() - lastInteractRef.current
        > AUTOROTATE_AFTER_MS;
      if (idle && !dragRef.current) rot.yaw += 0.0018;
      const cy = Math.cos(rot.yaw), sy = Math.sin(rot.yaw);
      const cp = Math.cos(rot.pitch), sp = Math.sin(rot.pitch);

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      for (const p of pts) {
        const cid = p.c[gammaIdx];
        const dim = !visible(p) || !inYear(p);
        const x1 = p.wx * cy + p.wz * sy;
        const z1 = -p.wx * sy + p.wz * cy;
        const y2 = p.wy * cp - z1 * sp;
        const z2 = p.wy * sp + z1 * cp;
        const scale = FOV / Math.max(0.8, FOV + z2);
        const sx = W / 2 + x1 * scale * zoomRef.current;
        const syy = H / 2 + y2 * scale * zoomRef.current;
        ctx.globalAlpha = dim ? 0.05
          : (cid < 0 ? 0.3 : 0.75) * Math.min(1, 0.4 + scale * 0.6);
        ctx.fillStyle = colorOf(cid);
        ctx.beginPath();
        ctx.arc(sx, syy, (dim ? 1.1 : 2) * scale, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };
    raf = requestAnimationFrame(draw);
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
    };
  }, [pts, gammaIdx, selected, year]);

  // Native wheel listener: React's synthetic onWheel is passive, so it can't
  // preventDefault and the page would scroll while zooming.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pts) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      lastInteractRef.current = performance.now();
      zoomRef.current = Math.max(40, Math.min(400,
        zoomRef.current * Math.exp(-e.deltaY * 0.0015)));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [pts]);

  if (!map || !pts || pts.length === 0) {
    return map ? (
      <p style={{ fontSize: 13, opacity: 0.6 }}>Topic map unavailable.</p>
    ) : null;
  }

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    lastInteractRef.current = performance.now();
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = ((e.clientX - rect.left) / rect.width) * W;
    const my = ((e.clientY - rect.top) / rect.height) * H;
    if (dragRef.current) {
      rotRef.current.yaw += (e.clientX - dragRef.current.px) * 0.008;
      rotRef.current.pitch = Math.max(-1.4, Math.min(1.4,
        rotRef.current.pitch + (e.clientY - dragRef.current.py) * 0.008));
      dragRef.current = { px: e.clientX, py: e.clientY };
      return;
    }
    const rot = rotRef.current;
    const cy = Math.cos(rot.yaw), sy = Math.sin(rot.yaw);
    const cp = Math.cos(rot.pitch), sp = Math.sin(rot.pitch);
    let best: P | null = null;
    let bestD = 9 * 9;
    for (const p of pts) {
      if (!visible(p) || !inYear(p)) continue;
      const x1 = p.wx * cy + p.wz * sy;
      const z1 = -p.wx * sy + p.wz * cy;
      const y2 = p.wy * cp - z1 * sp;
      const z2 = p.wy * sp + z1 * cp;
      const scale = FOV / Math.max(0.8, FOV + z2);
      const sx = W / 2 + x1 * scale * zoomRef.current;
      const syy = H / 2 + y2 * scale * zoomRef.current;
      const d = (sx - mx) ** 2 + (syy - my) ** 2;
      if (d < bestD) { bestD = d; best = p; }
    }
    setHover(best);
  };

  const labelOf = new Map(legend.map((c) => [c.cluster_id, c.label]));
  const selectedCommunity =
    selected === null ? null
      : legend.find((c) => c.cluster_id === selected) ?? null;
  const gammaName = ["broadest", "broad", "fine", "finest"][gammaIdx];
  const umapPanel = (
    <div style={{ width: 168, flexShrink: 0, padding: "10px 12px",
                  border: "1px solid rgba(128,128,128,0.25)",
                  borderRadius: 10, fontSize: 12 }}>
      <div style={{ fontWeight: 650, marginBottom: 10 }}>UMAP layout</div>
      <label style={{ display: "block", opacity: 0.7, marginBottom: 6 }}>
        neighbors
        <input type="range" min={0}
               max={Math.max(0, umapNeighbors.length - 1)} step={1}
               value={neighborsIdx}
               onChange={(e) => setNeighborsIdx(Number(e.target.value))}
               style={{ width: "100%", accentColor: "#9661bc",
                        display: "block", marginTop: 4 }} />
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {nNeighbors}
        </span>
      </label>
      <label style={{ display: "block", opacity: 0.7, marginBottom: 6 }}>
        min dist
        <input type="range" min={0}
               max={Math.max(0, umapMinDist.length - 1)} step={1}
               value={minDistIdx}
               onChange={(e) => setMinDistIdx(Number(e.target.value))}
               style={{ width: "100%", accentColor: "#9661bc",
                        display: "block", marginTop: 4 }} />
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {minDist}
        </span>
      </label>
      <div style={{ fontSize: 11, opacity: 0.5, lineHeight: 1.4 }}>
        {!layoutsReady
          ? "Loading layout variants…"
          : "Higher neighbors = smoother global shape. Higher min dist = looser clusters."}
      </div>
    </div>
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 14,
                    flexWrap: "wrap", margin: "8px 0" }}>
        <label style={{ fontSize: 12, opacity: 0.7, display: "flex",
                        alignItems: "center", gap: 8 }}>
          resolution
          <input type="range" min={0} max={GAMMAS.length - 1} step={1}
                 value={gammaIdx}
                 onChange={(e) => { setGammaIdx(Number(e.target.value));
                                    setSelected(null); }}
                 style={{ width: 110, accentColor: "#5b8ff9" }} />
          <span style={{ width: 88, fontVariantNumeric: "tabular-nums" }}>
            γ={gamma} ({gammaName})
          </span>
        </label>
        <label style={{ fontSize: 12, opacity: 0.7, display: "flex",
                        alignItems: "center", gap: 8 }}>
          year
          <input type="range" min={0} max={years.length} step={1}
                 value={yearIdx}
                 onChange={(e) => setYearIdx(Number(e.target.value))}
                 style={{ width: 130, accentColor: "#61ddaa" }} />
          <span style={{ width: 34, fontVariantNumeric: "tabular-nums" }}>
            {year ?? "all"}
          </span>
        </label>
        <span style={{ display: "flex", gap: 4 }}>
          {[["−", 0.75], ["+", 1.33]].map(([sym, f]) => (
            <button key={sym as string}
                    onClick={() => {
                      lastInteractRef.current = performance.now();
                      zoomRef.current = Math.max(40, Math.min(400,
                        zoomRef.current * (f as number)));
                    }}
                    style={{ fontSize: 13, width: 26, height: 26,
                             borderRadius: 999, font: "inherit",
                             color: "inherit", cursor: "pointer",
                             background: "transparent",
                             border: "1px solid rgba(128,128,128,0.4)" }}>
              {sym}
            </button>
          ))}
          <span style={{ fontSize: 11, opacity: 0.5, alignSelf: "center" }}>
            scroll to zoom · drag to rotate
          </span>
        </span>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap",
                    margin: "6px 0 8px" }}>
        {legend.map((c) => (
          <button key={c.cluster_id}
                  onClick={() => setSelected(
                    selected === c.cluster_id ? null : c.cluster_id)}
                  style={{ fontSize: 12, padding: "2px 9px",
                           borderRadius: 999, font: "inherit",
                           color: "inherit", cursor: "pointer",
                           background: selected === c.cluster_id
                             ? "rgba(128,128,128,0.18)" : "transparent",
                           border: `1px solid ${colorOf(c.cluster_id)}`,
                           opacity: selected !== null
                             && selected !== c.cluster_id ? 0.4 : 1 }}>
            <span style={{ display: "inline-block", width: 8, height: 8,
                           borderRadius: 4, marginRight: 5,
                           background: colorOf(c.cluster_id) }} />
            {c.label}{" "}
            <span style={{ opacity: 0.5 }}>
              {yearCounts.get(c.cluster_id)}
            </span>
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
      <canvas ref={canvasRef} onPointerMove={onPointerMove}
              onPointerDown={(e) => {
                lastInteractRef.current = performance.now();
                dragRef.current = { px: e.clientX, py: e.clientY };
              }}
              onPointerUp={() => {
                dragRef.current = null;
                lastInteractRef.current = performance.now();
              }}
              onPointerLeave={() => {
                dragRef.current = null;
                lastInteractRef.current = performance.now();
                setHover(null);
              }}
              style={{ width: "100%", maxWidth: W,
                       aspectRatio: `${W}/${H}`, touchAction: "none",
                       border: "1px solid rgba(128,128,128,0.25)",
                       borderRadius: 10, cursor: "grab",
                       opacity: layoutsReady ? 1 : 0.55,
                       transition: "opacity 0.15s" }} />

      <div style={{ minHeight: 44, fontSize: 12.5, padding: "6px 2px",
                    opacity: hover ? 1 : 0.45 }}>
        {hover ? (
          <>
            <span style={{ fontWeight: 600 }}>
              {labelOf.get(hover.c[gammaIdx]) ?? "unclustered"}
            </span>
            {" · "}{hover.contact} · {hover.date} · {hover.n_msgs} msgs
            <div style={{ opacity: 0.75, marginTop: 2 }}>
              “{hover.snippet}”
            </div>
          </>
        ) : (
          "Hover a point to see the conversation. Click a community chip to isolate it and list its sub-communities."
        )}
      </div>
        </div>
        {umapPanel}
      </div>

      {selectedCommunity && (
        <CommunityDetail c={selectedCommunity} year={year}
                         yearCount={yearCounts.get(selectedCommunity.cluster_id)}
                         children_={children} />
      )}
    </div>
  );
}
