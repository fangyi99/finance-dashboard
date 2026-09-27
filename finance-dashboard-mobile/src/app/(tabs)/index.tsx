import { useEffect, useState } from "react";
import { View, Text, FlatList, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "react-native";
import { API_URL, CURRENT_USER_ID } from "@/constants/config";

export default function DashboardScreen() {
  const router = useRouter();
  const [widgetPrefs, setWidgetPrefs] = useState<string[]>([]);
  const [monthlySummary, setMonthlySummary] = useState<{
    income: number;
    expenses: number;
    savings: number;
  } | null>(null);
  const [topExpenses, setTopExpenses] = useState<Transaction[]>([]);
  const [transactions, setTransactions] = useState([]);

  useEffect(() => {
    fetch(`${API_URL}/widget-preferences/${CURRENT_USER_ID}`)
      .then((res) => res.json())
      .then((prefs) => {
        setWidgetPrefs(
          Array.isArray(prefs)
            ? prefs
                .filter((p: any) => p.is_enabled)
                .map((p: any) => p.widget_key)
            : [],
        );
      })
      .catch((err) => console.error(err));
  }, []);

  useEffect(() => {
    if (widgetPrefs.includes("monthly_summary")) {
      fetch(`${API_URL}/summary/monthly/${CURRENT_USER_ID}`)
        .then((res) => res.json())
        .then(setMonthlySummary)
        .catch((err) => console.error(err));
    }
    if (widgetPrefs.includes("top_expenses")) {
      fetch(`${API_URL}/transactions/top-expenses/${CURRENT_USER_ID}?limit=5`)
        .then((res) => res.json())
        .then(setTopExpenses)
        .catch((err) => console.error(err));
    }
  }, [widgetPrefs]);

  useEffect(() => {
    fetch(`${API_URL}/transactions`)
      .then((res) => res.json())
      .then(setTransactions)
      .catch((err) => console.error(err));
  }, []);

  return (
    <View style={{ padding: 20 }}>
      {/* <Button
        title="Add Transaction"
        onPress={() => {
          router.push("/add-transaction" as any);
        }}
      /> */}
      <Button
        title="Import CSV"
        onPress={() => router.push("/import-csv" as any)}
      />
      {widgetPrefs.includes("balance_summary") && (
        <View style={styles.widgetCard}>
          <Text style={styles.widgetTitle}>Balance Summary</Text>
          <Text style={{ color: "#999" }}>Coming soon</Text>
        </View>
      )}
      {widgetPrefs.includes("monthly_summary") && (
        <View style={styles.widgetCard}>
          <Text style={styles.widgetTitle}>Monthly Summary</Text>
          <Text style={{ color: "#999" }}>Coming soon</Text>
        </View>
      )}
      {widgetPrefs.includes("top_expenses") && (
        <View style={styles.widgetCard}>
          <Text style={styles.widgetTitle}>Top Expenses</Text>
          <Text style={{ color: "#999" }}>Coming soon</Text>
        </View>
      )}

      {widgetPrefs.includes("upcoming_transactions") && (
        <View style={styles.widgetCard}>
          <Text style={styles.widgetTitle}>Upcoming Transactions</Text>
          <Text style={{ color: "#999" }}>Coming soon</Text>
        </View>
      )}
      {widgetPrefs.includes("recent_transactions") && (
        <View style={styles.widgetCard}>
          <Text style={styles.widgetTitle}>Recent Transactions</Text>
          <FlatList
            data={transactions}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => (
              <View
                style={{
                  paddingVertical: 8,
                  borderBottomWidth: 1,
                  borderColor: "#eee",
                }}
              >
                <Text>{item.description_raw}</Text>
                <Text style={{ color: item.amount < 0 ? "red" : "green" }}>
                  {item.amount} {item.currency}
                </Text>
              </View>
            )}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  widgetCard: {
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 10,
    padding: 16,
    marginBottom: 16,
  },
  widgetTitle: {
    fontSize: 16,
    fontWeight: "bold",
    marginBottom: 8,
  },
});
