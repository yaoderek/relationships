import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchGroups } from "../api";
import FilterPanel from "../components/FilterPanel";
import type { RangeDays } from "../components/FilterPanel";
import Leaderboard from "../components/Leaderboard";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

const DAY_MS = 86400000;

export default function Groups() {
  const navigate = useNavigate();
  const [range, setRange] = useState<RangeDays>(null);
  const [hideInactive, setHideInactive] = useState(false);
  const groups = useFetch(() => fetchGroups(range), [range]);
  const rows = (groups ?? []).filter((g) => !hideInactive
    || (Date.now() - new Date(g.last_ts).getTime()) / DAY_MS <= 30);
  return (
    <>
      <h1>Group chats</h1>
      <div style={{ margin: "4px 0 12px" }}>
        <FilterPanel range={range} onRange={setRange}
                     hideInactive={hideInactive}
                     onHideInactive={setHideInactive} />
      </div>
      {groups && (
        <Leaderboard
          rows={rows.map((g) => ({
            key: g.chat_id, name: g.name, total: g.total,
            subtitle: `${g.participants} people · you: ${fmtPercent(g.my_share)}`,
          }))}
          onSelect={(id) => navigate(`/groups/${id}`)}
        />
      )}
    </>
  );
}
