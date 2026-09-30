import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Button,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { Dropdown } from "@/components/Dropdown";
import { Category } from "@/utils/categoryTree";

const TYPES = ["expense", "income", "transfer"] as const;
const NONE_PARENT = "None (top-level)";

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Failed to save category";
}

export default function CategoryFormScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const isEdit = Boolean(id);
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [topLevel, setTopLevel] = useState<Category[]>([]);
  const [existing, setExisting] = useState<Category | null>(null);

  const [name, setName] = useState("");
  const [parentName, setParentName] = useState(NONE_PARENT);
  const [type, setType] = useState<(typeof TYPES)[number]>("expense");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/categories/${CURRENT_USER_ID}`).then((res) =>
        res.json(),
      ),
      fetch(`${API_URL}/categories/visibility/${CURRENT_USER_ID}`).then((res) =>
        res.json(),
      ),
    ])
      .then(([all, hidden]: [Category[], { category_id: string }[]]) => {
        const hiddenIds = new Set(hidden.map((h) => h.category_id));
        // Hidden categories aren't offered as a parent — if you don't want to see it in
        // your breakdown, you probably don't want to file new things under it either.
        let parentOptions = all.filter(
          (c) => c.parent_category_id === null && !hiddenIds.has(c.id),
        );

        if (isEdit) {
          const target = all.find((c) => c.id === id);
          if (!target) {
            setError("Category not found");
          } else if (target.is_system_default) {
            setError("Default categories cannot be edited");
          } else {
            // Can't pick itself as a parent, and if it already has children it can't
            // become a subcategory of anything (the backend enforces this too).
            parentOptions = parentOptions.filter((c) => c.id !== target.id);
            setExisting(target);
            setName(target.name);
            setType(target.type);
            if (target.parent_category_id) {
              // Looked up from the full list, not parentOptions, so this still shows
              // correctly even if the category's current parent happens to be hidden.
              const parent = all.find(
                (c) => c.id === target.parent_category_id,
              );
              setParentName(parent?.name ?? NONE_PARENT);
            }
          }
        }
        setTopLevel(parentOptions);
      })
      .catch(() => setError("Couldn't load categories"))
      .finally(() => setLoading(false));
  }, [id]);

  const performSave = async () => {
    const trimmed = name.trim();
    const parent = topLevel.find((c) => c.name === parentName);

    setSaving(true);
    try {
      if (isEdit) {
        const res = await fetch(
          `${API_URL}/categories/${id}?user_id=${CURRENT_USER_ID}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: trimmed,
              parent_category_id: parent ? parent.id : null,
              // Only meaningful when clearing the parent; ignored by the backend otherwise.
              type,
            }),
          },
        );
        const data = await res.json();
        if (!res.ok) throw new Error(formatDetail(data.detail));
      } else {
        const res = await fetch(`${API_URL}/categories`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: CURRENT_USER_ID,
            name: trimmed,
            parent_category_id: parent ? parent.id : null,
            type: parent ? parent.type : type, // ignored by the backend when a parent is set
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(formatDetail(data.detail));
      }
      router.back();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSave = () => {
    setError("");
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Name is required");
      return;
    }

    // A type change (via reparenting, or directly for a top-level category) reclassifies
    // every transaction already sitting in this category, not just future ones — since
    // reports read a transaction's type live from its category, not a frozen copy.
    if (isEdit && existing) {
      const parent = topLevel.find((c) => c.name === parentName);
      const newType = parent ? parent.type : type;
      if (newType !== existing.type) {
        Alert.alert(
          "This changes past transactions too",
          `Every transaction already in "${existing.name}" will now count as ${newType} instead of ${existing.type} in your reports, not just new ones. Continue?`,
          [
            { text: "Cancel", style: "cancel" },
            { text: "Continue", style: "destructive", onPress: performSave },
          ],
        );
        return;
      }
    }

    performSave();
  };

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (isEdit && !existing) {
    return (
      <>
        <Stack.Screen options={{ title: "Edit Category" }} />
        <Text style={styles.error}>{error}</Text>
      </>
    );
  }

  return (
    <>
      <Stack.Screen
        options={{ title: isEdit ? "Edit Category" : "Add Category" }}
      />
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.label}>Name</Text>
        <TextInput
          value={name}
          onChangeText={setName}
          style={styles.input}
          placeholder="e.g. Gifts"
        />

        <Dropdown
          label="Parent category"
          value={parentName}
          options={[NONE_PARENT, ...topLevel.map((c) => c.name)]}
          onChange={setParentName}
        />
        {parentName === NONE_PARENT ? (
          <Dropdown
            label="Type"
            value={type}
            options={[...TYPES]}
            onChange={(v) => setType(v as any)}
          />
        ) : (
          <Text style={styles.hint}>
            Inherits the "{topLevel.find((c) => c.name === parentName)?.type}"
            type from {parentName}.
          </Text>
        )}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={{ marginTop: 24 }}>
          <Button
            title={saving ? "Saving..." : "Save"}
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
  input: { borderWidth: 1, borderColor: "#ddd", borderRadius: 8, padding: 10 },
  hint: { color: "#999", fontSize: 12, marginTop: 12 },
  error: { color: "red", marginTop: 16, padding: 16 },
});
