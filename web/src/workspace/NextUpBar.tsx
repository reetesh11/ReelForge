import type { StageInfo } from "@/components/StageStepper";
import { waitingReason, waitingStage, type StageKey } from "@/workspace/stages";

/** Points to the stage that needs the person, unless they are already on it. */
export function NextUpBar({
  shown,
  stages,
  onGo,
}: {
  shown: StageKey;
  stages: StageInfo[];
  onGo: (key: StageKey) => void;
}) {
  const waiting = waitingStage(stages);
  if (!waiting || waiting.key === shown) return null;
  return (
    <div className="next-up" data-testid="next-up">
      <span>{waitingReason(waiting)}</span>
      <button type="button" className="btn btn-secondary" data-leave-guard onClick={() => onGo(waiting.key as StageKey)}>
        {`Go to ${waiting.label}`}
      </button>
    </div>
  );
}
