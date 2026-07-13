import { useEffect, useMemo, useRef, useState } from "react";
import { fetchPeopleMap } from "../api";
import type { MapPoint } from "../api";
import { useFetch } from "../lib/useFetch";

const W = 900;
const H = 560;
const FOV = 4.2;          // perspective strength
const LERP = 0.09;        // per-frame easing toward targets

export const CLUSTER_PALETTE = ["#5B8FF9", "#61DDAA", "#F6BD16", "#7262FD",
                                "#F08BB4", "#78D3F8", "#F6903D", "#008685"];

type Node = {
  id: number; name: string;
  x: number; y: number; z: number;
  tx: number; ty: number; tz: number;
  alpha: number; targetAlpha: number;
  cluster: number; msgs: number;
};

export default function PeopleMap3D() {
  const data = useFetch(fetchPeopleMap, []);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<Map<number, Node>>(new Map());
  const rotRef = useRef({ yaw: 0.6, pitch: 0.35, auto: true });
  const dragRef = useRef<{ px: number; py: number } | null>(null);
  const [periodIdx, setPeriodIdx] = useState<number | null>(null);
  const [hover, setHover] = useState<Node | null>(null);

  const periods = data?.periods ?? [];
  const idx = periodIdx ?? Math.max(0, periods.length - 1);
  const period = periods[idx];

  const byPeriod = useMemo(() => {
    const m = new Map<string, MapPoint[]>();
    for (const p of data?.points ?? []) {
      if (!m.has(p.period)) m.set(p.period, []);
      m.get(p.period)!.push(p);
    }
    return m;
  }, [data]);

  // Retarget nodes whenever the selected period changes.
  useEffect(() => {
    if (!period) return;
    const nodes = nodesRef.current;
    const present = new Set<number>();
    for (const p of byPeriod.get(period) ?? []) {
      present.add(p.person_id);
      const existing = nodes.get(p.person_id);
      if (existing) {
        Object.assign(existing, { tx: p.x, ty: p.y, tz: p.z,
                                  targetAlpha: 1, cluster: p.cluster_id,
                                  msgs: p.msgs });
      } else {
        nodes.set(p.person_id, {
          id: p.person_id, name: p.name,
          x: p.x, y: p.y, z: p.z, tx: p.x, ty: p.y, tz: p.z,
          alpha: 0, targetAlpha: 1, cluster: p.cluster_id, msgs: p.msgs,
        });
      }
    }
    for (const n of nodes.values()) {
      if (!present.has(n.id)) n.targetAlpha = 0;
    }
  }, [period, byPeriod]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;

    const draw = () => {
      const rot = rotRef.current;
      if (rot.auto && !dragRef.current) rot.yaw += 0.0022;
      const cy = Math.cos(rot.yaw), sy = Math.sin(rot.yaw);
      const cp = Math.cos(rot.pitch), sp = Math.sin(rot.pitch);

      ctx.clearRect(0, 0, W, H);
      const drawable: { n: Node; sx: number; sy: number; scale: number }[] = [];
      for (const n of nodesRef.current.values()) {
        n.x += (n.tx - n.x) * LERP;
        n.y += (n.ty - n.y) * LERP;
        n.z += (n.tz - n.z) * LERP;
        n.alpha += (n.targetAlpha - n.alpha) * LERP;
        if (n.alpha < 0.02) continue;
        // rotate around Y then X
        const x1 = n.x * cy + n.z * sy;
        const z1 = -n.x * sy + n.z * cy;
        const y2 = n.y * cp - z1 * sp;
        const z2 = n.y * sp + z1 * cp;
        const scale = FOV / (FOV + z2);
        drawable.push({ n, sx: W / 2 + x1 * scale * 160,
                        sy: H / 2 + y2 * scale * 160, scale });
      }
      drawable.sort((a, b) => a.scale - b.scale);  // paint far points first
      for (const d of drawable) {
        const r = Math.max(4, Math.sqrt(d.n.msgs) / 9) * d.scale;
        ctx.globalAlpha = d.n.alpha * Math.min(1, 0.35 + d.scale * 0.6);
        ctx.fillStyle = CLUSTER_PALETTE[d.n.cluster % CLUSTER_PALETTE.length];
        ctx.beginPath();
        ctx.arc(d.sx, d.sy, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.font = `${Math.max(9, 11 * d.scale)}px system-ui`;
        ctx.fillStyle = "rgba(200, 205, 215, 0.85)";
        ctx.fillText(d.n.name.split(" ")[0], d.sx + r + 3, d.sy + 3);
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  const pointer = (e: React.PointerEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (W / rect.width);
    const my = (e.clientY - rect.top) * (H / rect.height);
    if (dragRef.current) {
      rotRef.current.yaw += (e.clientX - dragRef.current.px) * 0.008;
      rotRef.current.pitch += (e.clientY - dragRef.current.py) * 0.008;
      rotRef.current.pitch = Math.max(-1.4, Math.min(1.4, rotRef.current.pitch));
      dragRef.current = { px: e.clientX, py: e.clientY };
      return;
    }
    // hover hit-test against current projection
    const rot = rotRef.current;
    const cy = Math.cos(rot.yaw), sy = Math.sin(rot.yaw);
    const cp = Math.cos(rot.pitch), sp = Math.sin(rot.pitch);
    let best: { n: Node; d: number } | null = null;
    for (const n of nodesRef.current.values()) {
      if (n.alpha < 0.5) continue;
      const x1 = n.x * cy + n.z * sy;
      const z1 = -n.x * sy + n.z * cy;
      const y2 = n.y * cp - z1 * sp;
      const z2 = n.y * sp + z1 * cp;
      const scale = FOV / (FOV + z2);
      const sx = W / 2 + x1 * scale * 160;
      const syy = H / 2 + y2 * scale * 160;
      const d = Math.hypot(mx - sx, my - syy);
      if (d < 22 && (!best || d < best.d)) best = { n, d };
    }
    setHover(best?.n ?? null);
  };

  if (!data || periods.length === 0) return null;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12,
                    marginBottom: 8 }}>
        <input type="range" min={0} max={periods.length - 1} value={idx}
               onChange={(e) => setPeriodIdx(Number(e.target.value))}
               style={{ flex: 1, accentColor: "#5B8FF9" }} />
        <span style={{ fontSize: 13, width: 70, opacity: 0.8,
                       fontVariantNumeric: "tabular-nums" }}>
          {period === "all" ? "All time" : period}
        </span>
      </div>
      <div style={{ position: "relative" }}>
        <canvas ref={canvasRef} width={W} height={H}
                onPointerDown={(e) => {
                  dragRef.current = { px: e.clientX, py: e.clientY };
                  rotRef.current.auto = false;
                }}
                onPointerUp={() => { dragRef.current = null; }}
                onPointerLeave={() => { dragRef.current = null; setHover(null); }}
                onPointerMove={pointer}
                style={{ width: "100%", display: "block", cursor: "grab",
                         border: "1px solid rgba(128,128,128,0.2)",
                         borderRadius: 12, touchAction: "none" }} />
        {hover && (
          <div style={{ position: "absolute", top: 10, left: 10,
                        padding: "6px 12px", borderRadius: 8, fontSize: 13,
                        background: "Canvas", color: "CanvasText",
                        border: "1px solid rgba(128,128,128,0.3)" }}>
            <strong>{hover.name}</strong>
            <span style={{ opacity: 0.6 }}>
              {" "}· {hover.msgs.toLocaleString()} msgs
            </span>
          </div>
        )}
      </div>
      <p style={{ fontSize: 11, opacity: 0.55, marginTop: 6 }}>
        Drag to rotate · scrub the timeline to watch people drift between
        clusters as their conversations with you change.
      </p>
    </div>
  );
}
