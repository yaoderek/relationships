import { Link, Route, Routes } from "react-router-dom";
import Compare from "./pages/Compare";
import GroupDetail from "./pages/GroupDetail";
import GroupMember from "./pages/GroupMember";
import Groups from "./pages/Groups";
import Overview from "./pages/Overview";
import People from "./pages/People";
import Person from "./pages/Person";
import You from "./pages/You";

export default function App() {
  return (
    <div style={{ display: "flex", justifyContent: "center", gap: 28,
                  padding: 24 }}>
      <aside className="spine-rail">
        <div id="spine-slot" />
      </aside>
      <div style={{ width: "100%", maxWidth: 1000, minWidth: 0 }}>
        <nav style={{ display: "flex", gap: 16, marginBottom: 24 }}>
          <Link to="/">Overview</Link>
          <Link to="/people">People</Link>
          <Link to="/compare">Compare</Link>
          <Link to="/groups">Groups</Link>
          <Link to="/you">You</Link>
        </nav>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/people" element={<People />} />
          <Route path="/you" element={<You />} />
          <Route path="/person/:id" element={<Person />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/groups" element={<Groups />} />
          <Route path="/groups/:id" element={<GroupDetail />} />
          <Route path="/groups/:id/members/:pid" element={<GroupMember />} />
        </Routes>
      </div>
      <div className="spine-balance" aria-hidden />
    </div>
  );
}
