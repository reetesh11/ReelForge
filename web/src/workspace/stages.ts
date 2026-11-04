import type { Project } from "@/api/queries";
import { badgeText, type StageInfo } from "@/components/StageStepper";

export type StageKey = "story" | "cast" | "voices" | "frames" | "shots" | "assembly";

export const STAGE_KEYS: readonly StageKey[] = ["story", "cast", "voices", "frames", "shots", "assembly"];

const isStageKey = (value: string | null): value is StageKey => STAGE_KEYS.includes(value as StageKey);

/** The stage a project opens on, from its overall stage. */
export function landingStage(projectStage: Project["stage"]): StageKey {
  switch (projectStage) {
    case "DRAFT":
      return "story";
    case "STORY_APPROVED":
      return "cast";
    case "CAST_APPROVED":
      return "voices";
    case "VOICES_APPROVED":
      return "frames";
    case "FRAMES_APPROVED":
      return "shots";
    default:
      return "assembly";
  }
}

/** `stage` wins over legacy `screen`; unknown or locked values fall back to the landing stage. */
export function resolveStage(
  params: URLSearchParams,
  projectStage: Project["stage"],
  stages: StageInfo[] | undefined,
): StageKey {
  const wanted = params.get("stage") ?? params.get("screen");
  if (!isStageKey(wanted)) return landingStage(projectStage);
  const info = stages?.find((s) => s.key === wanted);
  if (info?.locked) return landingStage(projectStage);
  return wanted;
}

const ATTENTION = new Set(["needs_review", "failed", "stale"]);

/** The stage that needs the person next: attention states first, then the first unfinished one. */
export function waitingStage(stages: StageInfo[]): StageInfo | null {
  const open = stages.filter((s) => !s.locked);
  return open.find((s) => ATTENTION.has(s.state)) ?? open.find((s) => s.state !== "approved") ?? null;
}

export function approvedCount(stages: StageInfo[]): number {
  return stages.filter((s) => s.state === "approved").length;
}

export function waitingReason(stage: StageInfo): string {
  switch (stage.state) {
    case "needs_review":
      return `${stage.label} needs review`;
    case "failed":
      return `${stage.label} failed`;
    case "stale":
      return `${stage.label} is stale`;
    case "not_started":
      return `${stage.label} not started`;
    default:
      return `${stage.label} ${badgeText(stage).toLowerCase()}`;
  }
}
