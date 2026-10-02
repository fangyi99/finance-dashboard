import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  SectionList,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { formatMoney } from "@/utils/format";

// A basic v1 of the filtered transactions list, built to satisfy the Cash Flow ->
// category drill-down flow now. This is expected to be folded into (or replaced by)
// a proper all-transactions screen later, per the plan to update that from Accounts.

interface Transaction {
  id: string;
  description_raw: string;
  amount: string;
  currency: string;
  transaction_date: string;
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

export default function TransactionsByCategoryScreen() {
  const { categoryId, categoryName, type, year, month } = useLocalSearchParams<{
    categoryId: string;
    categoryName: string;
    type: string;
    year: string;
    month: string;
  }>();
  const router = useRouter();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(
      `${API_URL}/transactions/${CURRENT_USER_ID}?category_id=${categoryId}&type=${type}&year=${year}&month=${month}&limit=200`,
    )
      .then((res) => {
        if (!res.ok) throw new Error("Couldn't load transactions");
        return res.json();
      })
      .then(setTransactions)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [categoryId, type, year, month]);

  const sections = groupByDate(transactions);

  return (
    <>
      <Stack.Screen options={{ title: categoryName || "Transactions" }} />
      <View style={styles.page}>
        {loading && <ActivityIndicator style={{ marginTop: 32 }} />}
        {error ? <Text style={styles.error}>{error}</Text> : null}

        {!loading && !error && sections.length === 0 && (
          <Text style={styles.empty}>
            No transactions in this category for this month.
          </Text>
        )}

        {!loading && !error && sections.length > 0 && (
          <SectionList
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
              <Pressable
                style={styles.txRow}
                onPress={() =>
                  router.push({
                    pathname: "/transaction/[id]",
                    params: { id: item.id },
                  })
                }
              >
                <Text style={{ flex: 1, marginRight: 8 }} numberOfLines={1}>
                  {item.description_raw}
                </Text>
                <Text
                  style={{ color: Number(item.amount) < 0 ? "red" : "green" }}
                >
                  {formatMoney(item.amount, item.currency)}
                </Text>
              </Pressable>
            )}
          />
        )}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: 16 },
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
  error: { color: "red", marginTop: 20, textAlign: "center" },
});
