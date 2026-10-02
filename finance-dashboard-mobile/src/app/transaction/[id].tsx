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
import { Stack, useLocalSearchParams } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { Dropdown } from "@/components/Dropdown";
import { formatDate, formatMoney } from "@/utils/format";
import { Category } from "@/utils/categoryTree";

interface TransactionDetail {
  id: string;
  description_raw: string;
  notes: string | null;
  amount: string;
  currency: string;
  transaction_date: string;
  category_id: string | null;
  category_name: string | null;
}

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Failed to save";
}

export default function TransactionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [transaction, setTransaction] = useState<TransactionDetail | null>(
    null,
  );
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryName, setCategoryName] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetch(`${API_URL}/transactions/by-id/${id}`).then((res) => {
        if (!res.ok) throw new Error("Couldn't load this transaction");
        return res.json();
      }),
      fetch(`${API_URL}/categories/${CURRENT_USER_ID}`).then((res) =>
        res.json(),
      ),
    ])
      .then(([txn, cats]) => {
        setTransaction(txn);
        setCategoryName(txn.category_name || "");
        setNotes(txn.notes || "");
        setCategories(cats);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    setError("");
    setMessage("");
    setSaving(true);
    try {
      const matchedCategory = categories.find((c) => c.name === categoryName);
      const payload: Record<string, unknown> = { notes: notes.trim() || null };
      if (matchedCategory && matchedCategory.id !== transaction?.category_id) {
        payload.category_id = matchedCategory.id;
      }

      const res = await fetch(`${API_URL}/transactions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(formatDetail(data.detail));
      setTransaction(data);
      setMessage("Saved");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (!transaction)
    return <Text style={styles.error}>{error || "Transaction not found"}</Text>;

  return (
    <>
      <Stack.Screen options={{ title: "Transaction" }} />
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        {/* Name and amount reflect what the bank/Stripe actually sent — not editable,
            so the original record is never overwritten by a later correction. */}
        <Text style={styles.label}>Name</Text>
        <Text style={styles.readonly}>{transaction.description_raw}</Text>

        <Text style={styles.label}>Date</Text>
        <Text style={styles.readonly}>
          {formatDate(transaction.transaction_date)}
        </Text>

        <Text style={styles.label}>Amount</Text>
        <Text
          style={[
            styles.readonly,
            {
              color: Number(transaction.amount) < 0 ? "red" : "green",
              fontWeight: "600",
            },
          ]}
        >
          {formatMoney(transaction.amount, transaction.currency)}
        </Text>

        <Dropdown
          label="Category"
          value={categoryName}
          options={categories.map((c) => c.name)}
          onChange={setCategoryName}
        />

        <Text style={styles.label}>Notes (optional)</Text>
        <TextInput
          value={notes}
          onChangeText={setNotes}
          placeholder="e.g. split with roommate"
          style={styles.input}
          multiline
        />

        {message ? <Text style={styles.success}>{message}</Text> : null}
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
  readonly: { fontSize: 15, color: "#333" },
  input: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    padding: 10,
    minHeight: 60,
    textAlignVertical: "top",
  },
  success: { color: "green", marginTop: 16 },
  error: { color: "red", marginTop: 16, padding: 16 },
});
