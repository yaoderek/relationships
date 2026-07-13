import { useState } from "react";
import { fetchYouDaySummary, fetchYouHotDays } from "../api";
import type { YouDaySummary, YouHotDay } from "../api";
import { useFetch } from "../lib/useFetch";

function YouHotDayRow({ day, maxCount }:
  { day: YouHotDay; maxCount: number }) {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<YouDaySummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && !summary && !loading) {
      setLoading(true);
      fetchYouDaySummary(day.date)
        .then(setSummary)
        .catch(() => setError("Couldn't summarize — is OPENAI_API_KEY set in .env?"))
        .finally(() => setLoading(false));
    }
  };

  return (
    <div style={{ border: "1px solid rgba(128,128,128,0.25)", borderRadius: 8,
                  marginBottom: 8 }}>
      <button onClick={toggle}
              style={{ display: "flex", alignItems: "center", gap: 10,
                       width: "100%", padding: "10px 12px", font: "inherit",
                       fontSize: 14, border: "none", background: "transparent",
                       color: "inherit", textAlign: "left" }}>
        <span aria-hidden style={{ fontSize: 9, opacity: 0.6,
                                   transform: open ? "rotate(180deg)" : "none",
                                   transition: "transform .18s ease" }}>▼</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{day.date}</span>
        <span style={{ flex: 1 }}>
          <span style={{ display: "block", background: "#5B8FF9", height: 6,
                         borderRadius: 3,
                         width: `${(day.count / maxCount) * 100}%` }} />
        </span>
        <span style={{ fontSize: 12, opacity: 0.6, width: 220,
                       textAlign: "right" }}>
          {day.count.toLocaleString()} msgs · {day.sent.toLocaleString()} sent
          {day.top_contact ? ` · mostly ${day.top_contact}` : ""}
        </span>
      </button>
      <div style={{ display: "grid", gridTemplateRows: open ? "1fr" : "0fr",
                    transition: "grid-template-rows .3s ease" }}>
        <div style={{ overflow: "hidden" }}>
          <div style={{ padding: "0 12px 12px 31px", fontSize: 14,
                        lineHeight: 1.5 }}>
            {loading && <span style={{ opacity: 0.6 }}>Summarizing…</span>}
            {error && <span style={{ opacity: 0.7 }}>{error}</span>}
            {summary && (
              <>
                {summary.sentiment && (
                  <span style={{ display: "inline-block", fontSize: 12,
                                 padding: "2px 8px", borderRadius: 999,
                                 border: "1px solid rgba(128,128,128,0.35)",
                                 marginBottom: 6 }}>
                    {summary.sentiment}
                  </span>
                )}
                <div>{summary.summary}</div>
                {summary.quotes.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    {summary.quotes.map((q, i) => (
                      <div key={i}
                           style={{ padding: "4px 0 4px 10px", margin: "4px 0",
                                    borderLeft: "2px solid rgba(91,143,249,0.6)",
                                    fontSize: 13 }}>
                        “{q.text}”
                        <span style={{ opacity: 0.55 }}> — {q.speaker}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function YouHotDays() {
  const days = useFetch(fetchYouHotDays, []);
  if (!days || days.length === 0) return null;
  const max = Math.max(1, ...days.map((d) => d.count));
  return (
    <>
      {days.map((d) => (
        <YouHotDayRow key={d.date} day={d} maxCount={max} />
      ))}
    </>
  );
}
