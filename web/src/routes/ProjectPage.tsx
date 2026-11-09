import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { NotFoundError, useProject, useStages, type Project } from "@/api/queries";
import { StoryUnavailableError, useStory } from "@/api/story";
import { AssemblyScreen } from "@/assembly/AssemblyScreen";
import { CastScreen } from "@/cast/CastScreen";
import { StageStepper } from "@/components/StageStepper";
import { StateMessage } from "@/components/StateMessage";
import { FrameBoard } from "@/frames/FrameBoard";
import { ShotBoard } from "@/shots/ShotBoard";
import { SoundScreen } from "@/sound/SoundScreen";
import { StoryEditor } from "@/story/StoryEditor";
import { StoryInput } from "@/story/StoryInput";
import { VoiceBoard } from "@/voice/VoiceBoard";
import { NextUpBar } from "@/workspace/NextUpBar";
import { ProjectHeader } from "@/workspace/ProjectHeader";
import { resolveStage, type StageKey } from "@/workspace/stages";

type ProjectStage = Project["stage"];

// Sound sits between Shots and Assembly but is not a stage on the rail; it opens once the shots are approved.
const SOUND_STAGES = new Set<ProjectStage>(["SHOTS_APPROVED", "REEL_EXPORTED", "EXPORTED"]);

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const stages = useStages(projectId);
  const story = useStory(projectId);
  const [params, setParams] = useSearchParams();
  // The landing stage is fixed when the project first loads, so approving the last item of a stage
  // does not move the person to the next panel behind their back.
  const [pinned, setPinned] = useState<{ id: string; stage: ProjectStage } | null>(null);
  if (project.data && pinned?.id !== projectId) setPinned({ id: projectId, stage: project.data.stage });

  if (project.isPending) return <StateMessage>Loading...</StateMessage>;
  if (project.isError) {
    return project.error instanceof NotFoundError ? (
      <StateMessage>Project not found.</StateMessage>
    ) : (
      <StateMessage tone="error">Couldn't load this project.</StateMessage>
    );
  }

  const landed = pinned?.stage ?? project.data.stage;
  const wanted = params.get("stage") ?? params.get("screen");
  const soundOpen = wanted === "sound" && SOUND_STAGES.has(landed);
  const shown = resolveStage(params, landed, stages.data);
  const go = (key: StageKey) => setParams({ stage: key });
  const goSound = () => setParams({ stage: "sound" });
  // Sound is not on the rail, so the rail and the next-up bar treat it as the step before Assembly.
  const railStage: StageKey = soundOpen ? "assembly" : shown;

  return (
    <section>
      <ProjectHeader title={project.data.title} stages={stages.data} />
      {stages.data ? <StageStepper stages={stages.data} current={railStage} onSelect={(key) => go(key as StageKey)} /> : null}
      {stages.data ? <NextUpBar shown={railStage} stages={stages.data} onGo={go} /> : null}
      {story.error instanceof StoryUnavailableError ? (
        <StateMessage>This stage arrives in a later milestone.</StateMessage>
      ) : null}
      <section className="stage-panel" data-testid={`stage-panel-${soundOpen ? "sound" : shown}`}>
        {!soundOpen && shown === "story" ? (
          <>
            {story.isPending ? <StateMessage>Loading...</StateMessage> : null}
            {story.isError && !(story.error instanceof StoryUnavailableError) ? (
              <StateMessage tone="error">Couldn't load the story.</StateMessage>
            ) : null}
            {story.data === null ? <StoryInput projectId={projectId} /> : null}
            {story.data ? <StoryEditor projectId={projectId} story={story.data} /> : null}
          </>
        ) : null}
        {!soundOpen && shown === "cast" ? <CastScreen projectId={projectId} /> : null}
        {!soundOpen && shown === "voices" ? <VoiceBoard projectId={projectId} onContinue={() => go("frames")} /> : null}
        {!soundOpen && shown === "frames" ? (
          <FrameBoard projectId={projectId} onBack={() => go("voices")} onContinue={() => go("shots")} />
        ) : null}
        {!soundOpen && shown === "shots" ? (
          <ShotBoard projectId={projectId} onBack={() => go("frames")} onContinue={goSound} />
        ) : null}
        {soundOpen ? <SoundScreen projectId={projectId} onBack={() => go("shots")} onContinue={() => go("assembly")} /> : null}
        {!soundOpen && shown === "assembly" ? (
          <AssemblyScreen projectId={projectId} onBack={goSound} backLabel="Back to Sound" />
        ) : null}
      </section>
    </section>
  );
}
