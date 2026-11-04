import { useEffect, useRef, useState } from "react";
import {
  useAssembly,
  useAssemblyEdit,
  useBuildAssembly,
  useOpenVersion,
  useRebuildPreview,
  type Preview,
} from "@/api/assembly";
import { Player } from "@/player/Player";
import { CaptionEditor } from "./CaptionEditor";
import { ExportPanel } from "./ExportPanel";
import { Timeline } from "./Timeline";

function previewBadge(p: Preview): string {
  switch (p.state) {
    case "up_to_date":
      return "Preview up to date";
    case "pending":
    case "out_of_date":
      return p.rebuild_in_s === null ? "Out of date" : `Out of date - rebuilding in ${Math.max(1, Math.ceil(p.rebuild_in_s))} s`;
    case "rebuilding":
      return `Rebuilding preview: ${p.step ?? "Starting"} (${p.progress ?? 0}%)`;
    case "failed":
      return "Preview failed - Retry";
    default:
      return "No preview yet";
  }
}

const WORKING = "working";

export function AssemblyScreen({ projectId, onBack }: { projectId: string; onBack: () => void }) {
  const assembly = useAssembly(projectId);
  const build = useBuildAssembly(projectId);
  const edit = useAssemblyEdit(projectId);
  const rebuild = useRebuildPreview(projectId);
  const open = useOpenVersion(projectId);
  const [version, setVersion] = useState(WORKING);
  const [notes, setNotes] = useState<string[]>([]);
  const built = useRef(false);

  const state = assembly.data;
  const needsBuild = state !== undefined && state.edl === null && state.blocked_reason === null;
  useEffect(() => {
    if (needsBuild && !built.current) {
      built.current = true;
      build.mutate(false);
    }
  }, [needsBuild, build]);

  if (assembly.isError) {
    return (
      <section aria-label="Assembly">
        <h2>Assembly</h2>
        <button type="button" onClick={onBack}>
          Back to Shots
        </button>
        <p role="alert">{assembly.error.message}</p>
      </section>
    );
  }
  if (!state) return null;

  const chosen = state.versions.find((v) => String(v.version) === version);
  const src = chosen && !chosen.missing ? chosen.reel_url : version === WORKING ? state.preview.url : null;
  const editError = edit.error?.message ?? open.error?.message ?? rebuild.error?.message ?? build.error?.message;
  const preview = state.preview;

  const send = (op: Parameters<typeof edit.mutate>[0]) => {
    edit.mutate(op, { onSuccess: (out) => setNotes(out.notes), onError: () => setNotes([]) });
  };

  return (
    <section aria-label="Assembly">
      <h2>Assembly</h2>
      <div className="actions">
        <button type="button" onClick={onBack}>
          Back to Shots
        </button>
        <label className="field">
          <span className="meta">Version</span>
          <select
            aria-label="Version"
            value={version}
            onChange={(e) => {
              const next = e.target.value;
              setVersion(next);
              const picked = state.versions.find((v) => String(v.version) === next);
              if (picked && !picked.missing) open.mutate(picked.version);
            }}
          >
            <option value={WORKING}>Editing: working copy</option>
            {state.versions.map((v) => (
              <option key={v.version} value={String(v.version)}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        {chosen?.missing ? <span role="status">This version's files are missing.</span> : null}
      </div>

      <div className="actions">
        {preview.state === "failed" ? (
          <button type="button" onClick={() => rebuild.mutate()}>
            {previewBadge(preview)}
          </button>
        ) : (
          <span className="badge">{previewBadge(preview)}</span>
        )}
        <button type="button" disabled={preview.state === "rebuilding"} onClick={() => rebuild.mutate()}>
          Rebuild preview
        </button>
      </div>
      {preview.state === "failed" && preview.error ? <p className="notice error">{preview.error}</p> : null}

      {src ? <Player src={src} label="Reel" /> : <p className="meta">No preview yet.</p>}

      {editError ? <p role="alert">{editError}</p> : null}
      {notes.map((n) => (
        <p key={n} className="meta">
          {n}
        </p>
      ))}

      {state.edl ? (
        <>
          <Timeline edl={state.edl} shots={state.shots} onEdit={send} />
          <CaptionEditor
            edl={state.edl}
            status={state.caption_status}
            presets={state.caption_presets}
            rebuilding={preview.state === "rebuilding"}
            onEdit={send}
          />
        </>
      ) : null}
      <ExportPanel projectId={projectId} state={state} />
    </section>
  );
}
