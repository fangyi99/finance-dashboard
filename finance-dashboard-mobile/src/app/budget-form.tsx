import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";

import { Dropdown } from "@/components/dropdown";
import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import {
  Budget,
  BudgetFormState,
  buildBudgetPayload,
  buildBudgetUpdate,
  EMPTY_BUDGET_FORM,
  formFromBudget,
  validateBudgetForm,
} from "@/utils/budget";
import { categoryChoices, sanitizeAmount } from "@/utils/recurring";
import { showToast } from "@/utils/toast";

const ALL_SPENDING = "All spending";

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Something went wrong";
}

// Adding a budget, and — given an `id` — editing one. The same two things either way: what
// to call it and how much it is, plus (optionally) which category it watches.
export default function BudgetFormScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const editingId = id ? String(id) : null;

  const [form, setForm] = useState<BudgetFormState>(EMPTY_BUDGET_FORM);
  const [categories, setCategories] = useState<any[]>([]);
  const [loading, setLoading] = useState(!!editingId);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (patch: Partial<BudgetFormState>) =>
    setForm((current) => ({ ...current, ...patch }));

  useEffect(() => {
    fetch(`${API_URL}/categories/${CURRENT_USER_ID}`)
      .then((res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((list) => setCategories(Array.isArray(list) ? list : []))
      .catch(() => setError("Couldn't load your categories"));
  }, []);

  useEffect(() => {
    if (!editingId) return;
    setLoading(true);
    setLoadError("");
    fetch(`${API_URL}/budgets/by-id/${editingId}`)
      .then((res) => {
        if (!res.ok) throw new Error("Couldn't load this budget");
        return res.json();
      })
      .then((budget: Budget) => setForm(formFromBudget(budget)))
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false));
  }, [editingId]);

  // A budget watches spending, so only expense categories are offered — and not
  // "Uncategorized": spending only counts towards a budget once it's been sorted into a real
  // category, so a budget on Uncategorized would always read $0.
  const options = useMemo(
    () =>
      categoryChoices(
        categories.filter(
          (c) => !(c.name === "Uncategorized" && c.is_system_default),
        ),
        "expense",
      ),
    [categories],
  );

  // A budget made before that rule may still point at Uncategorized. It's shown as "All
  // spending", and that's also what's saved — the form always saves what it shows. (Only
  // once the categories have loaded, so a failed load never clears anyone's category.)
  const categoryId =
    categories.length > 0 &&
    form.categoryId &&
    !options.some((c) => c.id === form.categoryId)
      ? null
      : form.categoryId;
  const selectedCategory =
    options.find((c) => c.id === categoryId)?.label ?? ALL_SPENDING;

  const goBack = () =>
    router.canGoBack() ? router.back() : router.replace("/budget" as any);

  const submit = async () => {
    const toSave = { ...form, categoryId };
    const problem = validateBudgetForm(toSave);
    if (problem) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const res = await fetch(
        editingId ? `${API_URL}/budgets/${editingId}` : `${API_URL}/budgets`,
        {
          method: editingId ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            editingId
              ? buildBudgetUpdate(toSave)
              : buildBudgetPayload(CURRENT_USER_ID, toSave),
          ),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(formatDetail(data.detail));
      // The Budget tab reloads when it comes back into view, so it shows the change.
      showToast(editingId ? "Saved" : `Added "${data.name}"`);
      goBack();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const title = editingId ? "Edit budget" : "New budget";

  if (editingId && loading) {
    return (
      <>
        <Stack.Screen options={{ title }} />
        <ActivityIndicator style={{ marginTop: 40 }} />
      </>
    );
  }

  if (editingId && loadError) {
    return (
      <>
        <Stack.Screen options={{ title }} />
        <Text style={[styles.error, { padding: 16 }]}>{loadError}</Text>
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
        <Text style={styles.label}>Budget name</Text>
        <TextInput
          value={form.name}
          onChangeText={(name) => set({ name })}
          placeholder="e.g. Groceries"
          maxLength={60}
          style={styles.input}
        />

        <Text style={styles.label}>Budget amount</Text>
        <TextInput
          value={form.amount}
          onChangeText={(text) => set({ amount: sanitizeAmount(text) })}
          placeholder="0.00"
          keyboardType="decimal-pad"
          style={styles.input}
        />
        <Text style={styles.hint}>The most you want to spend in a month.</Text>

        <Dropdown
          label="Category (optional)"
          value={selectedCategory}
          options={[ALL_SPENDING, ...options.map((c) => c.label)]}
          onChange={(label) =>
            set({
              categoryId: options.find((c) => c.label === label)?.id ?? null,
            })
          }
        />
        <Text style={styles.hint}>
          {categoryId
            ? "Counts spending in this category and its subcategories."
            : "Counts all your categorised spending each month."}
        </Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable style={styles.primary} disabled={saving} onPress={submit}>
          <Text style={styles.primaryText}>
            {editingId
              ? saving
                ? "Saving..."
                : "Save"
              : saving
                ? "Adding..."
                : "Add"}
          </Text>
        </Pressable>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  label: { fontWeight: "600", marginTop: 16, marginBottom: 8 },
  hint: { color: "#999", fontSize: 12, marginTop: 6 },
  input: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    padding: 12,
    fontSize: 15,
  },
  error: { color: "red", marginTop: 14 },
  primary: {
    backgroundColor: "#007AFF",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 24,
  },
  primaryText: { color: "#fff", fontWeight: "600", fontSize: 16 },
});
