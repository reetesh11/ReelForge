import type { ReactNode } from "react";

export function StateMessage({ tone, children }: { tone?: "error"; children: ReactNode }) {
  return <p className={`state-message${tone === "error" ? " error" : ""}`}>{children}</p>;
}
