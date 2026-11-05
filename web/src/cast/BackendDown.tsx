const STEPS = [
  "Install Draw Things from the Mac App Store.",
  "Open it and turn on the HTTP API server in settings.",
  "Set the port to 7860 and keep the app open.",
  "Click Retry.",
];

export function BackendDown({
  port,
  mfluxAvailable,
  onRetry,
  onUseMflux,
}: {
  port: number;
  mfluxAvailable: boolean;
  onRetry: () => void;
  onUseMflux: () => void;
}) {
  return (
    <div className="notice error">
      <h3>{`Draw Things isn't reachable on port ${port}`}</h3>
      <ol>
        {STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <div className="actions">
        <button type="button" className="btn btn-primary" onClick={onRetry}>
          Retry
        </button>
        {mfluxAvailable ? (
          <button type="button" className="btn btn-secondary" onClick={onUseMflux}>
            Use mflux instead
          </button>
        ) : null}
      </div>
    </div>
  );
}
