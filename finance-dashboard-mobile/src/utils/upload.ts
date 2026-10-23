// Attaching a file to a form works differently on a phone and in a browser.
//
//   Phone:  React Native's FormData takes a small object: { uri, name, type }.
//   Web:    a browser's FormData needs a real File (or Blob). Give it that same object and the browser quietly
//           sends the text "[object Object]" instead, and the server answers 422 ("Expected UploadFile").
//
// expo-document-picker hands web a ready-made File as `asset.file`. If it ever doesn't, the blob: URI is fetched.
//
// The Content-Type header differs too. On web, leave it to the browser: it adds the "boundary" that separates the
// parts of the upload. Set it by hand and the boundary is lost (the server answers 400, "Missing boundary").

import { Platform } from "react-native";

export interface PickedFile {
  uri: string;
  name?: string | null;
  mimeType?: string | null;
  file?: File; // web only
}

export async function appendFile(
  form: FormData,
  field: string,
  asset: PickedFile,
  defaults: { name: string; type: string } = {
    name: "statement.pdf",
    type: "application/pdf",
  },
): Promise<void> {
  const name = asset.name ?? defaults.name;
  if (Platform.OS === "web") {
    const blob: Blob = asset.file ?? (await (await fetch(asset.uri)).blob());
    (form as any).append(field, blob, name); // (React Native's typings only know the two-argument form)
    return;
  }
  form.append(field, {
    uri: asset.uri,
    name,
    type: asset.mimeType ?? defaults.type,
  } as any);
}

export function uploadHeaders(): Record<string, string> {
  return Platform.OS === "web" ? {} : { "Content-Type": "multipart/form-data" };
}
