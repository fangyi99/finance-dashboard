import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Stack, useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { ActionMenu } from "@/components/action-menu";
import { formatDate, formatMoney } from "@/utils/format";
import { takeFlash } from "@/utils/flash";
import {
  dueLabel,
  Frequency,
  repeatLabel,
  ruleTitle,
  seenLabel,
  Unit,
} from "@/utils/recurring";

interface Suggestion {
  pattern: string;
  label: string;
  frequency: Frequency;
  interval_count: number;
  interval_unit: Unit;
  expected_amount: string;
  currency: string;
  amount_tolerance_pct: string;
  amount_varies: boolean;
  occurrences: number;
  last_date: string;
  next_due_date: string;
  category_id: string | null;
  category_name: string | null;
  account_id: string | null;
}

interface Rule {
  id: string;
  description: string | null;
  merchant_pattern?: string | null;
  expected_amount: string | null;
  currency: string;
  interval_count: number;
  interval_unit: Unit;
  amount_varies: boolean;
  is_active: boolean;
  next_due_date: string | null;
  category_name: string | null;
  account_name: string | null;
}

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Something went wrong";
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export default function RecurringScreen() {
  const router = useRouter();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([
        fetch(`${API_URL}/recurring/suggestions/${CURRENT_USER_ID}`).then(
          (res) => res.json(),
        ),
        fetch(`${API_URL}/recurring/${CURRENT_USER_ID}`).then((res) =>
          res.json(),
        ),
      ]);
      setSuggestions(Array.isArray(s) ? s : []);
      setRules(Array.isArray(r) ? r : []);
      setError("");
    } catch {
      setError("Couldn't load recurring transactions");
    } finally {
      setLoaded(true);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      // Shown once: the form page leaves a message here when it closes after adding something.
      setMessage(takeFlash() ?? "");
      load();
    }, [load]),
  );

  // One place for every change, so a failure always shows the same way and the lists
  // always refresh from the server afterwards.
  const run = async (key: string, request: () => Promise<Response>) => {
    setBusy(key);
    setError("");
    try {
      const res = await request();
      const data = await res.json();
      if (!res.ok) throw new Error(formatDetail(data.detail));
      await load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  // Approving and dismissing are the same request; dismissing just stores it inactive,
  // which is how it's remembered and never suggested again.
  const saveSuggestion = (s: Suggestion, isActive: boolean) =>
    run(s.pattern, () =>
      fetch(`${API_URL}/recurring`, {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({
          user_id: CURRENT_USER_ID,
          description: labels[s.pattern] ?? s.label,
          merchant_pattern: s.pattern,
          expected_amount: s.expected_amount,
          amount_tolerance_pct: s.amount_tolerance_pct,
          frequency: s.frequency,
          category_id: s.category_id,
          account_id: s.account_id,
          is_active: isActive,
        }),
      }),
    );

  const setActive = (rule: Rule, isActive: boolean) =>
    run(rule.id, () =>
      fetch(`${API_URL}/recurring/${rule.id}`, {
        method: "PATCH",
        headers: JSON_HEADERS,
        body: JSON.stringify({ is_active: isActive }),
      }),
    );

  const edit = (rule: Rule) =>
    router.push({
      pathname: "/recurring-form",
      params: { id: rule.id },
    } as any);

  const remove = (rule: Rule) =>
    run(rule.id, () =>
      fetch(`${API_URL}/recurring/${rule.id}`, { method: "DELETE" }),
    );

  const tracked = rules.filter((r) => r.is_active);
  const stopped = rules.filter((r) => !r.is_active);

  // Set before the loading check, so the + is there straight away rather than popping in
  // after the lists arrive.
  const headerOptions = {
    title: "Recurring",
    headerRight: () => (
      <Pressable
        onPress={() => router.push("/recurring-form" as any)}
        hitSlop={12}
        accessibilityRole="button"
        accessibilityLabel="Add recurring transaction"
      >
        <Ionicons name="add" size={28} color="#007AFF" />
      </Pressable>
    ),
  };

  if (!loaded) {
    return (
      <>
        <Stack.Screen options={headerOptions} />
        <ActivityIndicator style={{ marginTop: 40 }} />
      </>
    );
  }

  return (
    <>
      <Stack.Screen options={headerOptions} />
      <ScrollView
        style={styles.page}
        contentContainerStyle={{ padding: 16 }}
        keyboardShouldPersistTaps="handled"
      >
        {error ? <Text style={styles.error}>{error}</Text> : null}
        {message ? <Text style={styles.success}>{message}</Text> : null}

        {suggestions.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Suggestions</Text>
            <Text style={styles.sectionHint}>
              Found in your transactions. Add the ones you want to track.
            </Text>
            {suggestions.map((s) => (
              <View key={s.pattern} style={styles.card}>
                <TextInput
                  value={labels[s.pattern] ?? s.label}
                  onChangeText={(text) =>
                    setLabels((current) => ({ ...current, [s.pattern]: text }))
                  }
                  style={styles.labelInput}
                  placeholder="Name"
                />
                <Text
                  style={[
                    styles.amount,
                    {
                      color:
                        Number(s.expected_amount) < 0 ? "#d93025" : "#1a9e4b",
                    },
                  ]}
                >
                  {s.amount_varies ? "~" : ""}
                  {formatMoney(s.expected_amount, s.currency)} ·{" "}
                  {repeatLabel(s.interval_count, s.interval_unit)}
                </Text>
                <Text style={styles.meta}>
                  {seenLabel(s.occurrences)} · last {formatDate(s.last_date)} ·
                  next {dueLabel(s.next_due_date)}
                </Text>
                <View style={styles.buttons}>
                  <Pressable
                    style={styles.primary}
                    disabled={busy === s.pattern}
                    onPress={() => saveSuggestion(s, true)}
                  >
                    <Text style={styles.primaryText}>Add</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondary}
                    disabled={busy === s.pattern}
                    onPress={() => saveSuggestion(s, false)}
                  >
                    <Text style={styles.secondaryText}>Dismiss</Text>
                  </Pressable>
                </View>
              </View>
            ))}
          </>
        )}

        <Text style={styles.sectionTitle}>Your recurring transactions</Text>
        {tracked.length === 0 ? (
          <Text style={styles.empty}>
            {suggestions.length > 0
              ? "Nothing yet — add a suggestion above."
              : "Nothing detected yet. A repeating charge needs at least 3 occurrences to be spotted. You can also mark any transaction as recurring from its details screen."}
          </Text>
        ) : (
          tracked.map((rule) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              onOpen={() => edit(rule)}
              actions={[
                { label: "Edit", onPress: () => edit(rule) },
                {
                  label: "Stop tracking",
                  onPress: () => setActive(rule, false),
                },
                {
                  label: "Delete",
                  destructive: true,
                  onPress: () => remove(rule),
                },
              ]}
            />
          ))
        )}

        {stopped.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Stopped or dismissed</Text>
            <Text style={styles.sectionHint}>
              These won't show as upcoming and won't be suggested again.
            </Text>
            {stopped.map((rule) => (
              <RuleRow
                key={rule.id}
                rule={rule}
                dimmed
                onOpen={() => edit(rule)}
                actions={[
                  { label: "Edit", onPress: () => edit(rule) },
                  { label: "Resume", onPress: () => setActive(rule, true) },
                  {
                    label: "Delete",
                    destructive: true,
                    onPress: () => remove(rule),
                  },
                ]}
              />
            ))}
          </>
        )}
      </ScrollView>
    </>
  );
}

