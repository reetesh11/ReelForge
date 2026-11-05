import type { ReactNode } from "react";

export type IconName =
  | "story" | "cast" | "voices" | "frames" | "shots" | "assembly"
  | "check" | "regenerate" | "edit" | "refine" | "upload" | "library" | "play" | "pause" | "stop"
  | "trash" | "reopen" | "enlarge" | "compare" | "info" | "success" | "warning" | "error" | "plus" | "chevron"
  | "mic" | "download" | "save" | "swap";

const PATHS: Record<IconName, ReactNode> = {
  story: <path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4zM8 8h7M8 12h7" />,
  cast: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0" />,
  voices: <path d="M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4" />,
  frames: <path d="M4 5h16v14H4zM4 15l5-5 4 4 3-3 4 4" />,
  shots: <path d="M4 6h11v12H4zM15 10l5-3v10l-5-3" />,
  assembly: <path d="M4 7h16M4 12h10M4 17h13M18 10l3 2-3 2" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  regenerate: <path d="M20 12a8 8 0 1 1-2.5-5.8M20 4v5h-5" />,
  edit: <path d="M4 20h4l11-11-4-4L4 16v4zM13 7l4 4" />,
  refine: <path d="M5 19l9-9M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM18 14l.7 1.3L20 16l-1.3.7L18 18l-.7-1.3L16 16l1.3-.7z" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />,
  library: <path d="M5 4h3v16H5zM10 4h3v16h-3zM15.5 5.5l2.8-.8 3 14.4-2.8.8z" />,
  play: <path d="M8 5v14l11-7z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  stop: <path d="M7 7h10v10H7z" />,
  trash: <path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13M10 11v6M14 11v6" />,
  reopen: <path d="M4 12a8 8 0 1 0 2.5-5.8M4 4v5h5" />,
  enlarge: <path d="M4 10V4h6M20 14v6h-6M4 4l6 6M20 20l-6-6" />,
  compare: <path d="M4 5h7v14H4zM13 5h7v14h-7z" />,
  info: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5v.5" />,
  success: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12.5l3 3 5-6" />,
  warning: <path d="M12 4l9 16H3zM12 10v4M12 17v.5" />,
  error: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9 9l6 6M15 9l-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  chevron: <path d="M9 6l6 6-6 6" />,
  mic: <path d="M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0" />,
  download: <path d="M12 4v12M7 11l5 5 5-5M5 20h14" />,
  save: <path d="M5 4h11l3 3v13H5zM8 4v5h7V4M8 20v-6h8v6" />,
  swap: <path d="M7 7h12l-3-3M17 17H5l3 3" />,
};

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
