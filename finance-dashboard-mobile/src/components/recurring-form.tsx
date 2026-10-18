import { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { Dropdown } from "@/components/dropdown";
import { RadioRow } from "@/components/radio-row";
import { RepeatButton } from "@/components/repeat-button";
import { RepeatField } from "@/components/repeat-field";
import {
  accountChoices,
  buildEditPayload,
  buildManualPayload,
  categoryChoices,
  DIRECTION_OPTIONS,
  dueLabel,
  EditableRule,
  formatDateInput,
  formFromRule,
  Kind,
  KIND_OPTIONS,
  repeatPhrase,
  RecurringFormState,
  sanitizeAmount,
  todayInput,
  validateForm,
} from "@/utils/recurring";

const NO_CATEGORY = "No category";

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Something went wrong";
}

interface Props {
  // Adding: called with a message to confirm what was added.
  onCreated?: (message: string) => void;
  // Editing: the rule being edited. The form starts filled in from it, and saving updates it.
  editing?: EditableRule;
  onSaved?: () => void;
}

export function RecurringForm({ onCreated, editing, onSaved }: Props) {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [form, setForm] = useState<RecurringFormState>(() =>
    editing
      ? formFromRule(editing)
      : {
          kind: "expense",
          direction: "out",
          date: todayInput(),
          intervalCount: 1,
          intervalUnit: "month",
          accountId: null,
          categoryId: null,
          description: "",
          amount: "",
        },
  );
  // A rule that follows real transactions takes its dates, and which way its money goes,
  // from them — so there's no date to type and no type to change.
  const followsTransactions = !!editing?.follows_transactions;
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (patch: Partial<RecurringFormState>) =>
    setForm((current) => ({ ...current, ...patch }));

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/accounts/${CURRENT_USER_ID}`).then((r) => r.json()),
      fetch(`${API_URL}/categories/${CURRENT_USER_ID}`).then((r) => r.json()),
    ])
      .then(([accountList, categoryList]) => {
        const list = Array.isArray(accountList) ? accountList : [];
        setAccounts(list);
        setCategories(Array.isArray(categoryList) ? categoryList : []);
        // Most people have one or two accounts, so start on the first rather than empty.
        if (list.length > 0)
          setForm((current) =>
            current.accountId ? current : { ...current, accountId: list[0].id },
          );
      })
      .catch(() => setError("Couldn't load your accounts and categories"));
  }, []);

  const accountOptions = useMemo(() => accountChoices(accounts), [accounts]);
  const categoryOptions = useMemo(
    () => categoryChoices(categories, form.kind),
    [categories, form.kind],
  );

  // The category list follows the type, so changing the type drops a category that no
  // longer belongs (an income category on an expense, say).
  const changeKind = (kind: Kind) => {
    const stillValid = categoryChoices(categories, kind).some(
      (c) => c.id === form.categoryId,
    );
    set({ kind, categoryId: stillValid ? form.categoryId : null });
  };

  const submit = async () => {
    const problem = validateForm(
      form,
      accounts.length > 0,
      !followsTransactions,
    );
    if (problem) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (editing) {
        const res = await fetch(`${API_URL}/recurring/${editing.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildEditPayload(form, editing)),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(formatDetail(data.detail));
        onSaved?.();
        return;
      }
      const res = await fetch(`${API_URL}/recurring/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildManualPayload(CURRENT_USER_ID, form)),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(formatDetail(data.detail));
      onCreated?.(
        `Added "${data.description}" — next ${data.next_due_date ? dueLabel(data.next_due_date) : "date unknown"}`,
      );
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const selectedAccount =
    accountOptions.find((a) => a.id === form.accountId)?.label ?? "";
  const selectedCategory =
    categoryOptions.find((c) => c.id === form.categoryId)?.label ?? NO_CATEGORY;

  return (
    <View>
      {!followsTransactions && (
        <>
          <RadioRow
            options={KIND_OPTIONS}
            value={form.kind}
            onChange={changeKind}
          />

          {/* A transfer can go either way, and which way decides whether it counts as an
              expense or as income — so it has to ask. */}
          {form.kind === "transfer" && (
            <View style={{ marginTop: 10 }}>
              <RadioRow
                options={DIRECTION_OPTIONS}
                value={form.direction}
                onChange={(direction) => set({ direction })}
              />
            </View>
          )}
        </>
      )}

      {followsTransactions ? (
        <>
          <RepeatField
            value={{ count: form.intervalCount, unit: form.intervalUnit }}
            onChange={(repeat) =>
              set({ intervalCount: repeat.count, intervalUnit: repeat.unit })
            }
          />
          <Text style={styles.hint}>
            Its dates follow your real transactions, so there's no date to set.
          </Text>
        </>
      ) : (
        <>
          <Text style={styles.label}>{editing ? "Next date" : "Date"}</Text>
          <View style={styles.dateRow}>
            <TextInput
              value={form.date}
              onChangeText={(text) => set({ date: formatDateInput(text) })}
              placeholder="DD/MM/YYYY"
              keyboardType="number-pad"
              maxLength={10}
              style={[styles.input, { flex: 1 }]}
            />
            <RepeatButton
              value={{ count: form.intervalCount, unit: form.intervalUnit }}
              onChange={(repeat) =>
                set({ intervalCount: repeat.count, intervalUnit: repeat.unit })
              }
            />
          </View>
          <Text style={styles.hint}>
            Repeats {repeatPhrase(form.intervalCount, form.intervalUnit)} from
            this date.
          </Text>
        </>
      )}

      <Text style={styles.label}>Amount</Text>
      <TextInput
        value={form.amount}
        onChangeText={(text) => set({ amount: sanitizeAmount(text) })}
        placeholder="0.00"
        keyboardType="decimal-pad"
        style={styles.input}
      />

      <Dropdown
        label="Account"
        value={selectedAccount}
        options={accountOptions.map((a) => a.label)}
        onChange={(label) =>
          set({
            accountId:
              accountOptions.find((a) => a.label === label)?.id ?? null,
          })
        }
        placeholder={accounts.length === 0 ? "No accounts yet" : "Select..."}
      />

      <Dropdown
        label="Category (optional)"
        value={selectedCategory}
        options={[NO_CATEGORY, ...categoryOptions.map((c) => c.label)]}
        onChange={(label) =>
          set({
            categoryId:
              categoryOptions.find((c) => c.label === label)?.id ?? null,
          })
        }
      />

      <Text style={styles.label}>Description</Text>
      <TextInput
        value={form.description}
        onChangeText={(description) => set({ description })}
        placeholder="e.g. Rent, Gym, Piano lessons"
        style={styles.input}
      />

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Pressable style={styles.primary} disabled={saving} onPress={submit}>
        <Text style={styles.primaryText}>
          {editing
            ? saving
              ? "Saving..."
              : "Save"
            : saving
              ? "Adding..."
              : "Add"}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  dateRow: { flexDirection: "row", gap: 10, alignItems: "center" },
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