function RuleRow({
  rule,
  actions,
  onOpen,
  dimmed,
}: {
  rule: Rule;
  actions: { label: string; onPress: () => void; destructive?: boolean }[];
  onOpen: () => void;
  dimmed?: boolean;
}) {
  return (
    <View style={[styles.ruleRow, dimmed && { opacity: 0.55 }]}>
      {/* Tapping the row opens it for editing; the ⋯ menu is its own, separate target. */}
      <Pressable
        style={{ flex: 1, marginRight: 8 }}
        onPress={onOpen}
        accessibilityRole="button"
        accessibilityLabel={`Edit ${ruleTitle(rule)}`}
      >
        <Text style={styles.ruleLabel} numberOfLines={1}>
          {ruleTitle(rule)}
        </Text>
        {/* The second line: how often and when on the left, the amount on the right. */}
        <View style={styles.ruleLine}>
          <Text style={styles.ruleMeta} numberOfLines={1}>
            {repeatLabel(rule.interval_count, rule.interval_unit)}
            {rule.next_due_date && !dimmed
              ? ` · next ${dueLabel(rule.next_due_date)}`
              : ""}
          </Text>
          {rule.expected_amount !== null && (
            <Text
              style={[
                styles.ruleAmount,
                {
                  color:
                    Number(rule.expected_amount) < 0 ? "#d93025" : "#1a9e4b",
                },
              ]}
            >
              {rule.amount_varies ? "~" : ""}
              {formatMoney(rule.expected_amount, rule.currency)}
            </Text>
          )}
        </View>
      </Pressable>
      <ActionMenu actions={actions} />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "bold",
    marginTop: 20,
    marginBottom: 4,
  },
  sectionHint: { color: "#999", fontSize: 12, marginBottom: 10 },
  card: {
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
  },
  labelInput: {
    fontSize: 16,
    fontWeight: "600",
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderColor: "#eee",
    marginBottom: 8,
  },
  amount: { fontSize: 15, fontWeight: "600" },
  meta: { color: "#999", fontSize: 12, marginTop: 3 },
  buttons: { flexDirection: "row", gap: 10, marginTop: 12 },
  primary: {
    backgroundColor: "#007AFF",
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 22,
  },
  primaryText: { color: "#fff", fontWeight: "600" },
  secondary: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 18,
  },
  secondaryText: { color: "#555" },
  ruleLine: { flexDirection: "row", alignItems: "center", marginTop: 3 },
  ruleMeta: { flex: 1, color: "#999", fontSize: 12, marginRight: 8 },
  ruleRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  ruleLabel: { fontSize: 15 },
  ruleAmount: { fontSize: 14, fontWeight: "600" },
  empty: { color: "#999", fontSize: 13, marginTop: 4 },
  error: { color: "red", marginBottom: 8 },
  success: { color: "green", marginBottom: 12 },
});
