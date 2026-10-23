// Alert.alert does nothing on web: no message appears and its buttons never run. So on a browser every
// "Imported 41 transactions", every error, and every "Are you sure?" (delete, reset the sandbox) would be silent.
//
// This makes Alert.alert work on web, once, for the whole app, so no screen has to change:
//   * no buttons, or one:  a plain browser alert, then that button's action
//   * two or more:         a browser confirm. OK runs the LAST button that isn't "cancel" (the action), and Cancel runs
//                          the cancel button (or the first one). A browser confirm can't relabel its buttons, so the
//                          labels are written into the message: "OK: Review now   Cancel: Later".
//
// Import it once, near the top of your root layout:   import '@/utils/web-alert';
// On a phone it does nothing at all.

import { Alert, AlertButton, Platform } from "react-native";

export function webAlert(
  title: string,
  message?: string,
  buttons?: AlertButton[],
): void {
  const text = [title, message].filter(Boolean).join("\n\n");
  const list = buttons ?? [];
  if (list.length <= 1) {
    window.alert(text);
    list[0]?.onPress?.();
    return;
  }
  const cancel = list.find((b) => b.style === "cancel");
  const actions = list.filter((b) => b !== cancel);
  const positive = actions[actions.length - 1];
  const negative = cancel ?? list.find((b) => b !== positive);
  const ok = window.confirm(
    `${text}\n\nOK: ${positive.text}   Cancel: ${negative?.text ?? "Close"}`,
  );
  (ok ? positive : negative)?.onPress?.();
}

let installed = false;
export function installWebAlert(): void {
  if (installed || Platform.OS !== "web") return;
  installed = true;
  (Alert as any).alert = webAlert;
}

installWebAlert();
