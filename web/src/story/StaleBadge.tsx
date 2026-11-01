export function StaleBadge({ show }: { show: boolean }) {
  return show ? <span className="badge amber">needs update</span> : null;
}
