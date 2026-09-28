import { useState } from "react";
import { View, Text, Button, ActivityIndicator } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { API_URL, CURRENT_USER_ID } from "@/constants/config";

const TEST_ACCOUNT_ID = "3c5c6110-9bf1-4caa-872e-8295fdd4b9fc";
export default function ImportCsvScreen() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  const pickAndUpload = async () => {
    setError("");
    setResult(null);

    const picked = await DocumentPicker.getDocumentAsync({ type: "*/*" });
    if (picked.canceled) return;

    const file = picked.assets[0];
    const formData = new FormData();
    formData.append("account_id", TEST_ACCOUNT_ID);
    formData.append("file", {
      uri: file.uri,
      name: file.name,
      type: file.mimeType || "text/csv",
    } as any);

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/transactions/import-csv`, {
        method: "POST",
        body: formData,
        headers: { "Content-Type": "multipart/form-data" },
      });
      const data = await res.json();
      if (!res.ok)
        throw new Error(JSON.stringify(data.detail) || "Import failed");
      setResult(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ padding: 20, paddingTop: 60 }}>
      <Text style={{ fontSize: 20, fontWeight: "bold", marginBottom: 20 }}>
        Import Transactions
      </Text>
      <Button
        title="Choose CSV File"
        onPress={pickAndUpload}
        disabled={loading}
      />
      {loading && <ActivityIndicator style={{ marginTop: 20 }} />}
      {error ? (
        <Text style={{ color: "red", marginTop: 20 }}>{error}</Text>
      ) : null}
      {result && (
        <View style={{ marginTop: 20 }}>
          <Text>Imported: {result.imported_count}</Text>
          <Text>Skipped: {result.skipped_count}</Text>
          {result.errors.map((e: string, i: number) => (
            <Text key={i} style={{ color: "#999", fontSize: 12 }}>
              {e}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}
