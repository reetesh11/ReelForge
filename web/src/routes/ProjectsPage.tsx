import { useState } from "react";
import { useProjects } from "@/api/queries";
import { NewProjectForm } from "@/components/NewProjectForm";
import { ProjectCard } from "@/components/ProjectCard";

export function ProjectsPage() {
  const projects = useProjects();
  const [creating, setCreating] = useState(false);

  return (
    <section>
      <header className="row">
        <h1>Projects</h1>
        <button type="button" onClick={() => setCreating(true)}>
          New project
        </button>
      </header>
      {creating ? <NewProjectForm onDone={() => setCreating(false)} /> : null}
      {projects.isPending ? (
        <div className="list">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" data-testid="project-skeleton" />
          ))}
        </div>
      ) : projects.isError ? (
        <div>
          <p>Couldn't load projects.</p>
          <button type="button" onClick={() => void projects.refetch()}>
            Retry
          </button>
        </div>
      ) : projects.data.length === 0 ? (
        <p>No projects yet.</p>
      ) : (
        <ul aria-label="Projects" className="list">
          {projects.data.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </ul>
      )}
    </section>
  );
}
