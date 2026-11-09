import { useState } from "react";
import {
  EMOTIONS,
  useClearVoice,
  usePresetPreview,
  useRemoveEmotionClip,
  useSetVoice,
  useUploadEmotionClip,
  useUploadReference,
  useVoices,
  type EmotionClip,
  type SetVoiceBody,
  type VoiceOut,
} from "@/api/voice";

const MODEL_LABELS: Record<string, string> = { omnivoice: "OmniVoice", kokoro: "Kokoro (fallback)" };
type Mode = "preset" | "cloned" | "recorded";
const MODES: Array<{ mode: Mode; label: string }> = [
  { mode: "preset", label: "Preset" },
  { mode: "cloned", label: "Cloned" },
  { mode: "recorded", label: "Recorded lines" },
];

export function modelNote(voice: VoiceOut | null): string | null {
  if (!voice || !voice.model_mismatch || !voice.model) return null;
  return `Voice made with ${MODEL_LABELS[voice.model] ?? voice.model}.`;
}

export interface VoiceSetupProps {
  name: string;
  voice: VoiceOut | null;
  presets: Array<{ id: string; label: string }>;
  busy?: boolean;
  error?: string | null;
  onSet: (body: SetVoiceBody) => void;
  onUpload: (file: File, text: string) => void;
  onPreview: (presetId: string) => Promise<string>;
  onClear?: () => void;
  age?: number | null;
  ageBand?: string;
  modelKey?: string;
  emotionClips?: Record<string, EmotionClip>;
  onUploadEmotionClip?: (emotion: string, file: File, transcript: string) => void;
  onRemoveEmotionClip?: (emotion: string) => void;
}

function EmotionClipRow({
  emotion,
  label,
  clip,
  onUpload,
  onRemove,
}: {
  emotion: string;
  label: string;
  clip: EmotionClip | undefined;
  onUpload?: (emotion: string, file: File, transcript: string) => void;
  onRemove?: (emotion: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [transcript, setTranscript] = useState("");
  return (
    <li aria-label={`${label} clip`} className="card">
      <strong>{label}</strong>
      {clip ? (
        <div>
          <audio controls src={clip.url} aria-label={`${label} clip audio`} />
          <p>{clip.transcript}</p>
          <button type="button" className="btn btn-secondary" onClick={() => onRemove?.(emotion)}>
            {`Remove ${label} clip`}
          </button>
        </div>
      ) : (
        <p className="meta">No clip. The neutral reference and emotion settings are used.</p>
      )}
      <div className="actions">
        <label className="field">
          {`Upload clip for ${label}`}
          <input
            type="file"
            accept="audio/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="field">
          {`Transcript for ${label}`}
          <input type="text" value={transcript} onChange={(e) => setTranscript(e.target.value)} />
        </label>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={!file || !transcript.trim()}
          onClick={() => {
            if (!file) return;
            onUpload?.(emotion, file, transcript);
            setFile(null);
            setTranscript("");
          }}
        >
          Upload clip
        </button>
      </div>
    </li>
  );
}

/** The "Voice" section of a cast row: preset, cloned clip or recorded lines. */
export function VoiceSetup({
  name,
  voice,
  presets,
  busy,
  error,
  onSet,
  onUpload,
  onPreview,
  onClear,
  age,
  ageBand,
  modelKey,
  emotionClips,
  onUploadEmotionClip,
  onRemoveEmotionClip,
}: VoiceSetupProps) {
  const [mode, setMode] = useState<Mode>((voice?.mode as Mode | undefined) ?? "preset");
  const [preset, setPreset] = useState(voice?.voice_id ?? "");
  const [text, setText] = useState(voice?.reference_text ?? "");
  const [audio, setAudio] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const note = modelNote(voice);
  const clip = voice?.clip_seconds;

  const pick = (next: Mode) => {
    setMode(next);
    if (next === "recorded") onSet({ mode: "recorded" });
  };
  const preview = async (id: string) => {
    setPreviewing(true);
    setPreviewError(null);
    try {
      setAudio(await onPreview(id));
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : "could not preview this voice");
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <fieldset aria-label={`Voice for ${name}`}>
      <legend>Voice</legend>
      {age !== undefined ? (
        <p className="meta">
          {age === null || age === undefined ? "No age set" : `Age ${age}${ageBand ? ` (${ageBand})` : ""}`}
          {modelKey === "kokoro" ? <span className="chip chip-amber">Experimental</span> : null}
        </p>
      ) : null}
      <div role="radiogroup" aria-label="Voice mode" className="actions">
        {MODES.map(({ mode: m, label }) => (
          <label key={m} className="inline">
            <input type="radio" name={`voice-mode-${name}`} checked={mode === m} onChange={() => pick(m)} />
            {label}
          </label>
        ))}
      </div>

      {mode === "preset" ? (
        <div className="actions">
          <label className="field">
            Preset voice
            <select
              value={preset}
              onChange={(e) => {
                setPreset(e.target.value);
                if (e.target.value) onSet({ mode: "preset", voice_id: e.target.value });
              }}
            >
              <option value="">Pick a voice</option>
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn-secondary" disabled={!preset || previewing} onClick={() => void preview(preset)}>
            Preview
          </button>
          {previewing ? <span className="meta">Making a sample...</span> : null}
          {audio ? <audio controls src={audio} aria-label="Voice preview" /> : null}
        </div>
      ) : null}

      {mode === "cloned" ? (
        <div>
          <label className="field">
            Upload reference clip
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onUpload(file, text);
                e.target.value = "";
              }}
            />
          </label>
          <p className="meta">Use a clean 5 to 10 second clip.</p>
          {clip !== undefined && clip !== null && (clip < 5 || clip > 10) ? (
            <p className="meta">Clips of 5 to 10 seconds clone best.</p>
          ) : null}
          {voice?.reference_url ? <audio controls src={voice.reference_url} aria-label="Reference clip" /> : null}
          <label className="field">
            What is said in the clip
            <input type="text" value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || !text.trim()}
            onClick={() => onSet({ mode: "cloned", reference_text: text })}
          >
            Use this clip
          </button>
          <section aria-label="Emotion reference clips">
            <h4>Emotion reference clips</h4>
            <ul className="list">
              {EMOTIONS.map((o) => (
                <EmotionClipRow
                  key={o.value}
                  emotion={o.value}
                  label={o.label}
                  clip={emotionClips?.[o.value]}
                  onUpload={onUploadEmotionClip}
                  onRemove={onRemoveEmotionClip}
                />
              ))}
            </ul>
          </section>
        </div>
      ) : null}

      {mode === "recorded" ? (
        <p className="meta">{`${name}'s lines will be uploaded as recordings on the voice board.`}</p>
      ) : null}

      {note ? <p className="meta">{note}</p> : null}
      {voice && onClear ? (
        <button type="button" className="btn btn-secondary" onClick={onClear}>
          Remove voice
        </button>
      ) : null}
      {error || previewError ? <p role="alert">{error ?? previewError}</p> : null}
    </fieldset>
  );
}

