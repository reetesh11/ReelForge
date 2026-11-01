import { useState } from "react";
import { useLibraryCharacters } from "@/api/library";

export function LibraryPicker({
  targets,
  fixedKey,
  onPick,
  onClose,
}: {
  targets: Array<{ key: string; name: string }>;
  fixedKey?: string;
  onPick: (key: string, characterId: string) => void;
  onClose: () => void;
}) {
  const library = useLibraryCharacters();
  const [target, setTarget] = useState(fixedKey ?? targets[0]?.key ?? "");

  return (
    <div role="dialog" aria-label="Choose from library" className="dialog">
      <h3>Choose from library</h3>
      {fixedKey ? null : (
        <label className="field">
          Use for character
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {targets.map((t) => (
              <option key={t.key} value={t.key}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {library.isPending ? <p>Loading...</p> : null}
      {library.isError ? <p>Couldn't load the library.</p> : null}
      {library.data && library.data.length === 0 ? (
        <p>No characters in your library yet. Approve a cast to save characters here.</p>
      ) : null}
      <ul className="list">
        {(library.data ?? []).map((c) => (
          <li key={c.id} className="row">
            <span>{c.name}</span>
            <button
              type="button"
              aria-label={`Use ${c.name}`}
              disabled={!c.master_image_url || !target}
              onClick={() => onPick(target, c.id)}
            >
              {c.master_image_url ? "Use" : "No image"}
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </div>
  );
}
