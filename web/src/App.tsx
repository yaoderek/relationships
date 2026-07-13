import { Link, Route, Routes } from "react-router-dom";

export default function App() {
  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: 24 }}>
      <nav style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        <Link to="/">Overview</Link>
        <Link to="/compare">Compare</Link>
        <Link to="/groups">Groups</Link>
      </nav>
      <Routes>
        <Route path="/" element={<p>Overview — Task 14</p>} />
        <Route path="/person/:id" element={<p>Person — Task 15</p>} />
        <Route path="/compare" element={<p>Compare — Task 15</p>} />
        <Route path="/groups" element={<p>Groups — Task 16</p>} />
        <Route path="/groups/:id" element={<p>Group detail — Task 16</p>} />
      </Routes>
    </div>
  );
}
