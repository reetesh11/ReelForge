import { Notice } from "@/components/Notice";

export function LicenceBanner({ warning }: { warning: string }) {
  return (
    <div role="status">
      <Notice tone="warning">{warning}</Notice>
    </div>
  );
}
