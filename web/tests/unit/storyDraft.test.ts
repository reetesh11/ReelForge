import { expect, it } from "vitest";
import {
  addCharacter,
  addScene,
  deleteIn,
  moveItem,
  nextSceneId,
  parseDraft,
  renameCharacter,
  setIn,
} from "@/story/draft";

const TEXT = `# my tale
title: "Tale" # name
characters:
  tomato:
    name: "Tamatar"
    look: "red"
scenes:
  - id: s1
    action: "one"
    # keep me
    duration: 2.0
  - id: s3
    speaker: tomato
    action: "three"
`;

it("parses valid text and reports syntax errors", () => {
  const ok = parseDraft(TEXT);
  expect(ok.ok).toBe(true);
  const bad = parseDraft("title: [oops\n");
  expect(bad.ok).toBe(false);
  expect(bad.problems.length).toBeGreaterThan(0);
  expect(parseDraft("  \n").problems[0]?.message).toBe("story.yaml is empty");
  expect(parseDraft("- a\n").ok).toBe(false);
});

it("setIn keeps comments and writes plain scalars", () => {
  const out = setIn(TEXT, ["title"], "New");
  expect(out).toContain("# my tale");
  expect(out).toContain("title: New # name");
  expect(setIn(TEXT, ["scenes", 0, "action"], "Aloo dances")).toContain("action: Aloo dances");
  expect(setIn(TEXT, ["scenes", 0, "action"], "x")).toContain("# keep me");
});

it("deleteIn removes a key", () => {
  expect(deleteIn(TEXT, ["scenes", 0, "duration"])).not.toContain("duration");
});

it("new scene id is the next unused number", () => {
  const draft = parseDraft(TEXT);
  if (!draft.ok) throw new Error("expected valid");
  expect(nextSceneId(draft.data)).toBe("s4");
  const out = addScene(TEXT);
  expect(out).toContain("id: s4");
  expect(parseDraft(out).ok).toBe(true);
});

it("adds, renames and moves", () => {
  expect(addCharacter(TEXT)).toContain("character_1:");
  const renamed = renameCharacter(TEXT, "tomato", "tamatar");
  expect(renamed).toContain("tamatar:");
  expect(renamed).toContain("speaker: tamatar");
  const moved = moveItem(TEXT, ["scenes"], 0, 1);
  expect(moved.indexOf("id: s3")).toBeLessThan(moved.indexOf("id: s1"));
});

it("returns the text untouched when it does not parse", () => {
  expect(setIn("a: [", ["a"], 1)).toBe("a: [");
});
