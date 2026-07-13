import { Link, Route, Routes } from "react-router-dom";
import Compare from "./pages/Compare";
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
        <Route path="/groups" element={<p>Groups — Task 16</p>} />
        <Route path="/groups/:id" element={<p>Group detail — Task 16</p>} />
      </Routes>
    </div>
  );
}
