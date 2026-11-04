import { useState } from "react";
import type { AssemblyState, EditOp, Edl, EdlCaption } from "@/api/assembly";

function CaptionLine({
  caption,
  status,
  onEdit,
}: {
  caption: EdlCaption;
  status: "words" | "line" | "pending" | undefined;
  onEdit: (op: EditOp) => void;
}) {
  const [draft, setDraft] = useState(caption.text);
  const [seen, setSeen] = useState(caption.text);
  if (seen !== caption.text) {
    setSeen(caption.text);
    setDraft(caption.text);
  }
  const name = `Caption for ${caption.speaker ?? "Narrator"} line ${caption.line_no}`;
  return (
    <li>
      <label className="field">
        <span className="meta">{name}</span>
        <input
          type="text"
          aria-label={name}
          placeholder="No caption for this line"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            if (draft !== caption.text) onEdit({ op: "set_caption_text", scene_id: caption.scene_id, text: draft });
          }}
        />
      </label>
      {status === "line" && caption.text.trim() ? (
        <p className="meta">Word timing unavailable - showing the whole line</p>
      ) : null}
    </li>
  );
}

export function CaptionEditor({
  edl,
  status,
  presets,
  rebuilding,
  onEdit,
}: {
  edl: Edl;
  status: AssemblyState["caption_status"];
  presets: AssemblyState["caption_presets"];
  rebuilding: boolean;
  onEdit: (op: EditOp) => void;
}) {
  const aligning = rebuilding && Object.values(status).includes("pending");
  return (
    <section aria-label="Captions">
      <h3>Captions</h3>
      <label className="field">
        <span className="meta">Caption style</span>
        <select
          aria-label="Caption style"
          value={edl.caption_style}
          onChange={(e) => onEdit({ op: "set_caption_style", style: e.target.value })}
        >
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
          <option value="auto">Auto</option>
        </select>
      </label>
      {aligning ? <p className="meta">Aligning captions...</p> : null}
      <ul className="list">
        {edl.captions.map((c) => (
          <CaptionLine key={c.scene_id} caption={c} status={status[c.scene_id]} onEdit={onEdit} />
        ))}
      </ul>
    </section>
  );
}
