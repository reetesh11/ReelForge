import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useEventStream } from "@/api/events";
import { ReconnectBanner } from "@/components/ReconnectBanner";
import { LibraryDetail } from "@/library/LibraryDetail";
import { LibraryPage } from "@/library/LibraryPage";
import { ProjectPage } from "@/routes/ProjectPage";
import { SettingsPage } from "@/routes/SettingsPage";
import { ProjectsPage } from "@/routes/ProjectsPage";

export function AppRoutes() {
  const { connected } = useEventStream();
  return (
    <div className="layout">
      <nav aria-label="Main" className="nav">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true" />
          ReelForge
        </span>
        <NavLink to="/projects">Projects</NavLink>
        <NavLink to="/settings">Settings &amp; status</NavLink>
        <NavLink to="/library">Library</NavLink>
      </nav>
      <main className="page">
        <div className="page-inner">
          <Routes>
            <Route path="/" element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<ProjectPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/library/:characterId" element={<LibraryDetail />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </div>
      </main>
      <ReconnectBanner connected={connected} />
    </div>
  );
}
