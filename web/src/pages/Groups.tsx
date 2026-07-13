import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchGroups } from "../api";
import type { GroupSummary } from "../api";
import Dropdown from "../components/Dropdown";
import FilterPanel from "../components/FilterPanel";
import type { RangeDays } from "../components/FilterPanel";
import Leaderboard from "../components/Leaderboard";
import Spine from "../components/Spine";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

const DAY_MS = 86400000;

type SortMetric = {
  key: keyof GroupSummary;
  label: string;
  fmt: (x: number) => string;
};

const SORT_METRICS: SortMetric[] = [
  { key: "total", label: "Total messages", fmt: (x) => x.toLocaleString() },
  { key: "my_share", label: "Your share", fmt: fmtPercent },
  { key: "participants", label: "Participants", fmt: (x) => x.toLocaleString() },
];

export default function Groups() {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortMetric["key"]>("total");
  const [range, setRange] = useState<RangeDays>(null);
  const [hideInactive, setHideInactive] = useState(false);
  const groups = useFetch(() => fetchGroups(range), [range]);
  const metric = SORT_METRICS.find((m) => m.key === sortKey)!;
  const value = (g: GroupSummary) => g[metric.key] as number;
  const rows = (groups ?? [])
    .filter((g) => !hideInactive
      || (Date.now() - new Date(g.last_ts).getTime()) / DAY_MS <= 30)
    .sort((a, b) => value(b) - value(a));
  return (
    <>
      <Spine sections={[{ id: "groups-list", label: "Group chats" }]} />
      <h1 id="groups-list">Group chats</h1>
      <div style={{ display: "flex", alignItems: "center", gap: 8,
                    margin: "4px 0 12px" }}>
        <span style={{ fontSize: 13, opacity: 0.7 }}>sort by</span>
        <Dropdown
          value={sortKey}
          options={SORT_METRICS.map((m) => ({ value: m.key, label: m.label }))}
          onChange={(v) => setSortKey(v as SortMetric["key"])}
        />
        <FilterPanel range={range} onRange={setRange}
                     hideInactive={hideInactive}
                     onHideInactive={setHideInactive} />
      </div>
      {groups && (
        <Leaderboard
          rows={rows.map((g) => ({
            key: g.chat_id, name: g.name,
            total: value(g),
            display: metric.fmt(value(g)),
            subtitle: `${g.total.toLocaleString()} msgs · ${g.participants} `
              + `people · you: ${fmtPercent(g.my_share)}`,
          }))}
          onSelect={(id) => navigate(`/groups/${id}`)}
        />
      )}
    </>
  );
}
