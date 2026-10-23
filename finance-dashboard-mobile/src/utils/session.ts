// Sandbox mode: whether the app is showing your real data or the sample data.
//
// Switching on asks the backend to set up (or refresh) the sandbox user, then points the whole app at it
// through setCurrentUserId. Switching off points it back at you. Nothing is saved between launches: the
// app always starts in real mode, so you can't leave yourself in the sandbox by accident.
//
//   const { sandbox, busy, version } = useSession();
//
// `version` goes up on every switch and reset. A screen that loads data once (rather than on focus) can put
// it in its effect's dependency list to reload when the data underneath it changes.

import { useSyncExternalStore } from "react";

import { API_URL, REAL_USER_ID, setCurrentUserId } from "@/constants/config";

export interface SessionState {
  sandbox: boolean;
  busy: boolean; // a request to the backend is in flight
  version: number;
}

let state: SessionState = { sandbox: false, busy: false, version: 0 };
const listeners = new Set<() => void>();

function update(patch: Partial<SessionState>) {
  state = { ...state, ...patch }; // a new object each time; useSyncExternalStore compares by identity
  listeners.forEach((listener) => listener());
}

export const getSession = () => state;

export function subscribeSession(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useSession(): SessionState {
  return useSyncExternalStore(subscribeSession, getSession, getSession);
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // not JSON: fall through
  }
  return `The server returned an error (${res.status}).`;
}

async function postDemo(
  path: "/demo/start" | "/demo/reset",
): Promise<{ user_id?: string }> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

function demoUserId(body: { user_id?: string }): string {
  if (!body?.user_id)
    throw new Error("The server didn't say which sandbox user to use.");
  return body.user_id;
}

export async function enterSandbox(): Promise<void> {
  if (state.busy || state.sandbox) return;
  update({ busy: true });
  try {
    const demo = await postDemo("/demo/start");
    setCurrentUserId(demoUserId(demo));
    update({ sandbox: true, busy: false, version: state.version + 1 });
  } catch (e) {
    update({ busy: false }); // nothing changed: still on your own data
    throw e;
  }
}

export function leaveSandbox(): void {
  if (state.busy || !state.sandbox) return;
  setCurrentUserId(REAL_USER_ID);
  update({ sandbox: false, version: state.version + 1 });
}

// Puts the sample data back the way it started. It works whether or not you're in the sandbox: if you're in it, every
// screen reloads; if you're not, the sample data is rebuilt quietly and you stay on your own accounts.
export async function resetSandbox(): Promise<void> {
  if (state.busy) return;
  update({ busy: true });
  try {
    const demo = await postDemo("/demo/reset");
    if (state.sandbox) {
      setCurrentUserId(demoUserId(demo));
      update({ busy: false, version: state.version + 1 });
    } else {
      update({ busy: false }); // nothing on screen is the sandbox's, so nothing needs to reload
    }
  } catch (e) {
    update({ busy: false });
    throw e;
  }
}
