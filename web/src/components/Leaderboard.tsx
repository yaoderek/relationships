export type LeaderboardRow = {
  key: number; name: string; total: number; subtitle: string;
  display?: string;
};

const ROW_H = 56;
const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

export default function Leaderboard(
  { rows, onSelect }: { rows: LeaderboardRow[]; onSelect: (key: number) => void },
) {
  const max = Math.max(1, ...rows.map((r) => r.total));
  const position = new Map(rows.map((r, i) => [r.key, i]));
  // Render in stable key order so React keeps DOM nodes in place and the
  // translateY change animates rows to their new rank.
  const stable = [...rows].sort((a, b) => a.key - b.key);
  return (
    <div style={{ position: "relative", height: rows.length * ROW_H }}>
      {stable.map((r) => {
        const i = position.get(r.key)!;
        return (
          <div
            key={r.key}
            className="lb-row"
            onClick={() => onSelect(r.key)}
            style={{
              position: "absolute", top: 0, left: 0, right: 0, height: ROW_H,
              boxSizing: "border-box",
              transform: `translateY(${i * ROW_H}px)`,
              transition: `transform .5s ${EASE}`,
              display: "flex", alignItems: "center", gap: 10,
              padding: "0 8px", borderRadius: 8, cursor: "pointer",
            }}
          >
            <div style={{ width: 26, opacity: 0.5,
                          fontVariantNumeric: "tabular-nums" }}>
              {i + 1}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis",
                            whiteSpace: "nowrap" }}>
                {r.name}
              </div>
              <div style={{ fontSize: 12, opacity: 0.6, overflow: "hidden",
                            textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.subtitle}
              </div>
            </div>
            <div style={{ width: "38%" }}>
              <div style={{
                background: "#5B8FF9", height: 8, borderRadius: 4,
                width: `${(r.total / max) * 100}%`,
                transition: `width .5s ${EASE}`,
              }} />
            </div>
            <div style={{ width: 92, textAlign: "right",
                          fontVariantNumeric: "tabular-nums" }}>
              {r.display ?? r.total.toLocaleString()}
            </div>
          </div>
        );
      })}
    </div>
  );
}
