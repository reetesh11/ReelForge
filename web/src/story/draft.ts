import { Document, Scalar, YAMLMap, YAMLSeq, isMap, isScalar, isSeq, parseDocument } from "yaml";

export type Path = ReadonlyArray<string | number>;
export type StoryData = Record<string, unknown>;

export type YamlProblem = { message: string; line: number | null };

export type Draft =
  | { ok: true; data: StoryData; problems: [] }
  | { ok: false; data: null; problems: YamlProblem[] };

const TO_STRING = { indent: 2, indentSeq: true, lineWidth: 0 } as const;

export function parseDraft(text: string): Draft {
  if (text.trim() === "") return { ok: false, data: null, problems: [{ message: "story.yaml is empty", line: null }] };
  const doc = parseDocument(text, { prettyErrors: false, uniqueKeys: true });
  if (doc.errors.length > 0) {
    return {
      ok: false,
      data: null,
      problems: doc.errors.map((e) => ({ message: e.message.split("\n")[0] ?? e.message, line: e.linePos?.[0].line ?? null })),
    };
  }
  const data: unknown = doc.toJS();
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return { ok: false, data: null, problems: [{ message: "story.yaml must be a mapping at the top level", line: null }] };
  }
  return { ok: true, data: data as StoryData, problems: [] };
}

function open(text: string): Document | null {
  const doc = parseDocument(text, { uniqueKeys: true });
  return doc.errors.length > 0 ? null : doc;
}

function render(doc: Document): string {
  return doc.toString(TO_STRING);
}

function replaceScalar(doc: Document, path: Path, value: unknown): void {
  const existing: unknown = doc.getIn(path, true);
  if (isScalar(existing) && (typeof value !== "object" || value === null)) {
    const next = new Scalar(value);
    next.comment = existing.comment;
    next.commentBefore = existing.commentBefore;
    next.spaceBefore = existing.spaceBefore;
    doc.setIn(path, next);
  } else {
    doc.setIn(path, value);
  }
}

/** Set a value, keeping comments around the old value. Returns the text unchanged if it does not parse. */
export function setIn(text: string, path: Path, value: unknown): string {
  const doc = open(text);
  if (!doc) return text;
  replaceScalar(doc, path, value);
  return render(doc);
}

export function deleteIn(text: string, path: Path): string {
  const doc = open(text);
  if (!doc) return text;
  doc.deleteIn(path);
  return render(doc);
}

export function nextSceneId(data: StoryData): string {
  const scenes = Array.isArray(data["scenes"]) ? (data["scenes"] as unknown[]) : [];
  let max = 0;
  for (const scene of scenes) {
    const id = typeof scene === "object" && scene !== null ? (scene as { id?: unknown }).id : null;
    const match = typeof id === "string" ? /^s(\d+)$/.exec(id) : null;
    if (match?.[1]) max = Math.max(max, Number(match[1]));
  }
  return `s${max + 1}`;
}

export function nextCharacterKey(data: StoryData): string {
  const chars = (typeof data["characters"] === "object" && data["characters"] !== null ? data["characters"] : {}) as Record<string, unknown>;
  let n = 1;
  while (`character_${n}` in chars) n += 1;
  return `character_${n}`;
}

export function addScene(text: string): string {
  const doc = open(text);
  if (!doc) return text;
  const draft = parseDraft(text);
  if (!draft.ok) return text;
  const item = doc.createNode({ id: nextSceneId(draft.data), action: "" });
  const scenes = doc.get("scenes", true);
  if (isSeq(scenes)) scenes.add(item);
  else doc.set("scenes", doc.createNode([{ id: nextSceneId(draft.data), action: "" }]));
  return render(doc);
}

export function addCharacter(text: string): string {
  const doc = open(text);
  if (!doc) return text;
  const draft = parseDraft(text);
  if (!draft.ok) return text;
  doc.setIn(["characters", nextCharacterKey(draft.data)], doc.createNode({ name: "New character", look: "Describe the look" }));
  return render(doc);
}

/** Move an item inside a sequence or mapping (by position). */
export function moveItem(text: string, listPath: Path, from: number, to: number): string {
  const doc = open(text);
  if (!doc) return text;
  const node: unknown = doc.getIn(listPath, true);
  if (!(isSeq(node) || isMap(node))) return text;
  const items = (node as YAMLSeq | YAMLMap).items as unknown[];
  if (from < 0 || to < 0 || from >= items.length || to >= items.length || from === to) return text;
  const [moved] = items.splice(from, 1);
  items.splice(to, 0, moved);
  return render(doc);
}

/** Rename a character key and update scene speakers that used it. */
export function renameCharacter(text: string, oldKey: string, newKey: string): string {
  const doc = open(text);
  if (!doc || oldKey === newKey) return text;
  const chars = doc.get("characters", true);
  if (!isMap(chars)) return text;
  const pair = chars.items.find((p) => isScalar(p.key) && p.key.value === oldKey);
  if (!pair || chars.items.some((p) => isScalar(p.key) && p.key.value === newKey)) return text;
  (pair.key as Scalar).value = newKey;
  const scenes = doc.get("scenes", true);
  if (isSeq(scenes)) {
    for (const scene of scenes.items) {
      if (isMap(scene) && scene.get("speaker") === oldKey) scene.set("speaker", newKey);
    }
  }
  return render(doc);
}
