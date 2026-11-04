import { useEffect, useState } from "react";
import {
  previewUrl,
  useCancelVoiceJob,
  useGenerateVoices,
  useVoices,
  type VoiceBoardState,
} from "@/api/voice";
import { LineCard } from "./LineCard";
import { usePlayback } from "./usePlayback";

function useSecondsSince(startedAt: number, baseSeconds: number, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return Math.max(0, Math.floor(baseSeconds + (running ? (now - startedAt) / 1000 : 0)));
}

function JobStatus({
  board,
  receivedAt,
  onCancel,
}: {
  board: VoiceBoardState;
  receivedAt: number;
  onCancel: (jobId: string) => void;
}) {
  const job = board.job;
  const running = job?.status === "queued" || job?.status === "running";
  const result = (job?.result ?? {}) as { completed?: number; total?: number; elapsed_s?: number };
  const elapsed = useSecondsSince(receivedAt, result.elapsed_s ?? 0, job?.status === "running");
  if (!job || !running) return null;
  const total = result.total ?? Number(job.payload["total"] ?? 0);
  const line = Math.min((result.completed ?? 0) + 1, Math.max(total, 1));
  return (
    <div>
      <p>
        {job.status === "queued"
          ? (job.message ?? "Waiting for the voice engine")
          : `Rendering line ${line} of ${total} - ${elapsed} s elapsed`}
      </p>
      <button type="button" onClick={() => onCancel(job.id)}>
        Cancel
      </button>
    </div>
  );
}

const VOICES_DONE = new Set(["VOICES_APPROVED", "FRAMES_APPROVED", "SHOTS_APPROVED", "REEL_EXPORTED", "EXPORTED"]);

export function VoiceBoard({ projectId, onContinue }: { projectId: string; onContinue?: () => void }) {
  const voices = useVoices(projectId);
  const generate = useGenerateVoices(projectId);
  const cancel = useCancelVoiceJob(projectId);
  const playback = usePlayback();

  if (!voices.data) return null;
  const board = voices.data;
  const recorded = new Set(board.characters.filter((c) => c.voice?.mode === "recorded").map((c) => c.key));
  const noTake = board.lines.filter((l) => l.state !== "no_dialogue" && !l.takes.some((t) => t.active)).length;
  const error = generate.error?.message ?? cancel.error?.message;

  return (
    <section aria-label="Voices">
      <h2>Voices</h2>
      <div className="actions">
        <button type="button" onClick={() => generate.mutate({ mode: "missing" })}>
          Generate all lines
        </button>
        {board.stale_count > 0 ? (
          <button type="button" onClick={() => generate.mutate({ mode: "stale" })}>
            Regenerate stale items
          </button>
        ) : null}
        <button type="button" onClick={() => playback.play(previewUrl(projectId))}>
          Play all
        </button>
        <span>{`${board.approved_count} of ${board.total} lines approved`}</span>
      </div>
      {noTake > 0 ? (
        <p className="meta">{noTake === 1 ? "1 line has no take yet" : `${noTake} lines have no take yet`}</p>
      ) : null}
      <JobStatus board={board} receivedAt={voices.dataUpdatedAt} onCancel={(id) => cancel.mutate(id)} />
      {error ? <p role="alert">{error}</p> : null}
      <audio key={playback.nonce} src={playback.url ?? undefined} autoPlay controls aria-label="Voice playback" />
      <ul aria-label="Voice lines" className="list">
        {board.lines.map((line) => (
          <LineCard
            key={line.scene_id}
            projectId={projectId}
            line={line}
            recorded={line.speaker !== null && recorded.has(line.speaker)}
            onPlay={playback.play}
          />
        ))}
      </ul>
      <div className="actions">
        <button type="button" disabled={!VOICES_DONE.has(board.stage)} onClick={onContinue}>
          Continue to key frames
        </button>
      </div>
    </section>
  );
}
