import { useState, type ReactNode } from "react";
import {
  addCharacter,
  addScene,
  deleteIn,
  moveItem,
  renameCharacter,
  setIn,
  type StoryData,
} from "./draft";
import { StaleBadge } from "./StaleBadge";

type Obj = Record<string, unknown>;
type Edit = (fn: (text: string) => string) => void;

const asObj = (v: unknown): Obj => (typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Obj) : {});
const asStr = (v: unknown): string => (typeof v === "string" ? v : v === undefined || v === null ? "" : String(v));

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label>
      {label}
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/** Keeps what the user typed until the value parses, so "2." survives. */
function NumberField({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: number | undefined;
  onCommit: (n: number | null) => void;
}) {
  const [local, setLocal] = useState<string | null>(null);
  return (
    <label>
      {label}
      <input
        type="text"
        inputMode="decimal"
        value={local ?? (value === undefined ? "" : String(value))}
        onChange={(e) => {
          const raw = e.target.value;
          setLocal(raw);
          if (raw.trim() === "") onCommit(null);
          else if (Number.isFinite(Number(raw))) onCommit(Number(raw));
        }}
        onBlur={() => setLocal(null)}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (v: string) => void;
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function CardActions({
  index,
  count,
  onDelete,
  onMove,
}: {
  index: number;
  count: number;
  onDelete: () => void;
  onMove: (to: number) => void;
}) {
  return (
    <div className="card-actions">
      <button type="button" onClick={onDelete}>
        Delete
      </button>
      <button type="button" disabled={index === 0} onClick={() => onMove(index - 1)}>
        Move up
      </button>
      <button type="button" disabled={index >= count - 1} onClick={() => onMove(index + 1)}>
        Move down
      </button>
    </div>
  );
}

function Card({ label, stale, children }: { label: string; stale: boolean; children: ReactNode }) {
  return (
    <section className="card" aria-label={label}>
      <StaleBadge show={stale} />
      {children}
    </section>
  );
}

const FRAMINGS: Array<[string, string]> = [
  ["", "—"],
  ["wide", "Wide"],
  ["medium", "Medium"],
  ["closeup", "Closeup"],
];

export function FormView({
  data,
  edit,
  stale,
  disabled,
}: {
  data: StoryData;
  edit: Edit;
  stale: ReadonlySet<string>;
  disabled: boolean;
}) {
  const characters = Object.entries(asObj(data["characters"]));
  const scenes = Array.isArray(data["scenes"]) ? (data["scenes"] as unknown[]).map(asObj) : [];
  const keys = characters.map(([k]) => k);

  const setOpt = (path: Array<string | number>, value: string) =>
    edit((t) => (value === "" ? deleteIn(t, path) : setIn(t, path, value)));
  const setFlag = (path: Array<string | number>, on: boolean) => edit((t) => (on ? setIn(t, path, true) : deleteIn(t, path)));
  const setNum = (path: Array<string | number>, n: number | null) =>
    edit((t) => (n === null ? deleteIn(t, path) : setIn(t, path, n)));

  return (
    <fieldset disabled={disabled} className="form-view">
      <details className="fold">
        <summary>Story settings</summary>
        <div className="card">
          <TextField label="Title" value={asStr(data["title"])} onChange={(v) => edit((t) => setIn(t, ["title"], v))} />
          <SelectField
            label="Story language"
            value={asStr(data["language"])}
            options={[
              ["hindi", "Hindi"],
              ["english", "English"],
              ["hinglish", "Hinglish"],
            ]}
            onChange={(v) => edit((t) => setIn(t, ["language"], v))}
          />
          <TextField label="Visual style" value={asStr(data["style"])} onChange={(v) => edit((t) => setIn(t, ["style"], v))} />
          <TextField label="Aspect ratio" value={asStr(data["aspect"])} onChange={(v) => edit((t) => setIn(t, ["aspect"], v))} />
          <NumberField label="Frames per second" value={data["fps"] as number | undefined} onCommit={(n) => n !== null && setNum(["fps"], n)} />
          <NumberField
            label="Target seconds"
            value={data["target_seconds"] as number | undefined}
            onCommit={(n) => n !== null && setNum(["target_seconds"], n)}
          />
        </div>
      </details>

      <h3>Characters</h3>
      {characters.map(([key, raw], i) => {
        const c = asObj(raw);
        const voice = asObj(c["voice"]);
        return (
          <Card key={key} label={`Character ${key}`} stale={stale.has(`character:${key}`)}>
            <label>
              Key
              <input
                type="text"
                defaultValue={key}
                onBlur={(e) => {
                  const next = e.target.value.trim();
                  if (next && next !== key) edit((t) => renameCharacter(t, key, next));
                  else e.target.value = key;
                }}
              />
            </label>
            <TextField label="Name" value={asStr(c["name"])} onChange={(v) => edit((t) => setIn(t, ["characters", key, "name"], v))} />
            <TextField label="Look" value={asStr(c["look"])} onChange={(v) => edit((t) => setIn(t, ["characters", key, "look"], v))} />
            <TextField
              label="Voice"
              value={asStr(voice["ref"])}
              onChange={(v) =>
                edit((t) => {
                  if (c["voice"] === undefined) return v === "" ? t : setIn(t, ["characters", key, "voice"], { mode: "preset", ref: v });
                  return v === "" ? deleteIn(t, ["characters", key, "voice", "ref"]) : setIn(t, ["characters", key, "voice", "ref"], v);
                })
              }
            />
            <CardActions
              index={i}
              count={characters.length}
              onDelete={() => edit((t) => deleteIn(t, ["characters", key]))}
              onMove={(to) => edit((t) => moveItem(t, ["characters"], i, to))}
            />
          </Card>
        );
      })}
      <button type="button" onClick={() => edit(addCharacter)}>
        Add character
      </button>

      <h3>Scenes</h3>
      {scenes.map((s, i) => {
        const id = asStr(s["id"]);
        const base = ["scenes", i];
        return (
          <Card key={`${id}-${i}`} label={`Scene ${id}`} stale={stale.has(`scene:${id}`)}>
            <TextField label="Setting" value={asStr(s["setting"])} onChange={(v) => setOpt([...base, "setting"], v)} />
            <TextField label="Action" value={asStr(s["action"])} onChange={(v) => edit((t) => setIn(t, [...base, "action"], v))} />
            <SelectField
              label="Speaker"
              value={asStr(s["speaker"])}
              options={[["", "None"], ...keys.map((k): [string, string] => [k, k])]}
              onChange={(v) => setOpt([...base, "speaker"], v)}
            />
            <TextField label="Line" value={asStr(s["line"])} onChange={(v) => setOpt([...base, "line"], v)} />
            {s["suggested"] === true ? (
              <div className="card-actions">
                <span className="badge amber">suggested</span>
                <button type="button" onClick={() => edit((t) => deleteIn(t, [...base, "suggested"]))}>
                  Accept
                </button>
              </div>
            ) : null}
            <NumberField label="Duration" value={s["duration"] as number | undefined} onCommit={(n) => setNum([...base, "duration"], n)} />
            <SelectField label="Framing" value={asStr(s["framing"])} options={FRAMINGS} onChange={(v) => setOpt([...base, "framing"], v)} />
            <Check label="Product in shot" checked={s["product_in_shot"] === true} onChange={(on) => setFlag([...base, "product_in_shot"], on)} />
            <TextField label="Continue from" value={asStr(s["continue_from"])} onChange={(v) => setOpt([...base, "continue_from"], v)} />
            <Check label="End card" checked={s["end_card"] === true} onChange={(on) => setFlag([...base, "end_card"], on)} />
            <CardActions
              index={i}
              count={scenes.length}
              onDelete={() => edit((t) => deleteIn(t, base))}
              onMove={(to) => edit((t) => moveItem(t, ["scenes"], i, to))}
            />
          </Card>
        );
      })}
      <button type="button" onClick={() => edit(addScene)}>
        Add scene
      </button>
    </fieldset>
  );
}
