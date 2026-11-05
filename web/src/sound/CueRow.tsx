import { useState } from "react";
import type { Cue, CueAction, CueState } from "@/api/audio";
import { TakesList } from "./TakesList";

const BADGES: Record<CueState, string> = {
  suggested: "Suggested",
  draft: "Draft",
  ready: "Ready",
  stale: "Needs update",
};

const seconds = (n: number) => `${Number(n.toFixed(2))} s`;

export function CueRow({
  cue,
  first,
  last,
  engineOk,
  onAction,
  onEdit,
  onDelete,
  onPlay,
}: {
  cue: Cue;
  first: boolean;
  last: boolean;
  engineOk: boolean;
  onAction: (action: CueAction) => void;
  onEdit: () => void;
  onDelete: () => void;
  onPlay: (url: string) => void;
}) {
  const [showTakes, setShowTakes] = useState(false);
  const silence = cue.kind === "silence";
  const fromFile = cue.source === "file";
  const picked = cue.takes.find((t) => t.id === cue.picked_take_id);
  const job = cue.job;
  const busy = job?.status === "queued" || job?.status === "running";
  const generateLabel = cue.takes.length > 0 ? `Re-take ${cue.id}` : `Generate ${cue.id}`;
  const canGenerate = engineOk && !busy && cue.state !== "suggested";

  return (
    <li aria-label={`Cue ${cue.id}`} className="card">
      <header className="editor-header">
        <strong>{cue.order}</strong>
        <span className="meta">{cue.kind}</span>
        <strong>{cue.id}</strong>
        {silence ? null : <span className="meta">{fromFile ? "File" : "Generate"}</span>}
        <span className="meta">{seconds(cue.start_s)}</span>
        <span className="meta">{seconds(cue.duration_s)}</span>
        <span className={cue.state === "stale" ? "badge amber" : cue.state === "ready" ? "badge green" : "badge"}>
          {BADGES[cue.state]}
        </span>
        {cue.licence ? <span className="meta">{cue.licence}</span> : null}
      </header>
      {cue.prompt && !silence ? <p className="meta">{cue.prompt}</p> : null}
      {cue.file_name ? <p className="meta">{cue.file_name}</p> : null}
      {cue.flags?.includes("ends_after_reel") ? <p className="notice amber">Ends after the reel.</p> : null}
      {busy ? <p role="status">{`Generating... ${job?.progress ?? 0}%`}</p> : null}
      {job?.status === "failed" ? <p role="alert">{job.error ?? "Generating failed."}</p> : null}

      <div className="actions">
        <button type="button" aria-label={`Edit cue ${cue.id}`} onClick={onEdit}>
          Edit
        </button>
        <button type="button" aria-label={`Delete cue ${cue.id}`} onClick={onDelete}>
          Delete
        </button>
        <button
          type="button"
          aria-label={`Move cue ${cue.id} up`}
          disabled={first}
          onClick={() => onAction({ name: "move", id: cue.id, direction: "up" })}
        >
          Up
        </button>
        <button
          type="button"
          aria-label={`Move cue ${cue.id} down`}
          disabled={last}
          onClick={() => onAction({ name: "move", id: cue.id, direction: "down" })}
        >
          Down
        </button>
        {picked ? (
          <button type="button" aria-label={`Play ${cue.id}`} onClick={() => onPlay(picked.url)}>
            Play
          </button>
        ) : null}
        {!silence && !fromFile ? (
          <button
            type="button"
            aria-label={generateLabel}
            disabled={!canGenerate}
            onClick={() => onAction({ name: "generate", id: cue.id })}
          >
            {cue.takes.length > 0 ? "Re-take" : "Generate"}
          </button>
        ) : null}
        {cue.takes.length > 0 ? (
          <button type="button" aria-label={`Takes for ${cue.id}`} onClick={() => setShowTakes((v) => !v)}>
            Takes
          </button>
        ) : null}
        {fromFile && !silence ? (
          <label className="field">
            Upload file
            <input
              type="file"
              accept="audio/*"
              aria-label={`Upload file for ${cue.id}`}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onAction({ name: "upload", id: cue.id, file });
                e.target.value = "";
              }}
            />
          </label>
        ) : null}
        {cue.state === "suggested" ? (
          <>
            <button type="button" onClick={() => onAction({ name: "approve", id: cue.id })}>
              Approve
            </button>
            <button type="button" onClick={() => onAction({ name: "dismiss", id: cue.id })}>
              Dismiss
            </button>
          </>
        ) : null}
      </div>
      {showTakes && cue.takes.length > 0 ? (
        <TakesList
          cueId={cue.id}
          takes={cue.takes}
          onPlay={onPlay}
          onUse={(takeId) => onAction({ name: "select-take", id: cue.id, takeId })}
        />
      ) : null}
    </li>
  );
}
