import type { ReactNode } from "react";

export type ChipTone = "green" | "amber" | "red" | "blue" | "grey";

export function Chip({ tone = "grey", testId, children }: { tone?: ChipTone; testId?: string; children: ReactNode }) {
  return (
    <span className={`chip chip-${tone}`} data-testid={testId}>
      {children}
    </span>
  );
}
