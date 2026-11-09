import { Link } from "react-router-dom";
import type { StageInfo } from "@/components/StageStepper";
import { approvedCount } from "@/workspace/stages";

export function ProjectHeader({ title, stages }: { title: string; stages: StageInfo[] | undefined }) {
  const approved = stages ? approvedCount(stages) : null;
  return (
    <header>
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <ol>
          <li>
            <Link to="/projects">Projects</Link>
          </li>
          <li>Project</li>
        </ol>
      </nav>
      <div className="project-header">
        <h1>{title}</h1>
        {approved !== null ? (
          <div className="progress-wrap">
            <span>{`${approved} of 6 stages approved`}</span>
            <div className="progress" role="progressbar" aria-label="Stages approved" aria-valuemin={0} aria-valuemax={6} aria-valuenow={approved}>
              <div className="progress-fill" data-testid="progress-fill" style={{ width: `${(approved / 6) * 100}%` }} />
            </div>
          </div>
        ) : null}
      </div>
    </header>
  );
}