/** VoiceSetup wired to a project character; renders nothing until the voice API is available. */
export function ProjectVoiceSetup({ projectId, characterKey }: { projectId: string; characterKey: string }) {
  const voices = useVoices(projectId);
  const setVoice = useSetVoice(projectId);
  const clear = useClearVoice(projectId);
  const upload = useUploadReference(projectId);
  const preview = usePresetPreview(projectId);
  const uploadClip = useUploadEmotionClip(projectId);
  const removeClip = useRemoveEmotionClip(projectId);
  const character = voices.data?.characters.find((c) => c.key === characterKey);
  if (!voices.data || !character) return null;
  const error = [setVoice, clear, upload, uploadClip, removeClip].map((m) => m.error?.message).find((m) => m !== undefined) ?? null;
  return (
    <VoiceSetup
      key={`${characterKey}-${character.voice?.mode ?? "none"}`}
      name={character.name}
      voice={character.voice}
      presets={voices.data.presets}
      busy={setVoice.isPending || upload.isPending}
      error={error}
      onSet={(body) => setVoice.mutate({ key: characterKey, body })}
      onUpload={(file, text) => upload.mutate({ key: characterKey, file, text: text || undefined })}
      onPreview={(id) => preview.mutateAsync(id)}
      onClear={() => clear.mutate(characterKey)}
      age={character.age ?? null}
      ageBand={character.age_band ?? undefined}
      modelKey={voices.data.voice_model.key}
      emotionClips={(character.voice?.emotion_clips ?? undefined) as Record<string, EmotionClip> | undefined}
      onUploadEmotionClip={(emotion, file, transcript) =>
        uploadClip.mutate({ key: characterKey, emotion, file, transcript })
      }
      onRemoveEmotionClip={(emotion) => removeClip.mutate({ key: characterKey, emotion })}
    />
  );
}
