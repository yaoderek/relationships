import { useMemo, useState } from "react";
import { fetchYouCalendar } from "../api";
import { useFetch } from "../lib/useFetch";

const CELL = 11;
const GAP = 2;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type Cell = { date: string | null; count: number };

function buildWeeks(year: number, counts: Map<string, number>): Cell[][] {
  const weeks: Cell[][] = [];
  let week: Cell[] = [];
  const first = new Date(Date.UTC(year, 0, 1));
  for (let i = 0; i < first.getUTCDay(); i++) {
    week.push({ date: null, count: 0 });
  }
  const d = new Date(first);
  while (d.getUTCFullYear() === year) {
    const iso = d.toISOString().slice(0, 10);
    week.push({ date: iso, count: counts.get(iso) ?? 0 });
    if (week.length === 7) { weeks.push(week); week = []; }
    d.setUTCDate(d.getUTCDate() + 1);
  }
  if (week.length > 0) {
    while (week.length < 7) week.push({ date: null, count: 0 });
    weeks.push(week);
  }
  return weeks;
}

function cellColor(count: number, max: number): string {
  if (count === 0) return "rgba(128,128,128,0.10)";
  const t = Math.sqrt(count / max);
  return `rgba(91, 143, 249, ${0.25 + 0.75 * t})`;
}

export default function CalendarHeatmap() {
  const days = useFetch(fetchYouCalendar, []);
  const [year, setYear] = useState<number | null>(null);
  const [picked, setPicked] = useState<Cell | null>(null);

  const { counts, years } = useMemo(() => {
    const counts = new Map((days ?? []).map((d) => [d.date, d.count]));
    const years = [...new Set((days ?? []).map((d) => Number(d.date.slice(0, 4))))]
      .sort((a, b) => b - a);
    return { counts, years };
  }, [days]);

  if (!days || years.length === 0) return null;
  const selected = year ?? years[0];
  const weeks = buildWeeks(selected, counts);
  const max = Math.max(1, ...weeks.flat().map((c) => c.count));
  const yearTotal = weeks.flat().reduce((s, c) => s + c.count, 0);

  // Month label above the first column containing the 1st of each month.
  const monthAt = weeks.map((week) => {
    const firstOfMonth = week.find((c) => c.date?.endsWith("-01"));
    return firstOfMonth?.date
      ? MONTHS[Number(firstOfMonth.date.slice(5, 7)) - 1] : "";
  });

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start",
                  marginTop: 14 }}>
      <div style={{ overflowX: "auto", flex: 1 }}>
        <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 6 }}>
          {yearTotal.toLocaleString()} texts sent in {selected}
        </div>
        <div style={{ display: "flex", gap: GAP, marginBottom: 3 }}>
          {monthAt.map((m, i) => (
            <div key={i} style={{ width: CELL, fontSize: 9, opacity: 0.6,
                                  overflow: "visible", whiteSpace: "nowrap" }}>
              {m}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: GAP }}>
          {weeks.map((week, wi) => (
            <div key={wi}
                 style={{ display: "flex", flexDirection: "column", gap: GAP }}>
              {week.map((c, di) => (
                <div key={di}
                     title={c.date
                       ? `${c.date} — ${c.count.toLocaleString()} texts` : ""}
                     onClick={() => c.date
                       && setPicked(picked?.date === c.date ? null : c)}
                     style={{ width: CELL, height: CELL, borderRadius: 2.5,
                              cursor: c.date ? "pointer" : "default",
                              outline: picked?.date === c.date
                                ? "2px solid #5B8FF9" : "none",
                              outlineOffset: 1,
                              background: c.date
                                ? cellColor(c.count, max) : "transparent" }} />
              ))}
            </div>
          ))}
        </div>
        <div style={{ minHeight: 22, marginTop: 8, fontSize: 13 }}>
          {picked?.date && (
            <span>
              <span style={{ fontVariantNumeric: "tabular-nums" }}>
                {new Date(picked.date + "T00:00:00").toLocaleDateString(
                  undefined,
                  { weekday: "short", year: "numeric", month: "long",
                    day: "numeric" })}
              </span>
              {" — "}
              <strong>{picked.count.toLocaleString()}</strong>
              {picked.count === 1 ? " text sent" : " texts sent"}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4,
                      marginTop: 2, fontSize: 10, opacity: 0.6,
                      justifyContent: "flex-end" }}>
          Less
          {[0, 0.15, 0.4, 0.7, 1].map((t) => (
            <span key={t}
                  style={{ width: CELL, height: CELL, borderRadius: 2.5,
                           display: "inline-block",
                           background: t === 0 ? "rgba(128,128,128,0.10)"
                             : `rgba(91,143,249,${0.25 + 0.75 * t})` }} />
          ))}
          More
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {years.map((y) => (
          <button key={y} onClick={() => { setYear(y); setPicked(null); }}
                  style={{ padding: "5px 14px", fontSize: 13, font: "inherit",
                           textAlign: "center", borderRadius: 8,
                           color: "inherit",
                           border: y === selected
                             ? "1px solid rgba(91,143,249,0.7)"
                             : "1px solid transparent",
                           background: y === selected
                             ? "rgba(91,143,249,0.18)" : "transparent",
                           transition: "background .18s ease, border-color .18s ease" }}>
            {y}
          </button>
        ))}
      </div>
    </div>
  );
}
