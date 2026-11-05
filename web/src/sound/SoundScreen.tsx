import { useRef, useState } from "react";
import { CueInvalidError, useAudio, useAudioMutations, type Cue, type CueAction } from "@/api/audio";
import { CueForm } from "./CueForm";
import { CueRow } from "./CueRow";

const EMPTY = "No sound cues yet. Add a cue or let the structuring step suggest some from your storyline.";
const LEGACY = "This story uses the old music note. Add cues to design the sound.";

export function SoundScreen({
  projectId,
  onBack,
  onContinue,
}: {
  projectId: string;
  onBack: () => void;
  onContinue: () => void;
}) {
  const audio = useAudio(projectId);
  const act = useAudioMutations(projectId);
  const [editing, setEditing] = useState<Cue | "new" | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);

  const play = (url: string) => {
    player.current?.pause();
    const el = new Audio(url);
    player.current = el;
    void el.play().catch(() => undefined);
  };
  const run = (action: CueAction) => act.mutate(action);

  if (audio.isError) {
    return (
      <section aria-label="Sound">
        <h2>Sound</h2>
        <button type="button" onClick={onBack}>
          Back
        </button>
        <p role="alert">{audio.error.message}</p>
      </section>
    );
  }
  const state = audio.data;
  if (!state) return null;

  const engineOk = state.engine.ok;
  const error = act.error;
  const formErrors = error instanceof CueInvalidError ? error.errors.map((e) => e.message) : undefined;
  const otherError = error && !(error instanceof CueInvalidError) ? error.message : undefined;
  const hasSuggested = state.cues.some((c) => c.state === "suggested");

  return (
    <section aria-label="Sound">
      <h2>Sound</h2>
      <div className="actions">
        <button type="button" onClick={onBack}>
          Back
        </button>
        <button type="button" onClick={() => setEditing("new")}>
          Add cue
        </button>
        <button type="button" disabled={state.cues.length === 0} onClick={() => run({ name: "preview-mix" })}>
          Preview full mix
        </button>
        {hasSuggested ? (
          <button type="button" onClick={() => run({ name: "approve-all" })}>
            Approve all
          </button>
        ) : null}
        <label className="field">
          Duck amount (dB)
          <input
            type="number"
            min={0}
            max={40}
            step="any"
            key={state.settings.duck_db}
            defaultValue={state.settings.duck_db}
            onBlur={(e) => {
              const value = Number(e.target.value);
              if (e.target.value.trim() !== "" && Number.isFinite(value) && value !== state.settings.duck_db) {
                run({ name: "settings", values: { duck_db: value } });
              }
            }}
          />
        </label>
        <button type="button" onClick={onContinue}>
          Next
        </button>
      </div>
      {!engineOk && state.engine.message ? <p className="notice error">{state.engine.message}</p> : null}
      {state.legacy_music_hint ? <p className="notice amber">{LEGACY}</p> : null}
      {otherError ? <p role="alert">{otherError}</p> : null}
      {state.skipped_count ? (
        <p className="meta">{`${state.skipped_count} cues have no audio and are left out of the mix.`}</p>
      ) : null}

      {editing !== null ? (
        <CueForm
          key={editing === "new" ? "new" : editing.id}
          cue={editing === "new" ? null : editing}
          scenes={state.scenes?.map((s) => s.id) ?? []}
          error={formErrors}
          onSave={(cue) =>
            act.mutate({ name: editing === "new" ? "add" : "update", cue }, { onSuccess: () => setEditing(null) })
          }
          onCancel={() => setEditing(null)}
        />
      ) : null}

      {state.cues.length === 0 ? (
        <p>{EMPTY}</p>
      ) : (
        <ul aria-label="Sound cues" className="list">
          {state.cues.map((cue, i) => (
            <CueRow
              key={cue.id}
              cue={cue}
              first={i === 0}
              last={i === state.cues.length - 1}
              engineOk={engineOk}
              onAction={run}
              onEdit={() => setEditing(cue)}
              onDelete={() => setDeleting(cue.id)}
              onPlay={play}
            />
          ))}
        </ul>
      )}

      {deleting !== null ? (
        <div role="dialog" aria-modal="true" aria-label={`Delete cue ${deleting}?`} className="card">
          <h3>{`Delete cue ${deleting}?`}</h3>
          <p>Its takes stay on disk but the cue leaves the mix.</p>
          <div className="actions">
            <button
              type="button"
              onClick={() => {
                run({ name: "delete", id: deleting });
                setDeleting(null);
              }}
            >
              Delete
            </button>
            <button type="button" onClick={() => setDeleting(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
