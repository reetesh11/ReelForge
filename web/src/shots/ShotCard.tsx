import { useState } from "react";
import {
  useRenderShot,
  useShotAction,
  useUploadClip,
  type Quality,
  type Shot,
  type ShotType,
} from "@/api/shots";
import { Player } from "@/player/Player";
import { CompareTakes } from "./CompareTakes";

const BADGES: Record<string, string> = {
  no_shot: "No shot yet",
  queued: "Queued",
  rendering: "Rendering",
  ready: "Ready",
  approved: "Approved",
  stale: "Needs update",
};
const TYPE_LABELS: Record<ShotType, string> = { talking: "Talking", action: "Action", continue: "Continue" };
const QUALITY_LABELS: Record<Quality, string> = { draft: "Draft", final: "Final" };
const BLOCKER_TEXT = {
  frame_not_approved: "Approve the key frame first",
  voice_not_approved: "Approve the voice take first",
  waiting_previous: "Waiting for the previous shot",
} as const;

export function ShotCard({
  projectId,
  shot,
  engineOk,
}: {
  projectId: string;
  shot: Shot;
  engineOk: boolean;
}) {
  const action = useShotAction(projectId);
  const render = useRenderShot(projectId);
  const upload = useUploadClip(projectId);
  const [draft, setDraft] = useState(shot.motion_prompt);
  const [seen, setSeen] = useState(shot.motion_prompt);
  const [comparing, setComparing] = useState(false);
  if (seen !== shot.motion_prompt) {
    setSeen(shot.motion_prompt);
    setDraft(shot.motion_prompt);
  }

  const active = shot.takes.find((t) => t.active);
  const busy = shot.state === "queued" || shot.state === "rendering";
  const blocked = shot.blockers.length > 0;
  const error = [action, render, upload].map((m) => m.error?.message).find((m) => m !== undefined);
  const go = (name: "render" | "reroll" | "retry-draft") => render.mutate({ sceneId: shot.scene_id, name });
  const canRender = engineOk && !busy && !blocked;

  return (
    <li role="group" aria-label={`Scene ${shot.scene_id}`} className="card">
      <header className="editor-header">
        <strong>{shot.scene_id}</strong>
        <span className="meta">{TYPE_LABELS[shot.shot_type]}</span>
        <span className="meta">{QUALITY_LABELS[shot.quality]}</span>
        <span className="meta">{`${shot.frames} frames (${shot.shot_length_s.toFixed(2)} s)`}</span>
        {BADGES[shot.state] ? (
          <span
            className={shot.state === "stale" ? "badge amber" : shot.state === "approved" ? "badge green" : "badge"}
          >
            {BADGES[shot.state]}
          </span>
        ) : null}
      </header>

      {active ? (
        <Player src={active.video_url} label="Shot video" loop muted width={180} grouped={false} />
      ) : shot.frame_url ? (
        <img src={shot.frame_url} alt={`Key frame for scene ${shot.scene_id}`} width={180} />
      ) : null}

      {shot.blockers.map((b) => (
        <div key={b} className="notice amber">
          <p>{BLOCKER_TEXT[b]}</p>
          {b === "voice_not_approved" ? (
            <button type="button" onClick={() => action.mutate({ sceneId: shot.scene_id, name: "set-type", body: { shot_type: "action" } })}>
              Switch to Action
            </button>
          ) : null}
        </div>
      ))}

      {shot.state === "failed" && shot.oom ? (
        <div className="notice error">
          <p>Killed, likely out of memory.</p>
          {shot.can_retry_draft ? (
            <button type="button" onClick={() => go("retry-draft")}>
              Retry at Draft size
            </button>
          ) : (
            <p className="meta">Close other apps and try again.</p>
          )}
        </div>
      ) : null}
      {shot.state === "failed" && !shot.oom ? (
        <div className="notice error">
          <p>Couldn't render this shot.</p>
          {shot.message ? <p className="meta">{shot.message}</p> : null}
          <button type="button" disabled={!engineOk} onClick={() => go("render")}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="actions">
        <label className="field">
          Shot type
          <select
            aria-label="Shot type"
            value={shot.shot_type}
            onChange={(e) => action.mutate({ sceneId: shot.scene_id, name: "set-type", body: { shot_type: e.target.value } })}
          >
            {(Object.keys(TYPE_LABELS) as ShotType[]).map((t) => (
              <option key={t} value={t}>
                {TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Quality
          <select
            aria-label="Quality"
            value={shot.quality}
            onChange={(e) => action.mutate({ sceneId: shot.scene_id, name: "set-quality", body: { quality: e.target.value } })}
          >
            {(Object.keys(QUALITY_LABELS) as Quality[]).map((q) => (
              <option key={q} value={q}>
                {QUALITY_LABELS[q]}
              </option>
            ))}
          </select>
        </label>
        {shot.takes.length > 0 ? (
          <label className="field">
            Takes
            <select
              aria-label="Takes"
              value={active?.id ?? ""}
              onChange={(e) => action.mutate({ sceneId: shot.scene_id, name: "select-take", body: { take_id: e.target.value } })}
            >
              {shot.takes.map((t) => (
                <option key={t.id} value={t.id}>
                  {`Take ${t.take_no}${t.active ? " - Active" : ""}`}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      <label className="field">
        Motion prompt
        <textarea aria-label="Motion prompt" rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} />
      </label>
      <div className="actions">
        <button
          type="button"
          disabled={!draft.trim()}
          onClick={() => action.mutate({ sceneId: shot.scene_id, name: "save-prompt", body: { prompt: draft, rerender: false } })}
        >
          Save prompt
        </button>
        <button
          type="button"
          disabled={!draft.trim() || !canRender}
          onClick={() => action.mutate({ sceneId: shot.scene_id, name: "save-prompt", body: { prompt: draft, rerender: true } })}
        >
          Save and re-render
        </button>
        <button type="button" disabled={!canRender} onClick={() => go("render")}>
          Render
        </button>
        <button
          type="button"
          disabled={!active || shot.state === "approved" || shot.state === "stale" || busy}
          onClick={() => action.mutate({ sceneId: shot.scene_id, name: "approve" })}
        >
          Approve
        </button>
        <button type="button" disabled={!active || !canRender} onClick={() => go("reroll")}>
          Re-roll
        </button>
        <button type="button" disabled={shot.takes.length < 2} onClick={() => setComparing(true)}>
          Compare takes
        </button>
        <label className="field">
          Upload own clip
          <input
            type="file"
            accept="video/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate({ sceneId: shot.scene_id, file });
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {comparing ? (
        <CompareTakes
          shot={shot}
          onClose={() => setComparing(false)}
          onMakeActive={(id) => {
            action.mutate({ sceneId: shot.scene_id, name: "select-take", body: { take_id: id } });
            setComparing(false);
          }}
        />
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </li>
  );
}
