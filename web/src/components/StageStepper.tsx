import type { StageInfo, StageState } from "@/api/queries";

export type { StageInfo };

const BADGES: Record<StageState, string> = {
  not_started: "Not started",
  queued: "Queued",
  rendering: "Rendering",
  needs_review: "Needs review",
  approved: "Approved",
  stale: "Stale",
  failed: "Failed",
};

export function badgeText(stage: StageInfo): string {
  if (stage.state === "rendering" && stage.progress !== null) {
    return `Rendering ${stage.progress}%`;
  }
  return BADGES[stage.state];
}

export function StageStepper({ stages }: { stages: StageInfo[] }) {
  return (
    <ol aria-label="Stages" className="stepper">
      {stages.map((stage) => (
        <li key={stage.key} aria-disabled={stage.locked ? "true" : undefined}>
          <strong>{stage.label}</strong>
          <span className="badge">{badgeText(stage)}</span>
        </li>
      ))}
    </ol>
  );
}
