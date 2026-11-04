import { useState } from "react";
import type { AssemblyState } from "@/api/assembly";
import { useExport } from "@/api/assembly";
import { LicenceDialog } from "./LicenceDialog";

export function ExportPanel({ projectId, state }: { projectId: string; state: AssemblyState }) {
  const exporter = useExport(projectId);
  const [asking, setAsking] = useState(false);
  const { export: exp, preview } = state;
  const running = exp.state === "running";
  const disabled = running || preview.state === "rebuilding" || state.blocked_reason !== null || exporter.isPending;
  const latest = state.versions.at(-1);

  const start = () => {
    if (state.licence_warnings.length > 0) setAsking(true);
    else exporter.mutate(false);
  };

  return (
    <section aria-label="Export">
      <h3>Export</h3>
      <div className="actions">
        <button type="button" disabled={disabled} onClick={start}>
          Export final
        </button>
      </div>
      {state.blocked_reason ? <p className="notice amber">{state.blocked_reason}</p> : null}
      {running ? (
        <p>
          {exp.step && exp.step_index && exp.step_total
            ? `Exporting: ${exp.step} (${exp.step_index} of ${exp.step_total})`
            : "Exporting..."}
        </p>
      ) : null}
      {exp.state === "failed" ? (
        <div className="notice error">
          <p>{`Export failed at ${exp.failed_step ?? "an unknown step"}. ${exp.error ?? ""}`.trim()}</p>
          <button type="button" disabled={disabled} onClick={start}>
            Retry
          </button>
        </div>
      ) : null}
      {exp.state === "idle" && latest ? <p className="notice green">{`Exported reel v${latest.version}`}</p> : null}
      {exporter.error ? <p role="alert">{exporter.error.message}</p> : null}
      {asking ? (
        <LicenceDialog
          warnings={state.licence_warnings}
          onCancel={() => setAsking(false)}
          onExport={() => {
            setAsking(false);
            exporter.mutate(true);
          }}
        />
      ) : null}
    </section>
  );
}
