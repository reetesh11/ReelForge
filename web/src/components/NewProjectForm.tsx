import { useState, type FormEvent } from "react";
import { useCreateProject } from "@/api/queries";

export function NewProjectForm({ onDone }: { onDone: () => void }) {
  const [title, setTitle] = useState("");
  const create = useCreateProject();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    create.mutate(trimmed, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} className="row">
      <label>
        Project title
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
      </label>
      <button type="submit" disabled={create.isPending}>
        Create
      </button>
      {create.isError ? <span className="meta">Couldn't create the project.</span> : null}
    </form>
  );
}
