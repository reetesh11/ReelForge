import { useDialog } from "@/components/useDialog";

export function ApproveDialog({
  warning,
  onConfirm,
  onCancel,
}: {
  warning: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useDialog(onCancel);
  return (
    <div role="dialog" aria-label="Approve this image" className="dialog">
      <p>{warning}</p>
      <div className="actions">
        <button type="button" className="btn btn-primary" onClick={onConfirm}>
          Approve anyway
        </button>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
