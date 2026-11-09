import { useParams, useSearchParams } from "react-router-dom";
import { NotFoundError, useProject, useStages } from "@/api/queries";
import { StoryUnavailableError, useStory } from "@/api/story";
import { CastScreen } from "@/cast/CastScreen";
import { AssemblyScreen } from "@/assembly/AssemblyScreen";
import { StageStepper } from "@/components/StageStepper";
import { FrameBoard } from "@/frames/FrameBoard";
import { ShotBoard } from "@/shots/ShotBoard";
import { SoundScreen } from "@/sound/SoundScreen";
import { StoryEditor } from "@/story/StoryEditor";
import { StoryInput } from "@/story/StoryInput";
import { VoiceBoard } from "@/voice/VoiceBoard";

const VOICE_STAGES = new Set([
  "CAST_APPROVED",
  "VOICES_APPROVED",
  "FRAMES_APPROVED",
  "SHOTS_APPROVED",
  "REEL_EXPORTED",
  "EXPORTED",
]);

const FRAME_STAGES = new Set(["VOICES_APPROVED", "FRAMES_APPROVED", "SHOTS_APPROVED", "REEL_EXPORTED", "EXPORTED"]);
const ASSEMBLY_STAGES = new Set(["SHOTS_APPROVED", "REEL_EXPORTED", "EXPORTED"]);
const SOUND_STAGES = new Set(["SHOTS_APPROVED", "REEL_EXPORTED", "EXPORTED"]);
const SHOT_STAGES = new Set(["FRAMES_APPROVED", "SHOTS_APPROVED", "REEL_EXPORTED", "EXPORTED"]);

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const stages = useStages(projectId);
  const story = useStory(projectId);
  const [params, setParams] = useSearchParams();
  const screen = params.get("screen");
  const show = (next: "voices" | "frames" | "shots" | "sound" | "assembly") => setParams(next === "voices" ? {} : { screen: next });

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
      {SHOT_STAGES.has(project.data.stage) && screen === "shots" ? (
        <ShotBoard projectId={projectId} onBack={() => show("frames")} onContinue={() => show("sound")} />
      ) : null}
      {SOUND_STAGES.has(project.data.stage) && screen === "sound" ? (
        <SoundScreen projectId={projectId} onBack={() => show("shots")} onContinue={() => show("assembly")} />
      ) : null}
      {ASSEMBLY_STAGES.has(project.data.stage) && screen === "assembly" ? (
        <AssemblyScreen projectId={projectId} onBack={() => show("sound")} backLabel="Back to Sound" />
      ) : null}
    </section>
  );
}
