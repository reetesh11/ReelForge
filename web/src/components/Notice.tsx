import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/icons";

const ICONS: Record<string, IconName> = { info: "info", success: "success", warning: "warning", error: "error" };

export function Notice({
  tone = "info",
  role,
  children,
}: {
  tone?: "info" | "success" | "warning" | "error";
  role?: "alert" | "status";
  children: ReactNode;
}) {
  return (
    <div className={`notice ${tone}`} role={role}>
      <Icon name={ICONS[tone] as IconName} />
      <div>{children}</div>
    </div>
  );
}
