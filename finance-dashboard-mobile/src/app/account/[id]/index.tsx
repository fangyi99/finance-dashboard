import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";

import { API_URL } from "@/constants/config";
import { formatDate, formatMoney } from "@/utils/format";

interface Account {
  id: string;
  source: string;
  display_name: string | null;
  institution_name: string | null;
  currency: string;
  balance: string | null;
  balance_as_of: string | null;
  last_synced_at: string | null;
}

interface Transaction {
  id: string;
  description_raw: string;
  amount: string;
  currency: string;
  transaction_date: string;
}

export default function AccountDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetch(`${API_URL}/accounts/by-id/${id}`),
      fetch(`${API_URL}/accounts/${id}/transactions?limit=5`),
    ])
      .then(async ([accRes, txRes]) => {
        if (!accRes.ok || !txRes.ok)
          throw new Error("Couldn't load this account");
        setAccount(await accRes.json());
        setTransactions(await txRes.json());
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (!account)
    return <Text style={styles.error}>{error || "Account not found"}</Text>;

  return (
    <>
      <Stack.Screen
        options={{
          title: account.display_name || account.institution_name || "Account",
          headerRight: () => (
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/account/[id]/edit",
                  params: { id: account.id },
                })
              }
              hitSlop={8}
            >
              <Text style={styles.edit}>Edit</Text>
            </Pressable>
          ),
        }}
      />
      <View style={styles.page}>
        <View style={styles.card}>
          <Text style={styles.balance}>
            {formatMoney(account.balance, account.currency)}
          </Text>
          <Text style={styles.meta}>
            {account.balance_as_of
              ? `Balance as of ${formatDate(account.balance_as_of)}`
              : "No balance yet"}
          </Text>
          <Text style={styles.meta}>
            {[account.institution_name, account.currency]
              .filter(Boolean)
              .join(" · ")}
          </Text>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Transactions</Text>
          <Pressable
            onPress={() =>
              router.push({
                pathname: "/account/[id]/transactions",
                params: { id: account.id },
              })
            }
          >
            <Text style={styles.viewAll}>View all</Text>
          </Pressable>
        </View>

        {transactions.length === 0 ? (
          <Text style={styles.empty}>No transactions yet.</Text>
        ) : (
          transactions.map((item) => (
            <View key={item.id} style={styles.txRow}>
              <View style={{ flex: 1, marginRight: 8 }}>
                <Text numberOfLines={1}>{item.description_raw}</Text>
                <Text style={styles.meta}>
                  {formatDate(item.transaction_date)}
                </Text>
              </View>
              <Text
                style={{ color: Number(item.amount) < 0 ? "red" : "green" }}
              >
                {formatMoney(item.amount, item.currency)}
              </Text>
            </View>
          ))
        )}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: 16 },
  card: { borderWidth: 1, borderColor: "#eee", borderRadius: 10, padding: 16 },
  balance: { fontSize: 26, fontWeight: "600" },
  edit: { color: "#007AFF", fontWeight: "600", marginRight: 4 },
  meta: { color: "#999", fontSize: 12, marginTop: 4 },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 24,
    marginBottom: 8,
  },
  sectionTitle: { fontSize: 16, fontWeight: "bold" },
  viewAll: { color: "#007AFF" },
  txRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  empty: { color: "#999", textAlign: "center", marginTop: 16 },
  error: { color: "red", marginTop: 8, padding: 16 },
});
