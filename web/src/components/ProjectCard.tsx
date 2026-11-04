import { Link } from "react-router-dom";
import type { Project } from "@/api/queries";
import { Chip } from "@/components/Chip";

const LABELS = ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"] as const;

type SegmentState = "approved" | "waiting" | "not_started";

/** Derive six segments from the approved count: approved first, then one waiting, the rest not started. */
export function miniRail(approved: number): Array<{ label: string; state: SegmentState }> {
  return LABELS.map((label, i) => ({
    label,
    state: i < approved ? "approved" : i === approved ? "waiting" : "not_started",
  }));
}

const STATE_TEXT: Record<SegmentState, string> = {
  approved: "approved",
  waiting: "needs you",
  not_started: "not started",
};

export function ProjectCard({ project }: { project: Project }) {
  const edited = new Date(project.updated_at);
  const segments = miniRail(project.stages_approved);
  const waiting = segments.find((s) => s.state === "waiting");
  return (
    <li className="row project-card">
      <div className="project-main">
        <Link to={`/projects/${project.id}`}>{project.title}</Link>
        <span className="meta">
          Edited <time dateTime={project.updated_at}>{edited.toLocaleString()}</time>
        </span>
      </div>
      <div className="project-main">
        <span className="meta">{`${project.stages_approved}/6 stages approved`}</span>
        <div className="mini-rail" data-testid="mini-rail">
          {segments.map((s) => (
            <span
              key={s.label}
              className="mini-rail-segment"
              data-testid="mini-rail-segment"
              data-state={s.state}
              title={`${s.label}: ${STATE_TEXT[s.state]}`}
            />
          ))}
        </div>
      </div>
      {waiting ? <Chip tone="amber">{`${waiting.label} needs you`}</Chip> : <Chip tone="green">All approved</Chip>}
    </li>
  );
}
