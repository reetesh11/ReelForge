import { useState } from "react";
import type { AssemblyState } from "@/api/assembly";
import { useExport } from "@/api/assembly";
import { ActionBar } from "@/components/ActionBar";
import { Notice } from "@/components/Notice";
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
      <ActionBar
        cta={
          <button type="button" className="btn btn-cta" disabled={disabled} onClick={start}>
            Export final
          </button>
        }
      />
      {state.blocked_reason ? <Notice tone="warning">{state.blocked_reason}</Notice> : null}
      {running ? (
        <p>
          {exp.step && exp.step_index && exp.step_total
            ? `Exporting: ${exp.step} (${exp.step_index} of ${exp.step_total})`
            : "Exporting..."}
        </p>
      ) : null}
      {exp.state === "failed" ? (
        <Notice tone="error">
          <p>{`Export failed at ${exp.failed_step ?? "an unknown step"}. ${exp.error ?? ""}`.trim()}</p>
          <button type="button" className="btn btn-secondary" disabled={disabled} onClick={start}>
            Retry
          </button>
        </Notice>
      ) : null}
      {exp.state === "idle" && latest ? <Notice tone="success">{`Exported reel v${latest.version}`}</Notice> : null}
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
