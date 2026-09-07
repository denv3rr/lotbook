import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";

type ModalProps = {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
};

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || !open) return;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    return () => { dialog.close(); trigger?.focus(); };
  }, [open]);

  return (
    <dialog ref={dialogRef} aria-labelledby={titleId} aria-describedby={description ? `${titleId}-description` : undefined}
      onKeyDown={event => {
        if (event.key !== "Tab") return;
        const targets = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')).filter(element => element.getClientRects().length > 0);
        const first = targets[0], last = targets[targets.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="clear-dialog m-auto w-[calc(100%-2rem)] max-w-xl max-h-[90dvh] overflow-y-auto rounded-2xl border border-slate-600 bg-slate-950 p-0 text-slate-100 shadow-xl">
      {open ? <div>
        <div className="border-b border-slate-800 px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id={titleId} className="text-lg font-semibold text-slate-100">{title}</h2>
              {description ? (
                <p id={`${titleId}-description`} className="mt-1 text-xs text-slate-400">{description}</p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-slate-700/70 px-2 py-1 text-[11px] text-slate-300 hover:border-slate-500"
              aria-label="Close modal"
            >
              Close
            </button>
          </div>
        </div>
        <div className="px-5 py-4 text-sm text-slate-200">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-slate-800 px-5 py-4">
            {footer}
          </div>
        ) : null}
      </div> : null}
    </dialog>
  );
}
