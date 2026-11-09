import type { ReactNode } from "react";

/** Sticky bar at the foot of a stage panel: status on the left, the one CTA on the right. */
export function ActionBar({ left, cta }: { left?: ReactNode; cta?: ReactNode }) {
  return (
    <div className="action-bar" data-testid="action-bar">
      <div className="action-left">{left}</div>
      <div className="action-cta">{cta}</div>
    </div>
  );
}
