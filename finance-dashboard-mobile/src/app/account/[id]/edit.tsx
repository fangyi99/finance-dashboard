import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Button,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";

import { API_URL } from "@/constants/config";
import { Dropdown } from "@/components/Dropdown";

const INSTITUTIONS = ["POSB", "DBS", "OCBC", "UOB", "Other"];

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Failed to save changes";
}

export default function EditAccountScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [institution, setInstitution] = useState("Other");
  const [customInstitution, setCustomInstitution] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    fetch(`${API_URL}/accounts/by-id/${id}`)
      .then((res) => res.json())
      .then((acc) => {
        const known = INSTITUTIONS.includes(acc.institution_name);
        setInstitution(known ? acc.institution_name : "Other");
        setCustomInstitution(known ? "" : (acc.institution_name ?? ""));
        setDisplayName(acc.display_name ?? "");
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    setError("");
    const institutionName =
      institution === "Other" ? customInstitution.trim() : institution;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/accounts/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: displayName.trim() || null,
          institution_name: institutionName || null,
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

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;

  return (
    <>
      <Stack.Screen options={{ title: "Edit Account" }} />
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
        {/* Currency isn't editable here — it's fixed at creation, since changing it after
            transactions have already been imported under the old currency would be misleading. */}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={{ marginTop: 24 }}>
          <Button
            title={saving ? "Saving..." : "Save changes"}
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
  error: { color: "red", marginTop: 16 },
});
