import { useRenderAll, useShots } from "@/api/shots";
import { QueuePanel } from "./QueuePanel";
import { ShotCard } from "./ShotCard";

const SHOTS_DONE = new Set(["SHOTS_APPROVED", "ASSEMBLED", "EXPORTED"]);

export function ShotBoard({
  projectId,
  onBack,
}: {
  projectId: string;
  onBack?: () => void;
}) {
  const shots = useShots(projectId);
  const renderAll = useRenderAll(projectId);

  if (!shots.data) return null;
  const board = shots.data;
  const engineOk = board.engine.ok;
  const error = renderAll.error?.message;

  return (
    <section aria-label="Shots">
      <h2>Shots</h2>
      <div className="actions">
        <button type="button" onClick={onBack}>
          Back to key frames
        </button>
        <button type="button" disabled={!engineOk} onClick={() => renderAll.mutate("missing")}>
          Render all
        </button>
        {board.stale_count > 0 ? (
          <button type="button" disabled={!engineOk} onClick={() => renderAll.mutate("stale")}>
            Regenerate stale items
          </button>
        ) : null}
        <span>{`${board.approved_count} of ${board.total} shots approved`}</span>
      </div>
      {!engineOk ? (
        <p className="notice error">{board.engine.message || "Video engine check failed - see Settings & status"}</p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      <QueuePanel projectId={projectId} queue={board.queue} />
      <ul aria-label="Shot cards" className="list">
        {board.shots.map((shot) => (
          <ShotCard key={shot.scene_id} projectId={projectId} shot={shot} engineOk={engineOk} />
        ))}
      </ul>
      <div className="actions">
        <button type="button" disabled={!SHOTS_DONE.has(board.stage)}>
          Continue to assembly
        </button>
      </div>
    </section>
  );
}
