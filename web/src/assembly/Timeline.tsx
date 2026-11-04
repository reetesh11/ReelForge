import { useState } from "react";
import type { AssemblyState, EditOp, Edl } from "@/api/assembly";

const FRAME_S = 1 / 24;

/** A number field that sends its value when it loses focus or Enter is pressed. */
function NumberField({
  label,
  value,
  step,
  min,
  max,
  disabled,
  onCommit,
}: {
  label: string;
  value: number;
  step: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  onCommit: (v: number) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? String(Math.round(value * 1000) / 1000);
  const commit = () => {
    if (draft === null) return;
    const n = Number(draft);
    setDraft(null);
    if (Number.isFinite(n) && n !== value) onCommit(n);
  };
  return (
    <label className="field">
      <span className="meta">{label}</span>
      <input
        type="number"
        aria-label={label}
        value={shown}
        step={step}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
        }}
      />
    </label>
  );
}

export function Timeline({
  edl,
  shots,
  onEdit,
}: {
  edl: Edl;
  shots: AssemblyState["shots"];
  onEdit: (op: EditOp) => void;
}) {
  const order = edl.video.map((s) => s.scene_id);
  const move = (index: number, by: -1 | 1) => {
    const next = [...order];
    const other = index + by;
    const a = next[index];
    const b = next[other];
    if (a === undefined || b === undefined) return;
    next[index] = b;
    next[other] = a;
    onEdit({ op: "reorder", scene_ids: next });
  };
  return (
    <ol aria-label="Timeline" className="list">
      {edl.video.map((shot, index) => {
        const sid = shot.scene_id;
        const clip = edl.dialogue.find((d) => d.scene_id === sid);
        const takes = shots.find((s) => s.scene_id === sid)?.takes ?? [];
        return (
          <li key={sid} className="card">
            <header className="editor-header">
              <strong>{sid}</strong>
              <span className="meta">{`${(shot.out_s - shot.in_s).toFixed(2)} s`}</span>
            </header>
            <div className="actions">
              <button type="button" disabled={index === 0} onClick={() => move(index, -1)}>
                {`Move ${sid} earlier`}
              </button>
              <button type="button" disabled={index === order.length - 1} onClick={() => move(index, 1)}>
                {`Move ${sid} later`}
              </button>
              <NumberField
                label={`Trim in for ${sid}`}
                value={shot.in_s}
                step={0.01}
                min={0}
                onCommit={(v) => onEdit({ op: "trim", scene_id: sid, in_s: v, out_s: shot.out_s })}
              />
              <NumberField
                label={`Trim out for ${sid}`}
                value={shot.out_s}
                step={0.01}
                min={0}
                onCommit={(v) => onEdit({ op: "trim", scene_id: sid, in_s: shot.in_s, out_s: v })}
              />
              <label className="field">
                <span className="meta">{`Take for ${sid}`}</span>
                <select
                  aria-label={`Take for ${sid}`}
                  value={shot.artifact}
                  onChange={(e) => onEdit({ op: "swap_take", scene_id: sid, take_id: e.target.value })}
                >
                  {takes.some((t) => t.id === shot.artifact) ? null : <option value={shot.artifact}>Current take</option>}
                  {takes.map((t) => (
                    <option key={t.id} value={t.id}>{`Take ${t.take_no}`}</option>
                  ))}
                </select>
              </label>
              <NumberField
                label={`Crossfade into ${sid}`}
                value={shot.transition_in_s}
                step={0.05}
                min={0}
                max={0.5}
                disabled={index === 0}
                onCommit={(v) => onEdit({ op: "set_transition", scene_id: sid, seconds: v })}
              />
            </div>
            {clip ? (
              <div className="actions">
                <button
                  type="button"
                  onClick={() =>
                    onEdit({ op: "nudge_dialogue", scene_id: sid, offset_s: Math.max(0, clip.offset_s - FRAME_S) })
                  }
                >
                  {`Nudge ${sid} dialogue earlier`}
                </button>
                <button
                  type="button"
                  onClick={() => onEdit({ op: "nudge_dialogue", scene_id: sid, offset_s: clip.offset_s + FRAME_S })}
                >
                  {`Nudge ${sid} dialogue later`}
                </button>
                <NumberField
                  label={`Dialogue offset for ${sid}`}
                  value={clip.offset_s}
                  step={FRAME_S}
                  min={0}
                  onCommit={(v) => onEdit({ op: "nudge_dialogue", scene_id: sid, offset_s: v })}
                />
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
