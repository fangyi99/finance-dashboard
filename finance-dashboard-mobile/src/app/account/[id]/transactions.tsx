import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  SectionList,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams } from "expo-router";

import { API_URL } from "@/constants/config";
import { formatMoney } from "@/utils/format";

interface Transaction {
  id: string;
  description_raw: string;
  amount: string;
  currency: string;
  transaction_date: string; // "YYYY-MM-DD"
}

interface MonthOption {
  key: string; // "2026-9"
  label: string; // "Sep 26"
  year: number;
  month: number; // 1-12
}

// Last 3 months plus the current month, oldest to newest, current month last.
function buildMonthOptions(): MonthOption[] {
  const now = new Date();
  const options: MonthOption[] = [];
  for (let offset = -3; offset <= 0; offset++) {
    const d = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    options.push({
      key: `${d.getFullYear()}-${d.getMonth() + 1}`,
      label: d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" }),
      year: d.getFullYear(),
      month: d.getMonth() + 1,
    });
  }
  return options;
}

function groupByDate(transactions: Transaction[]) {
  const sections: { title: string; data: Transaction[] }[] = [];
  let current: { title: string; data: Transaction[] } | null = null;
  for (const tx of transactions) {
    if (!current || current.title !== tx.transaction_date) {
      current = { title: tx.transaction_date, data: [] };
      sections.push(current);
    }
    current.data.push(tx);
  }
  return sections;
}

function formatSectionHeader(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export default function AccountTransactionsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const monthOptions = useMemo(buildMonthOptions, []);
  const currentMonthKey = monthOptions[monthOptions.length - 1].key; // last entry is always "now"
  const [selectedKey, setSelectedKey] = useState(currentMonthKey);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const selected = monthOptions.find((m) => m.key === selectedKey)!;

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError("");
    fetch(
      `${API_URL}/accounts/${id}/transactions?year=${selected.year}&month=${selected.month}&limit=200`,
    )
      .then((res) => {
        if (!res.ok) throw new Error("Couldn't load transactions");
        return res.json();
      })
      .then(setTransactions)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id, selectedKey]);

  const sections = groupByDate(transactions);

  return (
    <>
      <Stack.Screen options={{ title: "All Transactions" }} />
      <View style={styles.page}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.pillScroll}
          contentContainerStyle={styles.pillRow}
        >
          {monthOptions.map((m) => {
            const active = m.key === selectedKey;
            return (
              <Pressable
                key={m.key}
                onPress={() => setSelectedKey(m.key)}
                style={[styles.pill, active && styles.pillActive]}
              >
                <Text style={active ? styles.pillTextActive : styles.pillText}>
                  {m.label}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {loading ? (
          <ActivityIndicator style={{ marginTop: 32 }} />
        ) : sections.length === 0 ? (
          <Text style={styles.empty}>No transactions.</Text>
        ) : (
          <SectionList
            style={{ marginTop: 8 }}
            sections={sections}
            keyExtractor={(item) => item.id}
            renderSectionHeader={({ section }) => (
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionHeaderText}>
                  {formatSectionHeader(section.title)}
                </Text>
              </View>
            )}
            renderItem={({ item }) => (
              <View style={styles.txRow}>
                <Text style={{ flex: 1, marginRight: 8 }} numberOfLines={1}>
                  {item.description_raw}
                </Text>
                <Text
                  style={{ color: Number(item.amount) < 0 ? "red" : "green" }}
                >
                  {formatMoney(item.amount, item.currency)}
                </Text>
              </View>
            )}
            stickySectionHeadersEnabled
          />
        )}
        {/*
          No pending/cancelled filter: CSV and PDF statements only ever contain transactions
          that have already cleared, so there is no "pending" or "cancelled" state in the data
          to filter by yet. That becomes possible once Stripe (which does report pending
          charges) is wired in — a `status` column would need to be added to `transactions` then.
        */}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: 16 },
  pillScroll: { flexGrow: 0, marginBottom: 8 },
  pillRow: { gap: 8 },
  pill: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 20,
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  pillActive: { borderColor: "#007AFF", backgroundColor: "#007AFF" },
  pillText: { color: "#333" },
  pillTextActive: { color: "#fff", fontWeight: "600" },
  sectionHeader: {
    backgroundColor: "#f2f2f2",
    paddingVertical: 6,
    paddingHorizontal: 8,
    marginTop: 8,
    borderRadius: 6,
  },
  sectionHeaderText: { color: "#666", fontSize: 12, fontWeight: "600" },
  txRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  empty: { color: "#999", textAlign: "center", marginTop: 32 },
  error: { color: "red", marginTop: 16 },
});
