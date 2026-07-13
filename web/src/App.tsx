import { Link, Route, Routes } from "react-router-dom";
import Compare from "./pages/Compare";
import GroupDetail from "./pages/GroupDetail";
import GroupMember from "./pages/GroupMember";
import Groups from "./pages/Groups";
import Overview from "./pages/Overview";
import Person from "./pages/Person";

export default function App() {
  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: 24 }}>
      <nav style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        <Link to="/">Overview</Link>
        <Link to="/compare">Compare</Link>
        <Link to="/groups">Groups</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/person/:id" element={<Person />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/groups" element={<Groups />} />
        <Route path="/groups/:id" element={<GroupDetail />} />
        <Route path="/groups/:id/members/:pid" element={<GroupMember />} />
      </Routes>
    </div>
  );
}
