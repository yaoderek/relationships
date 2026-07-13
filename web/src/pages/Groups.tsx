import { useNavigate } from "react-router-dom";
import { fetchGroups } from "../api";
import Leaderboard from "../components/Leaderboard";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

export default function Groups() {
  const groups = useFetch(fetchGroups, []);
  const navigate = useNavigate();
  return (
    <>
      <h1>Group chats</h1>
      {groups && (
        <Leaderboard
          rows={groups.map((g) => ({
            key: g.chat_id, name: g.name, total: g.total,
            subtitle: `${g.participants} people · you: ${fmtPercent(g.my_share)}`,
          }))}
          onSelect={(id) => navigate(`/groups/${id}`)}
        />
      )}
    </>
  );
}
