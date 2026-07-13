import { Fragment } from "react";
import type { HeatCell } from "../api";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function Heatmap({ cells }: { cells: HeatCell[] }) {
  const lookup = new Map(cells.map((c) => [`${c.weekday}:${c.hour}`, c.count]));
  const max = Math.max(1, ...cells.map((c) => c.count));
  return (
    <div style={{ display: "grid", gridTemplateColumns: "38px repeat(24, 1fr)", gap: 2 }}>
      <div />
      {Array.from({ length: 24 }, (_, h) => (
        <div key={h} style={{ fontSize: 9, textAlign: "center", opacity: 0.6 }}>
          {h % 6 === 0 ? h : ""}
        </div>
      ))}
      {DAYS.map((day, wd) => (
        <Fragment key={day}>
          <div style={{ fontSize: 11, opacity: 0.7, lineHeight: "16px" }}>{day}</div>
          {Array.from({ length: 24 }, (_, h) => {
            const count = lookup.get(`${wd}:${h}`) ?? 0;
            return (
              <div key={h} title={`${day} ${h}:00 — ${count} messages`}
                   style={{ height: 16, borderRadius: 3,
                            background: `rgba(91, 143, 249, ${count / max})`,
                            outline: "1px solid rgba(128,128,128,0.15)" }} />
            );
          })}
        </Fragment>
      ))}
    </div>
  );
}
