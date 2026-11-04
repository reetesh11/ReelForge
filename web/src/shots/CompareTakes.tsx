import { useState } from "react";
import type { Shot, ShotTake } from "@/api/shots";

function Side({
  label,
  take,
  onMakeActive,
}: {
  label: string;
  take: ShotTake;
  onMakeActive: (id: string) => void;
}) {
  return (
    <div>
      <p className="meta">{`${label}: Take ${take.take_no}${take.active ? " - Active" : ""}`}</p>
      <video aria-label={`${label} video`} src={take.video_url} loop muted autoPlay playsInline width={180} />
      <button type="button" disabled={take.active} onClick={() => onMakeActive(take.id)}>
        Make active
      </button>
    </div>
  );
}

export function CompareTakes({
  shot,
  onMakeActive,
  onClose,
}: {
  shot: Shot;
  onMakeActive: (takeId: string) => void;
  onClose: () => void;
}) {
  const active = shot.takes.find((t) => t.active) ?? shot.takes[0];
  const others = shot.takes.filter((t) => t.id !== active?.id);
  const [otherId, setOtherId] = useState(others[others.length - 1]?.id ?? "");
  const other = shot.takes.find((t) => t.id === otherId) ?? others[0];
  if (!active || !other) return null;
  return (
    <div role="dialog" aria-modal="true" aria-label={`Compare takes for scene ${shot.scene_id}`} className="card">
      <label className="field">
        Compare with
        <select aria-label="Compare with" value={other.id} onChange={(e) => setOtherId(e.target.value)}>
          {others.map((t) => (
            <option key={t.id} value={t.id}>{`Take ${t.take_no}`}</option>
          ))}
        </select>
      </label>
      <div className="actions">
        <Side label="Left" take={active} onMakeActive={onMakeActive} />
        <Side label="Right" take={other} onMakeActive={onMakeActive} />
      </div>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </div>
  );
}
