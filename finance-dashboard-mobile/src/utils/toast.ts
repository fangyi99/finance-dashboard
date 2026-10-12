// A tiny toast bus: any screen can call showToast(); one <ToastHost /> at the root of the
// app listens and draws it. It lives at the root (not on a screen) so a toast survives the
// screen that triggered it closing — e.g. "Saved" appearing on the screen you've just gone
// back to.
export type ToastKind = "success" | "error";

export interface Toast {
  id: number;
  message: string;
  kind: ToastKind;
}

type Listener = (toast: Toast) => void;

let nextId = 1;
const listeners = new Set<Listener>();

export function showToast(message: string, kind: ToastKind = "success"): void {
  const toast: Toast = { id: nextId++, message, kind };
  listeners.forEach((listener) => listener(toast));
}

// Returns the function that stops listening.
export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
