import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { queryKeys } from "@/api/client";
import {
  StoryInvalidError,
  formatStoryError,
  parseStructureResult,
  useImportStory,
  useJob,
  useSaveStory,
  useStructure,
  type StructureBody,
} from "@/api/story";
import { GapQuestions, type Answer } from "./GapQuestions";
import { StructureStatus } from "./StructureStatus";

type Form = {
  storyline: string;
  characters: string;
  locations: string;
  product: string;
  dialogue: string;
  style: string;
  language: "" | "hindi" | "english" | "hinglish";
  target: number;
};

const EMPTY: Form = {
  storyline: "",
  characters: "",
  locations: "",
  product: "",
  dialogue: "",
  style: "",
  language: "",
  target: 12,
};

const SKIPPED = "No preference; choose something reasonable.";

function orNull(value: string): string | null {
  return value.trim() === "" ? null : value;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="fold">
      <summary>{title}</summary>
      {children}
    </details>
  );
}

export function StoryInput({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>(EMPTY);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const structure = useStructure(projectId);
  const job = useJob(jobId);
  const importStory = useImportStory(projectId);
  const saveDraft = useSaveStory(projectId);

  const status = job.data?.status;
  const running = structure.isPending || (jobId !== null && !job.data) || status === "queued" || status === "running";
  const result = status === "succeeded" ? parseStructureResult(job.data?.result ?? null) : null;
  const savedVersion = result?.version ?? null;

  useEffect(() => {
    if (savedVersion) void queryClient.invalidateQueries({ queryKey: queryKeys.story(projectId) });
  }, [savedVersion, projectId, queryClient]);

  function start(withAnswers: Answer[]) {
    const body: StructureBody = {
      storyline: form.storyline,
      characters: orNull(form.characters),
      locations: orNull(form.locations),
      product: orNull(form.product),
      dialogue: orNull(form.dialogue),
      style: orNull(form.style),
      language: form.language === "" ? null : form.language,
      target_seconds: form.target,
      library_picks: [],
      answers: withAnswers,
    };
    structure.mutate(body, { onSuccess: (j) => setJobId(j.id) });
  }

  function resolve(answered: Answer[], skipped: { path: string; question: string }[]) {
    if (answered.length === 0 && result?.draftYaml) {
      saveDraft.mutate(result.draftYaml);
      return;
    }
    const next = [
      ...answers,
      ...answered,
      ...(answered.length === 0 ? skipped.map((q) => ({ ...q, answer: SKIPPED })) : []),
    ];
    setAnswers(next);
    start(next);
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    setImportErrors([]);
    try {
      importStory.mutate(await file.text(), {
        onError: (e) => setImportErrors(e instanceof StoryInvalidError ? e.errors.map(formatStoryError) : [e.message]),
      });
    } catch {
      setImportErrors(["Could not read that file."]);
    }
  }

  const failure = structure.isError ? structure.error.message : null;
  const questions = result && result.questions.length > 0 ? result.questions : null;

  return (
    <section aria-label="Story input">
      <h2>Describe your story</h2>
      <label className="field">
        Storyline
        <textarea
          rows={5}
          value={form.storyline}
          onChange={(e) => setForm({ ...form, storyline: e.target.value })}
        />
      </label>
      <Section title="Characters">
        <textarea
          aria-label="Characters"
          rows={3}
          value={form.characters}
          onChange={(e) => setForm({ ...form, characters: e.target.value })}
        />
      </Section>
      <Section title="Backgrounds/locations">
        <textarea
          aria-label="Backgrounds/locations"
          rows={3}
          value={form.locations}
          onChange={(e) => setForm({ ...form, locations: e.target.value })}
        />
      </Section>
      <Section title="Product placement">
        <textarea
          aria-label="Product placement"
          rows={3}
          value={form.product}
          onChange={(e) => setForm({ ...form, product: e.target.value })}
        />
      </Section>
      <Section title="Dialogue">
        <textarea
          aria-label="Dialogue"
          rows={3}
          value={form.dialogue}
          onChange={(e) => setForm({ ...form, dialogue: e.target.value })}
        />
      </Section>
      <Section title="Style">
        <input
          type="text"
          aria-label="Style"
          value={form.style}
          onChange={(e) => setForm({ ...form, style: e.target.value })}
        />
      </Section>
      <Section title="Language">
        <select
          aria-label="Language"
          value={form.language}
          onChange={(e) => setForm({ ...form, language: e.target.value as Form["language"] })}
        >
          <option value="">Auto</option>
          <option value="hindi">Hindi</option>
          <option value="english">English</option>
          <option value="hinglish">Hinglish</option>
        </select>
      </Section>
      <Section title="Target length">
        <input
          type="number"
          aria-label="Target length (seconds)"
          min={1}
          max={60}
          value={form.target}
          onChange={(e) => setForm({ ...form, target: Math.min(60, Math.max(1, Number(e.target.value) || 12)) })}
        />
      </Section>
      <Section title="Use characters from library">
        <p>No saved characters yet. They appear here after Cast (coming later).</p>
      </Section>

      <div className="actions">
        <button type="button" disabled={form.storyline.trim() === "" || running} onClick={() => start(answers)}>
          {running ? "Structuring your story…" : "Structure my story"}
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

      {importErrors.length > 0 ? (
        <ul aria-label="Import errors" className="errors">
          {importErrors.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : null}

      <StructureStatus job={job.data} error={failure} onRetry={() => start(answers)} />
      {questions ? <GapQuestions key={job.data?.id} questions={questions} disabled={running} onResolve={resolve} /> : null}
    </section>
  );
}
