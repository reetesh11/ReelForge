import { useParams } from "react-router-dom";
import { NotFoundError, useProject, useStages } from "@/api/queries";
import { StageStepper } from "@/components/StageStepper";

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const stages = useStages(projectId);

  if (project.isPending) return <p>Loading...</p>;
  if (project.isError) {
    return project.error instanceof NotFoundError ? (
      <p>Project not found.</p>
    ) : (
      <p>Couldn't load this project.</p>
    );
  }

  return (
    <section>
      <h1>{project.data.title}</h1>
      {stages.data ? <StageStepper stages={stages.data} /> : null}
      <p>This stage arrives in a later milestone.</p>
    </section>
  );
}
