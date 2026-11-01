import { useState } from "react";
import type { CastCandidate } from "@/api/cast";

function Details({ candidate, onClose }: { candidate: CastCandidate; onClose: () => void }) {
  return (
    <div role="dialog" aria-label={`Candidate seed ${candidate.seed} details`} className="dialog">
      <img src={candidate.image_url} alt={`Enlarged seed ${candidate.seed}`} className="enlarged" />
      <p>{`Prompt: ${candidate.prompt}`}</p>
      <p>{`Seed: ${candidate.seed}`}</p>
      <p>{`Model: ${candidate.model}`}</p>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </div>
  );
}

function Compare({ pair, onClose }: { pair: CastCandidate[]; onClose: () => void }) {
  return (
    <div role="dialog" aria-label="Compare candidates" className="dialog">
      <div className="compare">
        {pair.map((c) => (
          <figure key={c.id}>
            <img src={c.image_url} alt={`Compared seed ${c.seed}`} className="enlarged" />
            <figcaption>{`Seed ${c.seed}`}</figcaption>
          </figure>
        ))}
      </div>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </div>
  );
}

export function CandidateGrid({
  candidates,
  selectedId,
  onSelect,
}: {
  candidates: CastCandidate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [enlarged, setEnlarged] = useState<string | null>(null);
  const [compared, setCompared] = useState<string[]>([]);
  const detail = candidates.find((c) => c.id === enlarged);
  const pair = candidates.filter((c) => compared.includes(c.id));

  const toggleCompare = (id: string) =>
    setCompared((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id].slice(-2)));

  return (
    <div role="radiogroup" aria-label="Candidates">
      <ul className="tiles">
        {candidates.map((c) => (
          <li key={c.id} aria-label={`Candidate seed ${c.seed}`} className={c.id === selectedId ? "tile selected" : "tile"}>
            <img src={c.image_url} alt={`Candidate seed ${c.seed}`} loading="lazy" />
            <div className="actions">
              <button
                type="button"
                role="radio"
                aria-checked={c.id === selectedId}
                aria-label={`Select candidate seed ${c.seed}`}
                onClick={() => onSelect(c.id)}
              >
                {c.id === selectedId ? "Selected" : "Select"}
              </button>
              <button type="button" aria-label={`Enlarge seed ${c.seed}`} onClick={() => setEnlarged(c.id)}>
                Enlarge
              </button>
              <button
                type="button"
                aria-label={`Compare seed ${c.seed}`}
                aria-pressed={compared.includes(c.id)}
                onClick={() => toggleCompare(c.id)}
              >
                Compare
              </button>
            </div>
          </li>
        ))}
      </ul>
      {detail ? <Details candidate={detail} onClose={() => setEnlarged(null)} /> : null}
      {pair.length === 2 ? <Compare pair={pair} onClose={() => setCompared([])} /> : null}
    </div>
  );
}
