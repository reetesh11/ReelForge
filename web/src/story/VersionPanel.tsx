import type { StoryVersion } from "@/api/story";

export function versionLabel(v: StoryVersion): string {
  return v.is_current ? `v${v.version} (current)` : `v${v.version}`;
}

export function VersionPanel({
  versions,
  viewing,
  onSelect,
}: {
  versions: StoryVersion[];
  viewing: number | null;
  onSelect: (version: number | null) => void;
}) {
  return (
    <details className="fold">
      <summary>Versions</summary>
      <ul className="list" aria-label="Version history">
        {versions.map((v) => {
          const selected = viewing === v.version || (viewing === null && v.is_current);
          return (
            <li key={v.id} className="row">
              <button
                type="button"
                className="btn btn-secondary"
                aria-pressed={selected}
                onClick={() => onSelect(v.is_current ? null : v.version)}
              >
                {versionLabel(v)}
              </button>
              {v.is_current ? null : <span className="meta">{new Date(v.created_at).toLocaleString()}</span>}
              {v.approved_at ? <span className="chip chip-green">Approved</span> : null}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
