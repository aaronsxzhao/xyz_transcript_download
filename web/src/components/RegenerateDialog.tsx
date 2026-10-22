import { useDialog } from "../lib/reading";
export default function RegenerateDialog({
  description,
  onClose,
  onConfirm,
}: {
  description: string;
  onClose: () => void;
  onConfirm: () => void;
}) {
  useDialog(true, onClose);
  return (
    <div className="reader-confirm-backdrop" onClick={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Regenerate summary"
        className="reader-confirm"
        onClick={(event) => event.stopPropagation()}
      >
        <h2>Regenerate summary?</h2>
        <p>{description}</p>
        <div>
          <button className="reader-action" onClick={onClose}>
            Cancel
          </button>
          <button
            className="reader-action reader-action-outlined"
            onClick={() => {
              onClose();
              onConfirm();
            }}
          >
            Regenerate
          </button>
        </div>
      </section>
    </div>
  );
}
