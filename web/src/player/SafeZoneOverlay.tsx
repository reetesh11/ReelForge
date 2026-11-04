// The vertical-video safe zone on a 1080x1920 frame: 250 px top and bottom, 64 px left and right.
const TOP_BOTTOM = (250 / 1920) * 100;
const SIDES = (64 / 1080) * 100;

export function SafeZoneOverlay() {
  return (
    <div
      data-testid="safe-zone-overlay"
      className="safe-zone-overlay"
      aria-hidden="true"
      style={{ top: `${TOP_BOTTOM}%`, bottom: `${TOP_BOTTOM}%`, left: `${SIDES}%`, right: `${SIDES}%` }}
    />
  );
}
