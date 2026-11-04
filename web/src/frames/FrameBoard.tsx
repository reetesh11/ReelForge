import { useCancelFrames, useFrames, useGenerateFrames, type FramesState } from "@/api/frames";
import { useElapsed } from "@/components/useElapsed";
import { FrameCard } from "./FrameCard";

const FRAMES_DONE = new Set(["FRAMES_APPROVED", "SHOTS_APPROVED", "ASSEMBLED", "EXPORTED"]);

function Progress({ board }: { board: FramesState }) {
  const running = board.jobs.find((j) => j.status === "running");
  const elapsed = useElapsed(running?.started_at, running !== undefined);
  if (!running) return board.jobs.length > 0 ? <p>Waiting for the image engine</p> : null;
  const index = Number(running.payload["index"] ?? 1);
  const total = Number(running.payload["total"] ?? board.jobs.length);
  return <p>{`Generating frame ${index} of ${total} - ${elapsed} s elapsed`}</p>;
}

export function FrameBoard({
  projectId,
  onBack,
  onContinue,
}: {
  projectId: string;
  onBack?: () => void;
  onContinue?: () => void;
}) {
  const frames = useFrames(projectId);
  const generate = useGenerateFrames(projectId);
  const cancel = useCancelFrames(projectId);

  if (!frames.data) return null;
  const board = frames.data;
  const error = generate.error?.message ?? cancel.error?.message;

  return (
    <section aria-label="Key frames">
      <h2>Key frames</h2>
      <div className="actions">
        <button type="button" onClick={onBack}>
          Back to voices
        </button>
        <button type="button" onClick={() => generate.mutate({ mode: "missing" })}>
          Generate all frames
        </button>
        {board.stale_count > 0 ? (
          <button type="button" onClick={() => generate.mutate({ mode: "stale" })}>
            Regenerate stale items
          </button>
        ) : null}
        {board.jobs.length > 0 ? (
          <button type="button" onClick={() => cancel.mutate()}>
            Cancel
          </button>
        ) : null}
        <span>{`${board.approved_count} of ${board.total} frames approved`}</span>
      </div>
      <Progress board={board} />
      {error ? <p role="alert">{error}</p> : null}
      <ul aria-label="Frames" className="list">
        {board.frames.map((frame) => (
          <FrameCard key={frame.scene_id} projectId={projectId} frame={frame} />
        ))}
      </ul>
      <div className="actions">
        <button type="button" disabled={!FRAMES_DONE.has(board.stage)} onClick={onContinue}>
          Continue to shots
        </button>
      </div>
    </section>
  );
}
