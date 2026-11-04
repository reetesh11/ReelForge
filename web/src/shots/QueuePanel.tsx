import { useQueueAction, useShotAction, type Queue } from "@/api/shots";
import { useElapsed } from "@/components/useElapsed";

const TYPE_LABELS = { talking: "Talking", action: "Action", continue: "Continue" } as const;
const QUALITY_LABELS = { draft: "Draft", final: "Final" } as const;

export function QueuePanel({ projectId, queue }: { projectId: string; queue: Queue }) {
  const act = useQueueAction(projectId);
  const running = queue.running;
  const elapsed = useElapsed(null, running !== null, running?.elapsed_s ?? 0);
  if (queue.rows.length === 0) return null;
  const queuedIds = queue.rows.filter((r) => r.can_move).map((r) => r.job_id);
  return (
    <section aria-label="Render queue" className="card">
      <p>{queue.total_text}</p>
      {running ? <p>{`Rendering shot ${running.index} of ${running.total} - ${elapsed} s elapsed`}</p> : null}
      <ul className="list">
        {queue.rows.map((row) => (
          <li key={row.job_id}>
            <span>{`${row.position}. ${row.scene_id} - ${TYPE_LABELS[row.shot_type]} - ${QUALITY_LABELS[row.quality]} - ${row.estimate_text}`}</span>
            <span className="actions">
              <button
                type="button"
                disabled={!row.can_move || queuedIds[0] === row.job_id}
                onClick={() => act.mutate({ name: "move", body: { job_id: row.job_id, direction: "up" } })}
              >
                Move up
              </button>
              <button
                type="button"
                disabled={!row.can_move || queuedIds[queuedIds.length - 1] === row.job_id}
                onClick={() => act.mutate({ name: "move", body: { job_id: row.job_id, direction: "down" } })}
              >
                Move down
              </button>
              <RemoveButton projectId={projectId} sceneId={row.scene_id} disabled={!row.can_move} />
            </span>
          </li>
        ))}
      </ul>
      <div className="actions">
        <button type="button" onClick={() => act.mutate({ name: queue.paused ? "resume" : "pause" })}>
          {queue.paused ? "Resume" : "Pause"}
        </button>
        <button type="button" onClick={() => act.mutate({ name: "cancel" })}>
          Cancel
        </button>
      </div>
      {act.error ? <p role="alert">{act.error.message}</p> : null}
    </section>
  );
}

function RemoveButton({ projectId, sceneId, disabled }: { projectId: string; sceneId: string; disabled: boolean }) {
  const action = useShotAction(projectId);
  return (
    <button type="button" disabled={disabled} onClick={() => action.mutate({ sceneId, name: "dequeue" })}>
      Remove
    </button>
  );
}
