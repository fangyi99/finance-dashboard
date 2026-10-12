// A one-shot message passed from one screen to the one it returns to — e.g. the add-form
// closing and the list saying "Added Rent". Plain module state is enough: it's read once
// and cleared, and unlike router params it works the same going *back*.
let pending: string | null = null;

export function setFlash(message: string): void {
  pending = message;
}

export function takeFlash(): string | null {
  const message = pending;
  pending = null;
  return message;
}
