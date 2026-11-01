import { useState } from "react";
import type { Question } from "@/api/story";

export type Answer = { path: string; question: string; answer: string };

type Status = "open" | "answered" | "skipped";

export function GapQuestions({
  questions,
  disabled,
  onResolve,
}: {
  questions: Question[];
  disabled: boolean;
  onResolve: (answered: Answer[], skipped: Question[]) => void;
}) {
  const [text, setText] = useState<string[]>(() => questions.map(() => ""));
  const [status, setStatus] = useState<Status[]>(() => questions.map(() => "open"));

  function finish(next: Status[], texts: string[]) {
    if (next.some((s) => s === "open")) return;
    const answered: Answer[] = [];
    const skipped: Question[] = [];
    questions.forEach((q, i) => {
      if (next[i] === "answered") answered.push({ path: q.path, question: q.question, answer: texts[i] ?? "" });
      else skipped.push(q);
    });
    onResolve(answered, skipped);
  }

  function mark(i: number, value: Status) {
    const next = status.map((s, j) => (j === i ? value : s));
    setStatus(next);
    finish(next, text);
  }

  return (
    <section aria-label="Questions from the model">
      <p>Before building the story, the model needs a few answers. Skip anything you want left open.</p>
      <ul className="list">
        {questions.map((q, i) => {
          const done = status[i] !== "open";
          return (
            <li key={q.path + i} className="row">
              <label>
                {q.question}
                <input
                  type="text"
                  value={text[i] ?? ""}
                  disabled={done || disabled}
                  onChange={(e) => setText(text.map((t, j) => (j === i ? e.target.value : t)))}
                />
              </label>
              {status[i] === "answered" ? <span className="meta">Answered</span> : null}
              {status[i] === "skipped" ? <span className="meta">Skipped</span> : null}
              <button type="button" disabled={done || disabled || (text[i] ?? "").trim() === ""} onClick={() => mark(i, "answered")}>
                Answer
              </button>
              <button type="button" disabled={done || disabled} onClick={() => mark(i, "skipped")}>
                Skip
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
