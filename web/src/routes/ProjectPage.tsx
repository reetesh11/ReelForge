import { useParams, useSearchParams } from "react-router-dom";
import { NotFoundError, useProject, useStages } from "@/api/queries";
import { StoryUnavailableError, useStory } from "@/api/story";
import { AssemblyScreen } from "@/assembly/AssemblyScreen";
import { CastScreen } from "@/cast/CastScreen";
import { StageStepper } from "@/components/StageStepper";
import { StateMessage } from "@/components/StateMessage";
import { FrameBoard } from "@/frames/FrameBoard";
import { ShotBoard } from "@/shots/ShotBoard";
import { StoryEditor } from "@/story/StoryEditor";
import { StoryInput } from "@/story/StoryInput";
import { VoiceBoard } from "@/voice/VoiceBoard";
import { NextUpBar } from "@/workspace/NextUpBar";
import { ProjectHeader } from "@/workspace/ProjectHeader";
import { resolveStage, type StageKey } from "@/workspace/stages";

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const stages = useStages(projectId);
  const story = useStory(projectId);
  const [params, setParams] = useSearchParams();

  if (project.isPending) return <StateMessage>Loading...</StateMessage>;
  if (project.isError) {
    return project.error instanceof NotFoundError ? (
      <StateMessage>Project not found.</StateMessage>
    ) : (
      <StateMessage tone="error">Couldn't load this project.</StateMessage>
    );
  }

  const shown = resolveStage(params, project.data.stage, stages.data);
  const go = (key: StageKey) => setParams({ stage: key });

  return (
    <section>
      <ProjectHeader title={project.data.title} stages={stages.data} />
      {stages.data ? <StageStepper stages={stages.data} current={shown} onSelect={(key) => go(key as StageKey)} /> : null}
      {stages.data ? <NextUpBar shown={shown} stages={stages.data} onGo={go} /> : null}
      {story.error instanceof StoryUnavailableError ? (
        <StateMessage>This stage arrives in a later milestone.</StateMessage>
      ) : null}
      <section className="stage-panel" data-testid={`stage-panel-${shown}`}>
        {shown === "story" ? (
          <>
            {story.isPending ? <StateMessage>Loading...</StateMessage> : null}
            {story.isError && !(story.error instanceof StoryUnavailableError) ? (
              <StateMessage tone="error">Couldn't load the story.</StateMessage>
            ) : null}
            {story.data === null ? <StoryInput projectId={projectId} /> : null}
            {story.data ? <StoryEditor projectId={projectId} story={story.data} /> : null}
          </>
        ) : null}
        {shown === "cast" ? <CastScreen projectId={projectId} /> : null}
        {shown === "voices" ? <VoiceBoard projectId={projectId} onContinue={() => go("frames")} /> : null}
        {shown === "frames" ? (
          <FrameBoard projectId={projectId} onBack={() => go("voices")} onContinue={() => go("shots")} />
        ) : null}
        {shown === "shots" ? (
          <ShotBoard projectId={projectId} onBack={() => go("frames")} onContinue={() => go("assembly")} />
        ) : null}
        {shown === "assembly" ? <AssemblyScreen projectId={projectId} onBack={() => go("shots")} /> : null}
      </section>
    </section>
  );
}
