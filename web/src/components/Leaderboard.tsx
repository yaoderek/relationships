export type LeaderboardRow = { key: number; name: string; total: number; subtitle: string };

export default function Leaderboard(
  { rows, onSelect }: { rows: LeaderboardRow[]; onSelect: (key: number) => void },
) {
  const max = Math.max(1, ...rows.map((r) => r.total));
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.key} onClick={() => onSelect(r.key)} style={{ cursor: "pointer" }}>
            <td style={{ padding: "6px 8px", opacity: 0.5, width: 28 }}>{i + 1}</td>
            <td style={{ padding: "6px 8px" }}>
              <div>{r.name}</div>
              <div style={{ fontSize: 12, opacity: 0.6 }}>{r.subtitle}</div>
            </td>
            <td style={{ padding: "6px 8px", width: "40%" }}>
              <div style={{ background: "#5B8FF9", height: 8, borderRadius: 4,
                            width: `${(r.total / max) * 100}%` }} />
            </td>
            <td style={{ padding: "6px 8px", textAlign: "right",
                         fontVariantNumeric: "tabular-nums" }}>
              {r.total.toLocaleString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
