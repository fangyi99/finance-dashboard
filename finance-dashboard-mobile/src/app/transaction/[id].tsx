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

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { Checkbox } from "@/components/checkbox";
import { RepeatField } from "@/components/repeat-field";
import { RepeatValue } from "@/components/repeat-picker";
import { Dropdown } from "@/components/Dropdown";
import { formatDate, formatMoney } from "@/utils/format";
import { Category } from "@/utils/categoryTree";
import { dueLabel, repeatLabel, repeatPhrase, Unit } from "@/utils/recurring";
import { showToast } from "@/utils/toast";

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

interface TrackedRule {
  interval_count: number;
  interval_unit: Unit;
  next_due_date: string | null;
}

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Failed to save";
}

export default function TransactionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [transaction, setTransaction] = useState<TransactionDetail | null>(
    null,
  );
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryName, setCategoryName] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // The "make this recurring" tick is only a choice until Save is pressed: nothing is sent
  // when it's ticked. `tracked` is the real state — set if a rule already covers this charge.
  const [makeRecurring, setMakeRecurring] = useState(false);
  const [repeat, setRepeat] = useState<RepeatValue>({
    count: 1,
    unit: "month",
  });
  const [tracked, setTracked] = useState<TrackedRule | null>(null);

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
      // If this lookup fails the screen still works; the box just starts unticked.
      fetch(`${API_URL}/recurring/for-transaction/${id}`)
        .then((res) => res.json())
        .catch(() => ({ rule: null })),
    ])
      .then(([txn, cats, recurring]) => {
        setTransaction(txn);
        setCategoryName(txn.category_name || "");
        setNotes(txn.notes || "");
        setCategories(cats);
        setTracked(recurring?.rule ?? null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  // Back to wherever the user came from; if there's nowhere to go back to (opened from a
  // link), land on the dashboard instead of doing nothing.
  const goBack = () =>
    router.canGoBack() ? router.back() : router.replace("/" as any);

  const handleSave = async () => {
    setError("");
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
    } catch (err: any) {
      setError(err.message);
      setSaving(false);
      return; // the save failed, so the recurring choice isn't acted on either
    }

    // Only now — after a successful save — does the recurring tick take effect.
    let note = "";
    if (makeRecurring && !tracked) {
      try {
        const res = await fetch(`${API_URL}/recurring/from-transaction`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transaction_id: id,
            interval_count: repeat.count,
            interval_unit: repeat.unit,
          }),
        });
        const rule = await res.json();
        if (!res.ok) throw new Error(formatDetail(rule.detail));
        setTracked({
          interval_count: rule.interval_count,
          interval_unit: rule.interval_unit,
          next_due_date: rule.next_due_date,
        });
        setMakeRecurring(false);
        note = ` · Now tracking ${repeatPhrase(repeat.count, repeat.unit)}`;
      } catch (err: any) {
        // Saved fine; only the recurring part failed. Stay here, where the problem can be
        // seen and the tick is still set to try again — a toast would vanish in seconds.
        setError(`Saved, but couldn't make it recurring: ${err.message}`);
        setSaving(false);
        return;
      }
    }

    setSaving(false);
    showToast(`Saved${note}`);
    goBack();
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

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.recurringBox}>
          {tracked ? (
            // Already covered by a rule: shown ticked and locked, so the box tells the truth.
            <Checkbox
              checked
              disabled
              onChange={() => {}}
              label="Recurring"
              hint={`${repeatLabel(tracked.interval_count, tracked.interval_unit)}${tracked.next_due_date ? ` · next ${dueLabel(tracked.next_due_date)}` : ""}. Manage it in Settings › Recurring Transactions.`}
            />
          ) : (
            <>
              <Checkbox
                checked={makeRecurring}
                onChange={setMakeRecurring}
                label="Make this recurring"
                hint="Takes effect when you tap Save."
              />
              {makeRecurring && (
                <RepeatField value={repeat} onChange={setRepeat} />
              )}
            </>
          )}
        </View>

        <View style={{ marginTop: 16 }}>
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
  recurringBox: { marginTop: 24 },
  error: { color: "red", marginTop: 16, padding: 16 },
});
