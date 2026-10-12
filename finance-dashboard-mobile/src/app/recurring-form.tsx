import { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text } from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";

import { RecurringForm } from "@/components/recurring-form";
import { API_URL } from "@/constants/config";
import { setFlash } from "@/utils/flash";
import { EditableRule } from "@/utils/recurring";
import { showToast } from "@/utils/toast";

// The page for adding a recurring transaction — and, given an `id`, for editing one. Adding
// is reached from the + in the Recurring list's header; editing from tapping a row there.
// Either way it's the same form.
export default function RecurringFormScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const editingId = id ? String(id) : null;

  const [rule, setRule] = useState<EditableRule | null>(null);
  const [loading, setLoading] = useState(!!editingId);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!editingId) return;
    setLoading(true);
    setLoadError("");
    fetch(`${API_URL}/recurring/by-id/${editingId}`)
      .then((res) => {
        if (!res.ok)
          throw new Error("Couldn't load this recurring transaction");
        return res.json();
      })
      .then(setRule)
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false));
  }, [editingId]);

  const goBack = () =>
    router.canGoBack() ? router.back() : router.replace("/recurring" as any);

  const title = editingId ? "Edit recurring" : "New recurring";

  if (editingId && loading) {
    return (
      <>
        <Stack.Screen options={{ title }} />
        <ActivityIndicator style={{ marginTop: 40 }} />
      </>
    );
  }

  if (editingId && !rule) {
    return (
      <>
        <Stack.Screen options={{ title }} />
        <Text style={styles.error}>
          {loadError || "Couldn't load this recurring transaction"}
        </Text>
      </>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title }} />
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
        keyboardShouldPersistTaps="handled"
      >
        <RecurringForm
          editing={rule ?? undefined}
          onCreated={(message) => {
            setFlash(message);
            goBack();
          }}
          onSaved={() => {
            // The list reloads when it comes back into view, so it shows the change.
            showToast("Saved");
            goBack();
          }}
        />
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  error: { color: "red", padding: 16 },
});
