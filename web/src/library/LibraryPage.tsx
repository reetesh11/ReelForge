import { Link } from "react-router-dom";
import { useLibraryCharacters } from "@/api/library";

export function LibraryPage() {
  const library = useLibraryCharacters();
  const nameOf = (id: string | null | undefined) => library.data?.find((c) => c.id === id)?.name ?? "a deleted character";

  return (
    <section>
      <h1>Library</h1>
      {library.isPending ? <p>Loading...</p> : null}
      {library.isError ? <p>Couldn't load the library.</p> : null}
      {library.data && library.data.length === 0 ? (
        <p>No characters in your library yet. Approve a cast to save characters here.</p>
      ) : null}
      {library.data && library.data.length > 0 ? (
        <ul aria-label="Library characters" className="tiles">
          {library.data.map((c) => (
            <li key={c.id} aria-label={`Library character: ${c.name}`} className="card">
              {c.master_image_url ? <img src={c.master_image_url} alt={`Master of ${c.name}`} className="master" /> : null}
              <Link to={`/library/${c.id}`}>{c.name}</Link>
              {c.aliases.length > 0 ? <p className="meta">{`Aliases: ${c.aliases.join(", ")}`}</p> : null}
              {c.tags.length > 0 ? <p className="meta">{`Tags: ${c.tags.join(", ")}`}</p> : null}
              <p className="meta">{`Created ${new Date(c.created_at).toLocaleDateString()}`}</p>
              {c.parent_character_id ? <p className="meta">{`Variant of ${nameOf(c.parent_character_id)}`}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
