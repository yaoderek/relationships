import { useEffect, useMemo, useRef, useState } from "react";
import { forceCollide, forceSimulation, forceX, forceY } from "d3-force";
import type { Simulation } from "d3-force";
import { fetchPersonsTimeline } from "../api";
import { useFetch } from "../lib/useFetch";

const W = 860;
const H = 540;
const MAX_R = 78;
const MIN_R = 9;
const WINDOW = 3;          // trailing months that define a blob's size
const GROW = 0.12;         // radius lerp per frame — the "amalgamate" feel

type BlobNode = {
  id: number;
  name: string;
  r: number;
  targetR: number;
  x: number;
  y: number;
  vx?: number;
  vy?: number;
};

function color(t: number): string {
  return `hsl(217, ${55 + t * 35}%, ${34 + t * 30}%)`;
}

export default function BlobField() {
  const rows = useFetch(fetchPersonsTimeline, []);
  const [monthIdx, setMonthIdx] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [, setFrame] = useState(0);
  const simRef = useRef<Simulation<BlobNode, undefined> | null>(null);
  const nodesRef = useRef<BlobNode[]>([]);
  const collideRef = useRef(forceCollide<BlobNode>());

  const { months, sizes, people, maxSize } = useMemo(() => {
    const months = [...new Set((rows ?? []).map((r) => r.bucket))].sort();
    const people = new Map<number, string>();
    const byKey = new Map<string, number>();
    for (const r of rows ?? []) {
      people.set(r.person_id, r.display_name);
      byKey.set(`${r.person_id}:${r.bucket}`, r.count);
    }
    // Blob size at month i = messages over the trailing WINDOW months.
    const sizes = new Map<string, number>();
    let maxSize = 1;
    for (const [pid] of people) {
      for (let i = 0; i < months.length; i++) {
        let s = 0;
        for (let j = Math.max(0, i - WINDOW + 1); j <= i; j++) {
          s += byKey.get(`${pid}:${months[j]}`) ?? 0;
        }
        sizes.set(`${pid}:${i}`, s);
        if (s > maxSize) maxSize = s;
      }
    }
    return { months, sizes, people, maxSize };
  }, [rows]);

  const idx = monthIdx ?? months.length - 1;

  useEffect(() => {
    if (people.size === 0) return;
    const nodes: BlobNode[] = [...people].map(([id, name], i) => {
      const angle = (i / people.size) * Math.PI * 2;
      return { id, name, r: 0, targetR: 0,
               x: W / 2 + Math.cos(angle) * 180,
               y: H / 2 + Math.sin(angle) * 140 };
    });
    nodesRef.current = nodes;
    const sim = forceSimulation(nodes)
      .force("x", forceX<BlobNode>(W / 2).strength(0.05))
      .force("y", forceY<BlobNode>(H / 2).strength(0.06))
      .force("collide", collideRef.current.strength(0.95).iterations(2))
      .velocityDecay(0.22)   // low damping keeps it bouncy
      .alphaDecay(0)
      .stop();
    simRef.current = sim;
    let raf = 0;
    const loop = () => {
      for (const n of nodesRef.current) {
        n.r += (n.targetR - n.r) * GROW;
      }
      // refresh collision radii so growth pushes neighbors aside
      collideRef.current.radius((d) => d.r + 2.5);
      sim.tick();
      setFrame((f) => f + 1);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); sim.stop(); };
  }, [people]);

  useEffect(() => {
    for (const n of nodesRef.current) {
      const s = sizes.get(`${n.id}:${idx}`) ?? 0;
      n.targetR = s === 0 ? 0
        : MIN_R + (MAX_R - MIN_R) * Math.sqrt(s / maxSize);
    }
  }, [idx, sizes, maxSize]);

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      setMonthIdx((i) => {
        const next = (i ?? months.length - 1) + 1;
        if (next >= months.length) { setPlaying(false); return i; }
        return next;
      });
    }, 550);
    return () => clearInterval(t);
  }, [playing, months.length]);

  if (!rows) return <p>Loading…</p>;
  if (months.length === 0) return null;

  const nodes = nodesRef.current;
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12,
                    marginBottom: 8 }}>
        <button
          onClick={() => {
            if (!playing && idx >= months.length - 1) setMonthIdx(0);
            setPlaying((p) => !p);
          }}
          style={{ width: 34, height: 34, borderRadius: 999, fontSize: 13,
                   border: "1px solid rgba(128,128,128,0.35)",
                   background: "transparent", color: "inherit" }}
          aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <input type="range" min={0} max={months.length - 1} value={idx}
               onChange={(e) => { setPlaying(false);
                                  setMonthIdx(Number(e.target.value)); }}
               style={{ flex: 1, accentColor: "#5B8FF9" }} />
        <span style={{ fontSize: 13, fontVariantNumeric: "tabular-nums",
                       opacity: 0.8, width: 62 }}>
          {months[idx]}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`}
           style={{ width: "100%", display: "block",
                    border: "1px solid rgba(128,128,128,0.2)",
                    borderRadius: 12 }}>
        {nodes.filter((n) => n.r > 0.5).map((n) => {
          const t = n.r / MAX_R;
          return (
            <g key={n.id} transform={`translate(${n.x},${n.y})`}>
              <circle r={n.r} fill={color(t)} fillOpacity={0.9}>
                <title>{n.name}</title>
              </circle>
              {n.r > 16 && (
                <text textAnchor="middle" dy="0.35em"
                      style={{ fontSize: Math.max(9, Math.min(15, n.r / 3)),
                               fill: "white", opacity: 0.92,
                               pointerEvents: "none" }}>
                  {n.name.split(" ")[0]}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
