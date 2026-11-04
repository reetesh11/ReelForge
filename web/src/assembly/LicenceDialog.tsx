import type { LicenceWarning } from "@/api/assembly";

export function LicenceDialog({
  warnings,
  onExport,
  onCancel,
}: {
  warnings: LicenceWarning[];
  onExport: () => void;
  onCancel: () => void;
}) {
  return (
    <div role="dialog" aria-modal="true" aria-label="Licence check before export" className="card">
      <h3>Licence check before export</h3>
      <p>
        Some models used in this reel are non-commercial or have no licence recorded. Exporting is allowed, but check
        you may publish this reel.
      </p>
      <ul>
        {warnings.map((w) => (
          <li key={`${w.model}-${w.version}`}>{`${w.model} ${w.version} - ${w.licence.trim() ? w.licence : "Licence not filled in"}`}</li>
        ))}
      </ul>
      <div className="actions">
        <button type="button" onClick={onExport}>
          Export anyway
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
