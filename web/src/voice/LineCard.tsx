import { useState } from "react";
import {
  previewUrl,
  useGenerateVoices,
  useLineAction,
  useShorten,
  useUploadRecording,
  type VoiceLine,
} from "@/api/voice";

const BADGES: Record<string, string> = {
  no_take: "No take yet",
  queued: "Queued",
  rendering: "Rendering",
  ready: "Ready",
  approved: "Approved",
  stale: "Needs update",
};

const seconds = (value: number | null | undefined): string =>
  value === null || value === undefined ? "" : `${value.toFixed(1)} s`;

export function LineCard({
  projectId,
  line,
  recorded,
  onPlay,
}: {
  projectId: string;
  line: VoiceLine;
  recorded: boolean;
  onPlay: (url: string) => void;
}) {
  const action = useLineAction(projectId);
  const generate = useGenerateVoices(projectId);
  const shorten = useShorten(projectId);
  const upload = useUploadRecording(projectId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(line.text);
  const [proposal, setProposal] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const active = line.takes.find((t) => t.active);
  const busy = line.state === "queued" || line.state === "rendering";
  const error = [action, generate, shorten, upload].map((m) => m.error?.message).find((m) => m !== undefined);

  if (line.state === "no_dialogue") {
    return (
      <li role="group" aria-label={`Scene ${line.scene_id}`} className="card">
        <strong>{line.scene_id}</strong>
        <p className="meta">No dialogue</p>
      </li>
    );
  }

  const retake = () => generate.mutate({ mode: "lines", lines: [line.scene_id] });
  const timing = (body: Record<string, unknown>) =>
    action.mutate({ sceneId: line.scene_id, name: "set-timing", body });
  const saveText = (text: string, thenRetake: boolean) => {
    action.mutate(
      { sceneId: line.scene_id, name: "edit-text", body: { text } },
      {
        onSuccess: () => {
          setEditing(false);
          setProposal(null);
          if (thenRetake && !recorded) retake();
        },
      },
    );
  };

  return (
    <li role="group" aria-label={`Scene ${line.scene_id}`} className="card">
      <header className="editor-header">
        <strong>{line.speaker_name ?? "No speaker"}</strong>
        <span className="meta">Hindi</span>
        {line.duration_s !== undefined ? <span className="meta">{seconds(line.duration_s)}</span> : null}
        <span className="meta">{`${line.takes.length} ${line.takes.length === 1 ? "take" : "takes"}`}</span>
        {BADGES[line.state] ? (
          <span className={line.state === "stale" ? "badge amber" : line.state === "approved" ? "badge green" : "badge"}>
            {BADGES[line.state]}
          </span>
        ) : null}
      </header>
      <p>{line.text}</p>

      {line.state === "no_voice" ? <p>{line.message}</p> : null}
      {line.state === "failed" ? (
        <div className="notice error">
          <p>Couldn't generate this line.</p>
          {line.message ? <p className="meta">{line.message}</p> : null}
          <button type="button" onClick={retake}>
            Retry
          </button>
        </div>
      ) : null}

      {line.over_budget ? (
        <div className="notice amber">
          <p>{`This line is ${line.over_budget.line_s.toFixed(1)} s but the scene allows ${line.over_budget.budget_s.toFixed(1)} s.`}</p>
          <div className="actions">
            <button
              type="button"
              onClick={() =>
                action.mutate(
                  { sceneId: line.scene_id, name: "speed-up" },
                  { onSuccess: (r) => setNote(r.message ?? null) },
                )
              }
            >
              Speed up
            </button>
            <button type="button" onClick={() => shorten.mutate(line.scene_id, { onSuccess: setProposal })}>
              Shorten text
            </button>
            <button type="button" onClick={() => action.mutate({ sceneId: line.scene_id, name: "extend-scene" })}>
              Extend scene
            </button>
          </div>
        </div>
      ) : null}
      {note ? <p className="meta">{note}</p> : null}
      {proposal ? (
        <div className="notice">
          <p>{`Shorter: ${proposal}`}</p>
          <div className="actions">
            <button type="button" onClick={() => saveText(proposal, true)}>
              Use this text
            </button>
            <button type="button" onClick={() => setProposal(null)}>
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      {line.takes.length > 0 ? (
        <label className="field">
          Takes
          <select
            value={active?.id ?? ""}
            onChange={(e) =>
              action.mutate({ sceneId: line.scene_id, name: "select-take", body: { take_id: e.target.value } })
            }
          >
            {line.takes.map((t) => (
              <option key={t.id} value={t.id}>
                {`Take ${t.take_no} (${seconds(t.duration_s)})${t.active ? " - Active" : ""}`}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div className="actions">
        <label className="field">
          Speed
          <input
            type="range"
            min={0.8}
            max={1.25}
            step={0.05}
            value={line.speed}
            onChange={(e) => timing({ speed: Number(e.target.value) })}
          />
        </label>
        <output aria-label="Speed value">{`${line.speed.toFixed(2)}x`}</output>
        <label className="field">
          Pause before
          <input
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={line.pause_before}
            onChange={(e) => e.target.value !== "" && timing({ pause_before: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          Pause after
          <input
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={line.pause_after}
            onChange={(e) => e.target.value !== "" && timing({ pause_after: Number(e.target.value) })}
          />
        </label>
      </div>

      {line.frames !== undefined && line.shot_length_s !== undefined ? (
        <p className="meta">
          {`Shot length: ${line.frames} frames (${line.shot_length_s.toFixed(2)} s)`}
          {line.shot_length_stale ? " - out of date" : ""}
        </p>
      ) : null}

      {editing ? (
        <div>
          <label className="field">
            Line text
            <textarea rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} />
          </label>
          <div className="actions">
            <button type="button" disabled={!draft.trim()} onClick={() => saveText(draft, true)}>
              Save and re-take
            </button>
            <button type="button" onClick={() => setEditing(false)}>
              Cancel edit
            </button>
          </div>
        </div>
      ) : null}

      <div className="actions">
        <button type="button" disabled={!active} onClick={() => active && onPlay(active.audio_url)}>
          Play
        </button>
        <button
          type="button"
          disabled={!active || line.state === "approved" || line.state === "stale" || busy}
          onClick={() => action.mutate({ sceneId: line.scene_id, name: "approve" })}
        >
          Approve
        </button>
        {recorded ? (
          <label className="field">
            Upload recording
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload.mutate({ sceneId: line.scene_id, file });
                e.target.value = "";
              }}
            />
          </label>
        ) : (
          <button type="button" disabled={busy || line.state === "no_voice"} onClick={retake}>
            New take
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setDraft(line.text);
            setEditing(true);
          }}
        >
          Edit text and re-take
        </button>
        <button type="button" onClick={() => onPlay(previewUrl(projectId, line.scene_id))}>
          Play scene
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </li>
  );
}
