import type { StageInfo, StageState } from "@/api/queries";
import { Icon, type IconName } from "@/components/icons";

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

const STAGE_ICONS: Record<string, IconName> = {
  story: "story",
  cast: "cast",
  voices: "voices",
  frames: "frames",
  shots: "shots",
  assembly: "assembly",
};

type Props = {
  stages: StageInfo[];
  current?: string;
  onSelect?: (key: string) => void;
  hrefFor?: (key: string) => string;
};

/** The stage rail: six equal cells, each a link when unlocked. */
export function StageStepper({ stages, current, onSelect, hrefFor = (key) => `?stage=${key}` }: Props) {
  return (
    <ol aria-label="Stages" className="stage-rail">
      {stages.map((stage, index) => {
        const icon = STAGE_ICONS[stage.key];
        const body = (
          <>
            <span className="stage-name" data-testid="stage-name" title={stage.label}>
              {icon ? <Icon name={icon} className="stage-icon" /> : <span className="stage-icon">{index + 1}</span>}
              <span className="stage-label">{stage.label}</span>
            </span>
            <span className="stage-state" data-testid="stage-state">
              {badgeText(stage)}
            </span>
            {stage.state === "rendering" && stage.progress !== null ? (
              <span className="stage-mini-bar" aria-hidden="true">
                <span style={{ width: `${stage.progress}%` }} />
              </span>
            ) : null}
          </>
        );
        return (
          <li
            key={stage.key}
            className="stage-cell"
            data-state={stage.state}
            aria-disabled={stage.locked ? "true" : undefined}
          >
            {stage.locked ? (
              <div className="stage-body">{body}</div>
            ) : (
              <a
                href={hrefFor(stage.key)}
                aria-current={current === stage.key ? "step" : undefined}
                onClick={(event) => {
                  if (!onSelect || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                  event.preventDefault();
                  onSelect(stage.key);
                }}
              >
                {body}
              </a>
            )}
          </li>
        );
      })}
    </ol>
  );
}
