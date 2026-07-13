export type LeaderboardRow = {
  key: number; name: string; total: number; subtitle: string;
  display?: string;
  badge?: "fire" | "moon";
  badgeTitle?: string;
};

const ROW_H = 56;
const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

function Badge({ kind, title }: { kind?: "fire" | "moon"; title?: string }) {
  if (kind === "fire") {
    return (
      <svg width="11" height="11" viewBox="0 0 24 24" aria-label={title}>
        <title>{title}</title>
        <path fill="rgba(196, 92, 74, 0.65)"
              d="M13.5 0.7s1 3.2-1.6 6.4C9.6 10 6.9 11 6.9 11s.4-2.5-1.2-4.2C2.9 9.3 2 12 2 14.2 2 19.6 6.5 24 12 24s10-4.4 10-9.8c0-6.7-6-8.8-8.5-13.5z"/>
      </svg>
    );
  }
  if (kind === "moon") {
    return (
      <svg width="11" height="11" viewBox="0 0 24 24" aria-label={title}>
        <title>{title}</title>
        <path fill="rgba(150, 155, 170, 0.4)"
              d="M12 3a9 9 0 1 0 9 9 7.2 7.2 0 0 1-9-9z"/>
      </svg>
    );
  }
  return null;
}

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
            <div style={{ width: 14, display: "flex", alignItems: "center",
                          justifyContent: "center" }}>
              <Badge kind={r.badge} title={r.badgeTitle} />
            </div>
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
