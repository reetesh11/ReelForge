import { useState, type FormEvent } from "react";
import type { Cue, CueBody, CueKind } from "@/api/audio";

const KINDS: CueKind[] = ["music", "sfx", "ambience", "silence"];

function num(text: string): number | undefined {
  if (text.trim() === "") return undefined;
  const n = Number(text);
  return Number.isFinite(n) ? n : undefined;
}

const text = (n: number | undefined) => (n === undefined ? "" : String(n));

export function CueForm({
  cue,
  scenes,
  error,
  onSave,
  onCancel,
}: {
  cue: Cue | null;
  scenes: string[];
  error?: string[];
  onSave: (cue: CueBody) => void;
  onCancel: () => void;
}) {
  const [id, setId] = useState(cue?.id ?? "");
  const [kind, setKind] = useState<CueKind>(cue?.kind ?? "music");
  const [scene, setScene] = useState(cue?.start.scene ?? scenes[0] ?? "s1");
  const [offset, setOffset] = useState(text(cue?.start.offset ?? 0));
  const [duration, setDuration] = useState(text(cue?.duration));
  const [prompt, setPrompt] = useState(cue?.prompt ?? "");
  const [source, setSource] = useState(cue?.source === "file" ? "file" : "generate");
  const [gain, setGain] = useState(text(cue?.gain_db));
  const [fadeIn, setFadeIn] = useState(text(cue?.fade_in_s));
  const [fadeOut, setFadeOut] = useState(text(cue?.fade_out_s));
  const [duck, setDuck] = useState(cue?.duck ?? false);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body: CueBody = {
      id: id.trim(),
      kind,
      start: { scene, at: cue?.start.at ?? "scene_start", offset: num(offset) ?? 0 },
    };
    const len = num(duration);
    if (len !== undefined) body.duration = len;
    else if (cue?.end) body.end = cue.end;
    if (kind !== "silence") {
      body.prompt = prompt;
      body.source = source === "file" ? "file" : "generate";
    }
    const g = num(gain);
    if (g !== undefined) body.gain_db = g;
    const fi = num(fadeIn);
    if (fi !== undefined) body.fade_in_s = fi;
    const fo = num(fadeOut);
    if (fo !== undefined) body.fade_out_s = fo;
    if (kind === "music") body.duck = duck;
    onSave(body);
  };

  return (
    <form className="card" aria-label={cue ? `Edit ${cue.id}` : "New cue"} onSubmit={submit}>
      <label>
        Cue id
        <input value={id} readOnly={cue !== null} onChange={(e) => setId(e.target.value)} />
      </label>
      <label>
        Kind
        <select value={kind} onChange={(e) => setKind(e.target.value as CueKind)}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <label>
        Scene
        {scenes.length > 0 ? (
          <select value={scene} onChange={(e) => setScene(e.target.value)}>
            {scenes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        ) : (
          <input value={scene} onChange={(e) => setScene(e.target.value)} />
        )}
      </label>
      <label>
        Offset (s)
        <input type="number" step="any" value={offset} onChange={(e) => setOffset(e.target.value)} />
      </label>
      <label>
        Duration (s)
        <input
          type="number"
          step="any"
          placeholder={cue ? String(Number(cue.duration_s.toFixed(2))) : ""}
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        />
      </label>
      <label>
        Prompt
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </label>
      <label>
        Source
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="generate">generate</option>
          <option value="file">file</option>
        </select>
      </label>
      <label>
        Gain (dB)
        <input type="number" step="any" value={gain} onChange={(e) => setGain(e.target.value)} />
      </label>
      <label>
        Fade in (s)
        <input type="number" step="any" value={fadeIn} onChange={(e) => setFadeIn(e.target.value)} />
      </label>
      <label>
        Fade out (s)
        <input type="number" step="any" value={fadeOut} onChange={(e) => setFadeOut(e.target.value)} />
      </label>
      <label className="inline">
        <input type="checkbox" checked={duck} onChange={(e) => setDuck(e.target.checked)} />
        Duck under dialogue
      </label>
      {error?.map((m) => (
        <p key={m} role="alert">
          {m}
        </p>
      ))}
      <div className="actions">
        <button type="submit">Save cue</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
