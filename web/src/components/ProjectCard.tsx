import { Link } from "react-router-dom";
import type { Project } from "@/api/queries";

export function ProjectCard({ project }: { project: Project }) {
  const edited = new Date(project.updated_at);
  return (
    <li className="row">
      <Link to={`/projects/${project.id}`}>{project.title}</Link>
      <span className="meta">{`${project.stages_approved}/6 stages approved`}</span>
      <span className="meta">
        Edited <time dateTime={project.updated_at}>{edited.toLocaleString()}</time>
      </span>
    </li>
  );
}
