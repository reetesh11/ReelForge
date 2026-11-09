import { useHealth, type HealthReport } from "@/api/queries";
import { useSetVoiceModel, useVoiceModel } from "@/api/voice";

type Check = HealthReport["checks"][number];
type Colour = "green" | "amber" | "red";

const WORDS: Record<Colour, string> = { green: "Ready", amber: "Warning", red: "Missing" };

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

function VoiceModelSection() {
  const model = useVoiceModel();
  const change = useSetVoiceModel();
  if (!model.data) return null;
  const { voice_model: current, label, model_id: modelId, choices } = model.data;
  return (
    <div className="card">
      <label className="field">
        Voice model
        <select value={current} onChange={(e) => change.mutate(e.target.value)}>
          {choices.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <p className="meta">{`Voice model: ${label} (${modelId})`}</p>
      {change.isError ? <p role="alert">{change.error.message}</p> : null}
    </div>
  );
}

export function SettingsPage() {
  const health = useHealth();

  return (
    <section>
      <h1>Settings &amp; status</h1>
      {health.isPending ? (
        <p className="state-message">Checking dependencies...</p>
      ) : health.isError ? (
        <div>
          <p className="state-message error">Couldn't load status.</p>
          <button type="button" className="btn btn-secondary" onClick={() => void health.refetch()}>
            Retry
          </button>
        </div>
      ) : (
        <ul aria-label="Dependencies" className="status-cards">
          {DEPENDENCIES.flatMap(({ label, check }) => {
            const result = health.data.checks.find((c) => c.name === check);
            if (!result) return [];
            const colour = colourOf(result);
            return [
              <li key={check} aria-label={`${label}: ${colour}`} className="status-card">
                <strong>{label}</strong>
                <span className="status-word">
                  <span className={`dot ${colour}`} aria-hidden="true" />
                  {WORDS[colour]}
                </span>
                <span className="meta">{result.detail}</span>
                {colour !== "green" && result.fix ? <span>{`Fix: ${result.fix}`}</span> : null}
              </li>,
            ];
          })}
          {health.data.image_licence_warning ? (
            <li aria-label="Image model licence: amber" className="status-card">
              <strong>Image model licence</strong>
              <span className="status-word">
                <span className="dot amber" aria-hidden="true" />
                Warning
              </span>
              <span className="meta">{health.data.image_licence_warning}</span>
            </li>
          ) : null}
        </ul>
      )}
      <VoiceModelSection />
    </section>
  );
}
