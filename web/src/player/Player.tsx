import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { SafeZoneOverlay } from "./SafeZoneOverlay";

const SPEEDS = [0.5, 1, 1.5, 2];

export interface PlayerProps {
  src: string;
  label: string;
  loop?: boolean;
  muted?: boolean;
  autoPlay?: boolean;
  width?: number;
  fps?: number;
  showSafeZone?: boolean;
  controls?: boolean;
  /** Give the player the `group` role. Screens that already count groups turn this off. */
  grouped?: boolean;
}

export function Player({
  src,
  label,
  loop = false,
  muted = false,
  autoPlay = false,
  width = 270,
  fps = 24,
  showSafeZone = false,
  controls = true,
  grouped = true,
}: PlayerProps) {
  const video = useRef<HTMLVideoElement>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);
  const [looping, setLooping] = useState(loop);
  const [isMuted, setIsMuted] = useState(muted);
  const [speed, setSpeed] = useState(1);
  const [zone, setZone] = useState(showSafeZone);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState(0);

  useEffect(() => {
    if (video.current) video.current.muted = isMuted;
  }, [isMuted, attempt]);
  useEffect(() => {
    if (video.current) video.current.playbackRate = speed;
  }, [speed, attempt]);

  const step = (frames: number) => {
    const v = video.current;
    if (!v) return;
    v.pause();
    setPlaying(false);
    const next = v.currentTime + frames / fps;
    const upper = Number.isFinite(v.duration) ? v.duration : Infinity;
    v.currentTime = Math.min(Math.max(0, next), upper);
    setTime(v.currentTime);
  };

  const toggle = () => {
    const v = video.current;
    if (!v) return;
    if (playing) {
      v.pause();
      setPlaying(false);
    } else {
      void Promise.resolve(v.play()).catch(() => setPlaying(false));
      setPlaying(true);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLElement>) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "SELECT") return;
    if (e.key === "ArrowRight") {
      e.preventDefault();
      step(1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      step(-1);
    }
  };

  const retry = () => {
    setFailed(false);
    setLoading(true);
    setAttempt((n) => n + 1);
  };

  return (
    <div
      className="player"
      role={grouped ? "group" : undefined}
      aria-label={`${label} player`}
      tabIndex={0}
      onKeyDown={onKey}
    >
      <div className="player-frame" style={{ width }}>
        <video
          key={attempt}
          ref={video}
          aria-label={label}
          src={src}
          loop={looping}
          muted={isMuted}
          autoPlay={autoPlay}
          playsInline
          preload="metadata"
          onLoadedData={() => setLoading(false)}
          onLoadedMetadata={(e) => setLength(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : 0)}
          onError={() => {
            setLoading(false);
            setFailed(true);
          }}
          onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
        />
        {zone ? <SafeZoneOverlay /> : null}
      </div>
      {loading && !failed ? <p className="meta">Loading video...</p> : null}
      {failed ? (
        <p role="status">
          Couldn't load this video.{" "}
          <button type="button" className="btn btn-secondary" onClick={retry}>
            Retry
          </button>
        </p>
      ) : null}
      {controls ? (
        <div className="player-controls actions">
          <button type="button" className="btn btn-secondary" onClick={toggle}>
            {playing ? "Pause" : "Play"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => step(-1)}>
            Previous frame
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => step(1)}>
            Next frame
          </button>
          <button type="button" className="btn btn-secondary" aria-pressed={looping} onClick={() => setLooping((v) => !v)}>
            Loop
          </button>
          <select
            aria-label="Speed"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>{`${s}x`}</option>
            ))}
          </select>
          <input
            type="range"
            aria-label="Scrub"
            min={0}
            max={length || 0}
            step={1 / fps}
            value={Math.min(time, length || 0)}
            onChange={(e) => {
              const v = video.current;
              if (!v) return;
              v.currentTime = Number(e.target.value);
              setTime(v.currentTime);
            }}
          />
          <button type="button" className="btn btn-secondary" onClick={() => setIsMuted((m) => !m)}>
            {isMuted ? "Unmute" : "Mute"}
          </button>
          <button type="button" className="btn btn-secondary" aria-pressed={zone} onClick={() => setZone((z) => !z)}>
            Safe-zone overlay
          </button>
        </div>
      ) : null}
    </div>
  );
}
