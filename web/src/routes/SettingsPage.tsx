import { useHealth, type HealthReport } from "@/api/queries";

type Check = HealthReport["checks"][number];
type Colour = "green" | "amber" | "red";

const DEPENDENCIES: Array<{ label: string; check: string }> = [
  { label: "Draw Things", check: "draw_things" },
  { label: "ltx-2-mlx", check: "ltx" },
  { label: "mlx-audio", check: "mlx_audio" },
  { label: "Local LLM", check: "ollama" },
  { label: "ffmpeg", check: "ffmpeg_filters" },
];

export function colourOf(check: Check): Colour {
  if (check.status === "pass") return "green";
  return check.severity === "warning" ? "amber" : "red";
}

export function SettingsPage() {
  const health = useHealth();

  return (
    <section>
      <h1>Settings &amp; status</h1>
      {health.isPending ? (
        <p>Checking dependencies...</p>
      ) : health.isError ? (
        <div>
          <p>Couldn't load status.</p>
          <button type="button" onClick={() => void health.refetch()}>
            Retry
          </button>
        </div>
      ) : (
        <ul aria-label="Dependencies" className="list">
          {DEPENDENCIES.flatMap(({ label, check }) => {
            const result = health.data.checks.find((c) => c.name === check);
            if (!result) return [];
            const colour = colourOf(result);
            return [
              <li key={check} aria-label={`${label}: ${colour}`} className="row">
                <span>
                  <span className={`dot ${colour}`} aria-hidden="true" />
                  {label}
                </span>
                <span className="meta">{result.detail}</span>
                {colour !== "green" && result.fix ? <span>{`Fix: ${result.fix}`}</span> : null}
              </li>,
            ];
          })}
        </ul>
      )}
    </section>
  );
}
