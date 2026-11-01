import { useState } from "react";
import { useParams } from "react-router-dom";
import { useLibraryCharacter, usePatchLibraryCharacter, type LibraryCharacter } from "@/api/library";

const split = (text: string): string[] =>
  text
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");

function DetailForm({ character }: { character: LibraryCharacter }) {
  const patch = usePatchLibraryCharacter(character.id);
  const [name, setName] = useState(character.name);
  const [aliases, setAliases] = useState(character.aliases.join(", "));
  const [tags, setTags] = useState(character.tags.join(", "));

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        patch.mutate({ name, aliases: split(aliases), tags: split(tags) });
      }}
    >
      {character.master_image_url ? (
        <img src={character.master_image_url} alt={`Master of ${character.name}`} className="master" />
      ) : null}
      <p className="meta">{character.look_text}</p>
      <label className="field">
        Name
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        Aliases
        <input type="text" value={aliases} onChange={(e) => setAliases(e.target.value)} />
      </label>
      <label className="field">
        Tags
        <input type="text" value={tags} onChange={(e) => setTags(e.target.value)} />
      </label>
      <div className="actions">
        <button type="submit" disabled={patch.isPending}>
          Save
        </button>
      </div>
      {patch.isError ? <p role="alert">{patch.error.message}</p> : null}
      {patch.isSuccess ? <p className="meta">Saved.</p> : null}
    </form>
  );
}

export function LibraryDetail() {
  const { characterId = "" } = useParams();
  const character = useLibraryCharacter(characterId);

  if (character.isPending) return <p>Loading...</p>;
  if (character.isError) return <p>Couldn't load this character.</p>;
  return (
    <section>
      <h1>{character.data.name}</h1>
      <DetailForm key={character.data.id} character={character.data} />
    </section>
  );
}
