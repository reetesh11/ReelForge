import { useEffect, useMemo, useState } from "react";
import {
  StoryInvalidError,
  downloadStory,
  formatStoryError,
  useApprove,
  useImportStory,
  useSaveStory,
  useStale,
  useStorySchema,
  useStoryVersion,
  useStoryVersions,
  type Affected,
  type StoryDetail,
} from "@/api/story";
import { parseDraft, type StoryData } from "./draft";
import { FormView } from "./FormView";
import { estimateLength } from "./length";
import { VersionPanel, versionLabel } from "./VersionPanel";
import { YamlView } from "./YamlView";

type Tab = "form" | "yaml";

const LEAVE = "You have unsaved changes. Leave anyway?";

function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    const onClick = (e: MouseEvent) => {
      const anchor = (e.target as Element | null)?.closest?.("a[href], [data-leave-guard]");
      if (anchor && !window.confirm(LEAVE)) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);
}

function scenesOf(data: StoryData | null): Array<Record<string, unknown>> {
  return data && Array.isArray(data["scenes"]) ? (data["scenes"] as Array<Record<string, unknown>>) : [];
}

export function StoryEditor({ projectId, story }: { projectId: string; story: StoryDetail }) {
  const versions = useStoryVersions(projectId);
  const schema = useStorySchema();
  const save = useSaveStory(projectId);
  const approve = useApprove(projectId);
  const importStory = useImportStory(projectId);

  const [baseId, setBaseId] = useState(story.id);
  const [text, setText] = useState(story.yaml_text);
  const [tab, setTab] = useState<Tab>("form");
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [affected, setAffected] = useState<Affected[]>([]);
  const [viewing, setViewing] = useState<number | null>(null);
  const viewed = useStoryVersion(projectId, viewing);

  if (story.id !== baseId) {
    setBaseId(story.id);
    setText(story.yaml_text);
    setServerErrors([]);
    setViewing(null);
  }

  const draft = useMemo(() => parseDraft(text), [text]);
  const [lastValid, setLastValid] = useState<StoryData | null>(draft.ok ? draft.data : null);
  if (draft.ok && draft.data !== lastValid) setLastValid(draft.data);

  const dirty = text !== story.yaml_text;
  useUnsavedGuard(dirty);

  const approved = story.approved_at !== null;
  const stale = useStale(projectId, approved || affected.length > 0);
  const staleKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const a of affected) keys.add(`${a.owner_type}:${a.owner_id}`);
    for (const s of stale.data ?? []) keys.add(`${s.owner_type}:${s.owner_id}`);
    return keys;
  }, [affected, stale.data]);

  const problems = [...draft.problems.map((p) => (p.line ? `line ${p.line}: ${p.message}` : p.message)), ...serverErrors];
  const hasErrors = !draft.ok || serverErrors.length > 0;
  const scenes = scenesOf(lastValid);
  const target = typeof lastValid?.["target_seconds"] === "number" ? lastValid["target_seconds"] : 12;
  const length = estimateLength(
    scenes.map((s) => (typeof s["duration"] === "number" ? s["duration"] : null)),
    target,
  );
  const title = typeof lastValid?.["title"] === "string" && lastValid["title"] ? lastValid["title"] : "Untitled story";
  const readingOld = viewing !== null;

  const edit = (fn: (current: string) => string) => {
    setText((current) => fn(current));
    setServerErrors([]);
    setNotice(null);
  };

  function onSave(body: string) {
    save.mutate(body, {
      onSuccess: (v) => {
        setAffected(v.affected ?? []);
        setServerErrors([]);
        setNotice(null);
      },
      onError: (e) => setServerErrors(e instanceof StoryInvalidError ? e.errors.map(formatStoryError) : [e.message]),
    });
  }

  function onApprove() {
    const suggested = scenes.filter((s) => s["suggested"] === true).length;
    if (suggested > 0 && !window.confirm(`${suggested} lines are still marked suggested. Approve anyway?`)) return;
    approve.mutate(undefined, { onError: (e) => setNotice(e.message) });
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    importStory.mutate(await file.text(), {
      onError: (e) => setServerErrors(e instanceof StoryInvalidError ? e.errors.map(formatStoryError) : [e.message]),
    });
  }

  const current = versions.data?.find((v) => v.is_current);

  return (
    <section aria-label="Story editor">
      <div className="editor-header">
        <h2>{title}</h2>
        {versions.data ? (
          <label>
            Version
            <select
              value={viewing ?? current?.version ?? ""}
              onChange={(e) => {
                const n = Number(e.target.value);
                setViewing(current && n === current.version ? null : n);
              }}
            >
              {versions.data.map((v) => (
                <option key={v.id} value={v.version}>
                  {versionLabel(v)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <span className="meta">{length}</span>
      </div>

      {approved && !readingOld ? <p className="notice">Story approved. Editing it will mark dependent items for update.</p> : null}
      {notice ? <p role="alert" className="errors">{notice}</p> : null}

      <div className="actions">
        <button type="button" disabled={readingOld || !dirty || !draft.ok || save.isPending} onClick={() => onSave(text)}>
          Save
        </button>
        <button
          type="button"
          disabled={readingOld || dirty || hasErrors || approve.isPending}
          title={dirty ? "Save your changes first" : undefined}
          onClick={onApprove}
        >
          Approve story
        </button>
        <button type="button" onClick={() => void downloadStory(projectId)}>
          Export story.yaml
        </button>
        <label className="link-button">
          Import story.yaml
          <input
            type="file"
            accept=".yaml,.yml,text/yaml,text/plain"
            className="visually-hidden"
            onChange={(e) => void onFile(e.target.files?.[0])}
          />
        </label>
      </div>

      {versions.data ? <VersionPanel versions={versions.data} viewing={viewing} onSelect={setViewing} /> : null}

      {readingOld ? (
        <div>
          <p className="notice">Viewing an older version (read-only).</p>
          <textarea
            className="yaml-editor"
            aria-label="Version text"
            readOnly
            value={viewed.data?.yaml_text ?? "Loading..."}
          />
          <button
            type="button"
            disabled={!viewed.data || save.isPending}
            onClick={() => {
              if (viewed.data) {
                onSave(viewed.data.yaml_text);
                setViewing(null);
              }
            }}
          >
            Restore as new version
          </button>
        </div>
      ) : (
        <>
          <div role="tablist" aria-label="Editor view" className="tabs">
            <button type="button" role="tab" aria-selected={tab === "form"} onClick={() => setTab("form")}>
              Form
            </button>
            <button type="button" role="tab" aria-selected={tab === "yaml"} onClick={() => setTab("yaml")}>
              YAML
            </button>
          </div>
          <div role="tabpanel">
            {tab === "form" ? (
              !draft.ok ? (
                <p role="alert" className="errors">
                  YAML has errors; fix them to keep editing in Form view
                </p>
              ) : (
                <FormView data={draft.data} edit={edit} stale={staleKeys} disabled={false} />
              )
            ) : (
              <YamlView
                text={text}
                onChange={(v) => edit(() => v)}
                errors={problems}
                readOnly={false}
                schema={schema.data}
              />
            )}
          </div>
          {tab === "form" && problems.length > 0 && draft.ok ? (
            <ul aria-label="YAML errors" className="errors">
              {problems.map((p, i) => (
                <li key={`${i}-${p}`}>{p}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}
