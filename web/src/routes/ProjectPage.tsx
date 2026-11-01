import { useParams } from "react-router-dom";
import { NotFoundError, useProject, useStages } from "@/api/queries";
import { StoryUnavailableError, useStory } from "@/api/story";
import { StageStepper } from "@/components/StageStepper";
import { StoryEditor } from "@/story/StoryEditor";
import { StoryInput } from "@/story/StoryInput";

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const stages = useStages(projectId);
  const story = useStory(projectId);

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
      {story.isPending ? <p>Loading...</p> : null}
      {story.error instanceof StoryUnavailableError ? <p>This stage arrives in a later milestone.</p> : null}
      {story.isError && !(story.error instanceof StoryUnavailableError) ? (
        <p>Couldn't load the story.</p>
      ) : null}
      {story.data === null ? <StoryInput projectId={projectId} /> : null}
      {story.data ? <StoryEditor projectId={projectId} story={story.data} /> : null}
    </section>
  );
}
