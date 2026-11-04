import { useEffect, useState } from "react";
import {
  useApproveCandidate,
  useCancelJob,
  useGenerate,
  useReopen,
  useSetAge,
  useUpload,
  useUseLibrary,
  type CastItem,
} from "@/api/cast";
import { useLibraryCharacters } from "@/api/library";
import { ProjectVoiceSetup } from "@/voice/VoiceSetup";
import { ApproveDialog } from "./ApproveDialog";
import { CandidateGrid } from "./CandidateGrid";
import { LibraryPicker } from "./LibraryPicker";

function useSecondsSince(startedAt: number, baseSeconds: number, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return Math.max(0, Math.floor(baseSeconds + (running ? (now - startedAt) / 1000 : 0)));
}

export function CastRow({
  projectId,
  item,
  backendDown,
  licenceWarning,
  receivedAt,
}: {
  projectId: string;
  item: CastItem;
  backendDown: boolean;
  licenceWarning: string | null;
  receivedAt: number;
}) {
  const generate = useGenerate(projectId);
  const approve = useApproveCandidate(projectId);
  const reopen = useReopen(projectId);
  const useLibrary = useUseLibrary(projectId);
  const upload = useUpload(projectId);
  const cancel = useCancelJob(projectId);
  const setAge = useSetAge(projectId);
  const library = useLibraryCharacters();

  const [selected, setSelected] = useState<string | null>(null);
  const [edited, setEdited] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [picking, setPicking] = useState(false);
  const [ageDraft, setAgeDraft] = useState<string | null>(null);

  const progress = item.progress;
  const generating = item.state === "generating";
  const elapsed = useSecondsSince(receivedAt, progress?.elapsed_s ?? 0, generating);
  const total = progress?.total ?? 4;
  const completed = progress?.completed ?? 0;
  const error = [generate, approve, reopen, useLibrary, upload, cancel, setAge]
    .map((m) => m.error?.message)
    .find((m) => m !== undefined);

  const selection = item.candidates.some((c) => c.id === selected) ? selected : null;
  const text = edited ?? item.bible_line;
  const libraryName = library.data?.find((c) => c.id === item.library_character_id)?.name;

  const start = (body: Parameters<typeof generate.mutate>[0]["body"]) => {
    generate.mutate({ key: item.key, body });
  };
  const doApprove = () => {
    if (selection) approve.mutate({ key: item.key, candidateId: selection });
    setConfirming(false);
  };

  return (
    <li aria-label={`Character: ${item.name}`} className="card">
      <header className="editor-header">
        <strong>{item.name}</strong>
        {item.aliases.length > 0 ? <span className="meta">{item.aliases.join(", ")}</span> : null}
        <span className={item.approved ? "badge green" : "badge"}>{item.approved ? "Approved" : "Not approved"}</span>
      </header>
      <label className="field">
        Character bible line
        <textarea rows={2} value={text} onChange={(e) => setEdited(e.target.value)} />
      </label>
      {item.note ? <p className="meta">{item.note}</p> : null}
      <div className="actions">
        <p className="meta">
          {item.age !== undefined && item.age !== null
            ? `Age ${item.age}${item.age_band ? ` (${item.age_band})` : ""}`
            : "No age set"}
        </p>
        <label className="field">
          Age (years)
          <input
            type="number"
            min={1}
            max={120}
            step={1}
            value={ageDraft ?? (item.age !== undefined && item.age !== null ? String(item.age) : "")}
            onChange={(e) => setAgeDraft(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={ageDraft === null || setAge.isPending}
          onClick={() =>
            setAge.mutate(
              { key: item.key, age: ageDraft === null || ageDraft.trim() === "" ? null : Number(ageDraft) },
              { onSuccess: () => setAgeDraft(null) },
            )
          }
        >
          Save age
        </button>
      </div>

      {item.approved && item.master_artifact_id ? (
        <div>
          <img
            src={`/media/${item.master_artifact_id}`}
            alt={`Approved master for ${item.name}`}
            className="master"
          />
          {item.library_character_id ? <p className="meta">{`From library: ${libraryName ?? item.name}`}</p> : null}
          {item.variant_of_library_id ? (
            <p className="meta">This changes a library character, so a copy was made.</p>
          ) : null}
          <div className="actions">
            <button type="button" onClick={() => reopen.mutate(item.key)}>
              Change approval
            </button>
            <button type="button" onClick={() => setPicking(true)}>
              Replace from library
            </button>
          </div>
        </div>
      ) : null}

      {generating ? (
        <div>
          <p>{`Generating image ${Math.min(completed + 1, total)} of ${total} - ${elapsed} s elapsed`}</p>
          {item.job_id ? (
            <button type="button" onClick={() => cancel.mutate(item.job_id as string)}>
              Cancel
            </button>
          ) : null}
        </div>
      ) : null}
      {item.state === "stopped" ? <p>{`Stopped after ${completed} of ${total} images`}</p> : null}
      {item.state === "failed" ? (
        <div className="notice error">
          <p>Couldn't generate images.</p>
          {item.error ? <p>{item.error}</p> : null}
          {backendDown ? null : (
            <button type="button" onClick={() => start({})}>
              Retry
            </button>
          )}
        </div>
      ) : null}
      {item.state === "empty" ? <p>No candidates yet</p> : null}

      {!item.approved && item.candidates.length > 0 ? (
        <CandidateGrid candidates={item.candidates} selectedId={selection} onSelect={setSelected} />
      ) : null}

      {!item.approved ? (
        <div className="actions">
          {backendDown || generating ? null : item.state === "empty" ? (
            <button type="button" onClick={() => start({})}>
              Generate candidates
            </button>
          ) : null}
          {item.candidates.length > 0 ? (
            <button
              type="button"
              disabled={!selection}
              onClick={() => (licenceWarning ? setConfirming(true) : doApprove())}
            >
              Approve this one
            </button>
          ) : null}
          {backendDown || generating || item.candidates.length === 0 ? null : (
            <>
              <button type="button" onClick={() => start({ regenerate: true })}>
                Regenerate 4 more
              </button>
              <button type="button" onClick={() => start({ look_text: text })}>
                Edit look text and regenerate
              </button>
            </>
          )}
          <button type="button" onClick={() => setPicking(true)}>
            Use from library
          </button>
        </div>
      ) : null}

      {!item.approved && !backendDown && !generating && item.candidates.length > 0 ? (
        <div className="actions">
          <label className="field">
            What small change?
            <input type="text" value={instruction} onChange={(e) => setInstruction(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={!selection}
            onClick={() => selection && start({ refine: { from_candidate: selection, instruction } })}
          >
            Refine selected (img2img)
          </button>
        </div>
      ) : null}

      {item.approved ? null : (
        <label className="field">
          Upload my own image
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate({ key: item.key, file });
              e.target.value = "";
            }}
          />
        </label>
      )}

      {item.approved ? <ProjectVoiceSetup projectId={projectId} characterKey={item.key} /> : null}

      {error ? <p role="alert">{error}</p> : null}
      {confirming && licenceWarning ? (
        <ApproveDialog warning={licenceWarning} onConfirm={doApprove} onCancel={() => setConfirming(false)} />
      ) : null}
      {picking ? (
        <LibraryPicker
          targets={[{ key: item.key, name: item.name }]}
          fixedKey={item.key}
          onPick={(key, characterId) => {
            useLibrary.mutate({ key, characterId });
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </li>
  );
}
