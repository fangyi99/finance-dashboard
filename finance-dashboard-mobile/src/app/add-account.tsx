import { useState } from "react";
import {
  Button,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Stack, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { CURRENCIES } from "@/constants/currencies";
import { Dropdown } from "@/components/Dropdown";

const INSTITUTIONS = ["POSB", "DBS", "OCBC", "UOB", "Other"];

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Failed to save account";
}

export default function AddAccountScreen() {
  const router = useRouter();
  const [institution, setInstitution] = useState("POSB");
  const [customInstitution, setCustomInstitution] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [currency, setCurrency] = useState("SGD");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    setError("");
    const institutionName =
      institution === "Other" ? customInstitution.trim() : institution;

    if (!institutionName) {
      setError(
        institution === "Other"
          ? "Enter the institution name"
          : "Pick an institution",
      );
      return;
    }

    setSaving(true);
    try {
      // PDF e-statement is the only import method built so far, so it's set directly
      // rather than asked as a choice (see the earlier CSV/PDF decision).
      const res = await fetch(`${API_URL}/accounts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: CURRENT_USER_ID,
          source: "pdf_import",
          display_name: displayName.trim() || null,
          institution_name: institutionName,
          currency,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(formatDetail(data.detail));
      router.back();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Stack.Screen options={{ title: "Add Account" }} />
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.label}>Display Name</Text>
        <TextInput
          placeholder="e.g. Emergency Fund"
          value={displayName}
          onChangeText={setDisplayName}
          style={styles.input}
        />

        <Dropdown
          label="Institution"
          value={institution}
          options={INSTITUTIONS}
          onChange={setInstitution}
        />
        {institution === "Other" && (
          <TextInput
            placeholder="Institution name"
            value={customInstitution}
            onChangeText={setCustomInstitution}
            style={styles.input}
          />
        )}

        <Dropdown
          label="Currency"
          value={currency}
          options={CURRENCIES}
          onChange={setCurrency}
        />
        <Text style={styles.hint}>
          Cards that hold several currencies aren't supported yet — pick the one
          you'll track for this account.
        </Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={{ marginTop: 24 }}>
          <Button
            title={saving ? "Saving..." : "Save account"}
            onPress={handleSave}
            disabled={saving}
          />
        </View>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20 },
  label: { fontWeight: "600", marginTop: 16, marginBottom: 8 },
  input: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    padding: 10,
    marginTop: 8,
  },
  hint: { color: "#999", fontSize: 12, marginTop: 8 },
  error: { color: "red", marginTop: 16 },
});
