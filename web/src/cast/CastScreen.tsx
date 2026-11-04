import { useState } from "react";
import { useCast, useGenerate, useUseLibrary } from "@/api/cast";
import { StateMessage } from "@/components/StateMessage";
import { BackendDown } from "./BackendDown";
import { CastRow } from "./CastRow";
import { LibraryPicker } from "./LibraryPicker";
import { LicenceBanner } from "./LicenceBanner";

export function CastScreen({ projectId }: { projectId: string }) {
  const cast = useCast(projectId);
  const generate = useGenerate(projectId);
  const useLibrary = useUseLibrary(projectId);
  const [picking, setPicking] = useState(false);

  if (cast.isPending) {
    return (
      <section>
        <h2>Cast</h2>
        <StateMessage>Loading...</StateMessage>
      </section>
    );
  }
  if (!cast.data) return null;
  const { image_backend: backend, characters } = cast.data;
  const backendDown = backend.kind === "draw_things" && !backend.reachable;
  const warning = cast.data.licence_warning ?? null;

  const useMflux = () => {
    for (const c of characters) {
      if (!c.approved && c.state !== "generating") {
        generate.mutate({ key: c.key, body: { backend: "mflux" } });
      }
    }
  };

  return (
    <section aria-label="Cast">
      <h2>Cast</h2>
      {warning ? <LicenceBanner warning={warning} /> : null}
      {backendDown ? (
        <BackendDown
          port={backend.port}
          mfluxAvailable={backend.mflux_available}
          onRetry={() => void cast.refetch()}
          onUseMflux={useMflux}
        />
      ) : null}
      <div className="status-strip" data-testid="status-strip">
        <span>{`${cast.data.approved_count} of ${cast.data.total} characters approved`}</span>
        <button type="button" className="btn btn-ghost" onClick={() => setPicking(true)}>
          Use characters from library
        </button>
      </div>
      {characters.length === 0 ? <p className="state-message">This story has no characters to cast.</p> : null}
      <ul aria-label="Cast characters" className="card-stack">
        {characters.map((item) => (
          <CastRow
            key={item.key}
            projectId={projectId}
            item={item}
            backendDown={backendDown}
            licenceWarning={warning}
            receivedAt={cast.dataUpdatedAt}
          />
        ))}
      </ul>
      {picking ? (
        <LibraryPicker
          targets={characters.map((c) => ({ key: c.key, name: c.name }))}
          onPick={(key, characterId) => {
            useLibrary.mutate({ key, characterId });
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </section>
  );
}
