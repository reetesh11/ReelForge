import { NavLink, Navigate, Route, Routes } from "react-router-dom";

function Placeholder({ title }: { title: string }) {
  return (
    <section>
      <h1>{title}</h1>
    </section>
  );
}

export function AppRoutes() {
  return (
    <div className="layout">
      <nav aria-label="Main" className="nav">
        <NavLink to="/projects">Projects</NavLink>
        <NavLink to="/settings">Settings &amp; status</NavLink>
      </nav>
      <main className="page">
        <Routes>
          <Route path="/" element={<Navigate to="/projects" replace />} />
          <Route path="/projects" element={<Placeholder title="Projects" />} />
          <Route path="/projects/:projectId" element={<Placeholder title="Project" />} />
          <Route path="/settings" element={<Placeholder title="Settings & status" />} />
        </Routes>
      </main>
    </div>
  );
}
