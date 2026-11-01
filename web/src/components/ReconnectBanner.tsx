export function ReconnectBanner({ connected }: { connected: boolean }) {
  if (connected) return null;
  return (
    <div role="status" className="banner">
      Reconnecting...
    </div>
  );
}
