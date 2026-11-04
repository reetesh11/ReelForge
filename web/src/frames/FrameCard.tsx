import { useState } from "react";
import {
  useFrameAction,
  useGenerateFrame,
  useUploadFrame,
  type Frame,
  type Framing,
} from "@/api/frames";

const BADGES: Record<string, string> = {
  no_frame: "No frame yet",
  queued: "Queued",
  rendering: "Rendering",
  ready: "Ready",
  approved: "Approved",
  stale: "Needs update",
  continue_previous: "Continue from previous",
};

const FRAMINGS: Array<{ value: Framing; label: string }> = [
  { value: "wide", label: "Wide" },
  { value: "medium", label: "Medium" },
  { value: "closeup", label: "Closeup" },
];

export function FrameCard({ projectId, frame }: { projectId: string; frame: Frame }) {
  const action = useFrameAction(projectId);
  const generate = useGenerateFrame(projectId);
  const upload = useUploadFrame(projectId);
  const [draft, setDraft] = useState(frame.prompt);
  const [seen, setSeen] = useState(frame.prompt);
  if (seen !== frame.prompt) {
    setSeen(frame.prompt);
    setDraft(frame.prompt);
  }

  const active = frame.takes.find((t) => t.active);
  const busy = frame.state === "queued" || frame.state === "rendering";
  const notes = frame.notes;
  const blocked = notes.needs_master !== undefined || notes.no_character === true || frame.continue_previous;
  const error = [action, generate, upload].map((m) => m.error?.message).find((m) => m !== undefined);
  const names = frame.characters.map((c) => c.name).join(", ");
  const run = () => generate.mutate(frame.scene_id);
  const savePrompt = (regenerate: boolean) =>
    action.mutate({ sceneId: frame.scene_id, name: "save-prompt", body: { prompt: draft, regenerate } });

  return (
    <li role="group" aria-label={`Scene ${frame.scene_id}`} className="card">
      <header className="editor-header">
        <strong>{frame.scene_id}</strong>
        {names ? <span className="meta">{names}</span> : null}
        <span className="meta">{`${frame.takes.length} ${frame.takes.length === 1 ? "take" : "takes"}`}</span>
        {BADGES[frame.state] ? (
          <span
            className={frame.state === "stale" ? "badge amber" : frame.state === "approved" ? "badge green" : "badge"}
          >
            {BADGES[frame.state]}
          </span>
        ) : null}
      </header>

      {active ? (
        <img src={active.image_url} alt={`Key frame for scene ${frame.scene_id}`} width={180} />
      ) : null}

      {notes.second_character ? (
        <p className="meta">
          {`Built from ${notes.second_character.master_name}'s master. ${notes.second_character.other_name} is described in the prompt, not copied. Use Upload replacement if the second character looks wrong.`}
        </p>
      ) : null}
      {notes.product === "included" ? <p className="meta">Product pack included</p> : null}
      {notes.product === "missing" ? <p className="notice amber">Product image missing</p> : null}
      {notes.waiting_for_previous_shot ? <p className="meta">Waiting for the previous shot to be rendered</p> : null}
      {notes.needs_master ? <p className="notice amber">{`Approve a master for ${notes.needs_master} in Cast first`}</p> : null}
      {notes.no_character ? <p className="meta">No character in this scene</p> : null}
      {frame.look_removed ? (
        <p className="notice amber">The character description was removed from the prompt.</p>
      ) : null}

      {frame.state === "failed" ? (
        <div className="notice error">
          <p>Couldn't generate this frame.</p>
          {frame.message ? <p className="meta">{frame.message}</p> : null}
          <button type="button" onClick={run}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="actions">
        <label className="field">
          Framing
          <select
            aria-label="Framing"
            value={frame.framing}
            onChange={(e) =>
              action.mutate({ sceneId: frame.scene_id, name: "set-framing", body: { framing: e.target.value } })
            }
          >
            {FRAMINGS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        {frame.takes.length > 0 ? (
          <label className="field">
            Takes
            <select
              aria-label="Takes"
              value={active?.id ?? ""}
              onChange={(e) =>
                action.mutate({ sceneId: frame.scene_id, name: "select-take", body: { take_id: e.target.value } })
              }
            >
              {frame.takes.map((t) => (
                <option key={t.id} value={t.id}>
                  {`Take ${t.take_no}${t.active ? " - Active" : ""}`}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      <label className="field">
        Frame prompt
        <textarea aria-label="Frame prompt" rows={4} value={draft} onChange={(e) => setDraft(e.target.value)} />
      </label>
      <div className="actions">
        <button type="button" disabled={!draft.trim()} onClick={() => savePrompt(false)}>
          Save prompt
        </button>
        <button type="button" disabled={!draft.trim() || busy || blocked} onClick={() => savePrompt(true)}>
          Save and regenerate
        </button>
        <button type="button" disabled={busy || blocked} onClick={run}>
          {active ? "Regenerate" : "Generate"}
        </button>
        <button
          type="button"
          disabled={!active || frame.state === "approved" || frame.state === "stale" || busy}
          onClick={() => action.mutate({ sceneId: frame.scene_id, name: "approve" })}
        >
          Approve
        </button>
        <button
          type="button"
          aria-pressed={frame.continue_previous}
          onClick={() =>
            action.mutate({
              sceneId: frame.scene_id,
              name: "continue-previous",
              body: { enabled: !frame.continue_previous },
            })
          }
        >
          Continue from previous
        </button>
        <label className="field">
          Upload replacement
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate({ sceneId: frame.scene_id, file });
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </li>
  );
}
