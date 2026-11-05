import type { AudioTake } from "@/api/audio";

export function TakesList({
  cueId,
  takes,
  onPlay,
  onUse,
}: {
  cueId: string;
  takes: AudioTake[];
  onPlay: (url: string) => void;
  onUse: (takeId: string) => void;
}) {
  return (
    <ul aria-label={`Takes of ${cueId}`} className="takes">
      {takes.map((t) => (
        <li key={t.id} className="actions">
          <span>{`take ${t.take_no}`}</span>
          <span className="meta">{`${Number(t.duration_s.toFixed(2))} s`}</span>
          {t.picked ? <span className="badge green">Picked</span> : null}
          {t.stale ? <span className="badge amber">Needs update</span> : null}
          <button type="button" onClick={() => onPlay(t.url)}>
            Play
          </button>
          <button type="button" onClick={() => onUse(t.id)}>
            Use this take
          </button>
        </li>
      ))}
    </ul>
  );
}
