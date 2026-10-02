import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { formatDate, formatMoney } from "@/utils/format";

interface Subcategory {
  category_id: string;
  category_name: string;
  total: number;
}

interface RecentTransaction {
  id: string;
  description_raw: string;
  amount: string;
  currency: string;
  transaction_date: string;
}

interface CategoryDetailResponse {
  category_id: string;
  category_name: string;
  total: number;
  subcategories: Subcategory[];
  recent_transactions: RecentTransaction[];
}

export default function CategoryDetailScreen() {
  const { categoryId, categoryName, type, year, month } = useLocalSearchParams<{
    categoryId: string;
    categoryName: string;
    type: string;
    year: string;
    month: string;
  }>();
  const router = useRouter();
  const [data, setData] = useState<CategoryDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(
      `${API_URL}/summary/category-detail/${CURRENT_USER_ID}?category_id=${categoryId}&type=${type}&year=${year}&month=${month}`,
    )
      .then((res) => {
        if (!res.ok) throw new Error("Couldn't load this category");
        return res.json();
      })
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [categoryId, year, month]);

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (!data) return <Text style={styles.error}>{error || "Not found"}</Text>;

  return (
    <>
      <Stack.Screen options={{ title: categoryName || data.category_name }} />
      <ScrollView style={styles.page} contentContainerStyle={{ padding: 16 }}>
        <View style={styles.totalCard}>
          <Text style={styles.totalLabel}>Total</Text>
          <Text style={styles.totalAmount}>
            {Number(data.total).toFixed(2)}
          </Text>
        </View>

        {data.subcategories.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Subcategories</Text>
            {data.subcategories.map((sub) => (
              <Pressable
                key={sub.category_id}
                style={styles.row}
                onPress={() =>
                  router.push({
                    pathname: "/transactions-by-category",
                    params: {
                      categoryId: sub.category_id,
                      categoryName: sub.category_name,
                      type,
                      year,
                      month,
                    },
                  })
                }
              >
                <Text style={styles.rowLabel} numberOfLines={1}>
                  {sub.category_name}
                </Text>
                <Text style={styles.rowAmount}>
                  {Number(sub.total).toFixed(2)}
                </Text>
                <Text style={styles.arrow}>›</Text>
              </Pressable>
            ))}
          </>
        )}

        <Text style={styles.sectionTitle}>Recent Transactions</Text>
        {data.recent_transactions.length === 0 ? (
          <Text style={styles.empty}>No transactions this month.</Text>
        ) : (
          data.recent_transactions.map((tx) => (
            <Pressable
              key={tx.id}
              style={styles.row}
              onPress={() =>
                router.push({
                  pathname: "/transaction/[id]",
                  params: { id: tx.id },
                })
              }
            >
              <View style={{ flex: 1, marginRight: 8 }}>
                <Text numberOfLines={1}>{tx.description_raw}</Text>
                <Text style={styles.rowDate}>
                  {formatDate(tx.transaction_date)}
                </Text>
              </View>
              <Text style={{ color: Number(tx.amount) < 0 ? "red" : "green" }}>
                {formatMoney(tx.amount, tx.currency)}
              </Text>
            </Pressable>
          ))
        )}
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  totalCard: {
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
  },
  totalLabel: { color: "#999", fontSize: 12 },
  totalAmount: { fontSize: 28, fontWeight: "700", marginTop: 4 },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "bold",
    marginTop: 24,
    marginBottom: 8,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  rowLabel: { flex: 1, fontSize: 14 },
  rowAmount: { fontSize: 14, fontWeight: "600", marginRight: 6 },
  rowDate: { color: "#999", fontSize: 12, marginTop: 2 },
  arrow: { fontSize: 18, color: "#ccc" },
  empty: { color: "#999", textAlign: "center", marginTop: 16 },
  error: { color: "red", marginTop: 20, textAlign: "center", padding: 16 },
});
