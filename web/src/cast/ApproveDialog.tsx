export function ApproveDialog({
  warning,
  onConfirm,
  onCancel,
}: {
  warning: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div role="dialog" aria-label="Approve this image" className="dialog">
      <p>{warning}</p>
      <div className="actions">
        <button type="button" onClick={onConfirm}>
          Approve anyway
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
