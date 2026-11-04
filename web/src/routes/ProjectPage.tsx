import { useParams, useSearchParams } from "react-router-dom";
import { NotFoundError, useProject, useStages } from "@/api/queries";
import { StoryUnavailableError, useStory } from "@/api/story";
import { CastScreen } from "@/cast/CastScreen";
import { StageStepper } from "@/components/StageStepper";
import { FrameBoard } from "@/frames/FrameBoard";
import { StoryEditor } from "@/story/StoryEditor";
import { StoryInput } from "@/story/StoryInput";
import { VoiceBoard } from "@/voice/VoiceBoard";

const VOICE_STAGES = new Set([
  "CAST_APPROVED",
  "VOICES_APPROVED",
  "FRAMES_APPROVED",
  "SHOTS_APPROVED",
  "ASSEMBLED",
  "EXPORTED",
]);

const FRAME_STAGES = new Set(["VOICES_APPROVED", "FRAMES_APPROVED", "SHOTS_APPROVED", "ASSEMBLED", "EXPORTED"]);

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const stages = useStages(projectId);
  const story = useStory(projectId);
  const [params, setParams] = useSearchParams();
  const screen = params.get("screen");
  const show = (next: "voices" | "frames" | "shots") => setParams(next === "voices" ? {} : { screen: next });

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
      {project.data.stage !== "DRAFT" ? <CastScreen projectId={projectId} /> : null}
      {VOICE_STAGES.has(project.data.stage) && (screen === null || screen === "voices") ? (
        <VoiceBoard projectId={projectId} onContinue={() => show("frames")} />
      ) : null}
      {FRAME_STAGES.has(project.data.stage) && screen === "frames" ? (
        <FrameBoard projectId={projectId} onBack={() => show("voices")} onContinue={() => show("shots")} />
      ) : null}
    </section>
  );
}
