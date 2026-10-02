import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { PieChart, PieSlice } from "@/components/PieChart";

type BreakdownType = "expense" | "income";

interface BreakdownItem {
  category_id: string;
  category_name: string;
  total: string;
}

const PALETTE = [
  "#007AFF",
  "#FF9500",
  "#34C759",
  "#FF3B30",
  "#AF52DE",
  "#5AC8FA",
  "#FFCC00",
  "#FF2D55",
  "#5856D6",
  "#8E8E93",
];

function monthLabel(offset: number) {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() + offset);
  return {
    label: d.toLocaleDateString("en-GB", { month: "long", year: "numeric" }),
    year: d.getFullYear(),
    month: d.getMonth() + 1,
  };
}

export default function CashFlowScreen() {
  const router = useRouter();
  const [type, setType] = useState<BreakdownType>("expense");
  const monthOptions = useMemo(() => [monthLabel(-1), monthLabel(0)], []);
  const [selectedIndex, setSelectedIndex] = useState(1);
  const [items, setItems] = useState<BreakdownItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const selected = monthOptions[selectedIndex];

  useEffect(() => {
    setLoading(true);
    setError("");
    fetch(
      `${API_URL}/summary/category-breakdown/${CURRENT_USER_ID}?type=${type}&year=${selected.year}&month=${selected.month}`,
    )
      .then((res) => {
        if (!res.ok) throw new Error("Couldn't load the breakdown");
        return res.json();
      })
      .then(setItems)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [type, selectedIndex]);

  const slices: PieSlice[] = items
    .map((item, i) => ({
      label: item.category_name,
      value: Number(item.total),
      color: PALETTE[i % PALETTE.length],
    }))
    .sort((a, b) => b.value - a.value);

  const total = slices.reduce((sum, s) => sum + s.value, 0);

  // Matches the slice order/colors for the rows below the chart.
  const rows = items
    .map((item, i) => ({ ...item, color: PALETTE[i % PALETTE.length] }))
    .sort((a, b) => Number(b.total) - Number(a.total));

  return (
    <ScrollView
      style={styles.page}
      contentContainerStyle={{ padding: 16, paddingTop: 20 }}
    >
      <View style={styles.typeToggle}>
        {(["expense", "income"] as BreakdownType[]).map((t) => (
          <Pressable
            key={t}
            onPress={() => setType(t)}
            style={[styles.typeButton, type === t && styles.typeButtonActive]}
          >
            <Text style={type === t ? styles.typeTextActive : styles.typeText}>
              {t === "expense" ? "Expenses" : "Income"}
            </Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.monthRow}>
        {monthOptions.map((m, i) => (
          <Pressable
            key={m.label}
            onPress={() => setSelectedIndex(i)}
            style={[
              styles.monthPill,
              selectedIndex === i && styles.monthPillActive,
            ]}
          >
            <Text
              style={
                selectedIndex === i ? styles.monthTextActive : styles.monthText
              }
            >
              {m.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {loading && <ActivityIndicator style={{ marginTop: 32 }} />}
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!loading && !error && (
        <>
          <View style={{ marginTop: 24, alignItems: "center" }}>
            <PieChart data={slices} size={220} />
          </View>

          <View style={{ marginTop: 24 }}>
            {rows.map((row) => {
              const pct =
                total > 0
                  ? ((Number(row.total) / total) * 100).toFixed(0)
                  : "0";
              // "Others" bundles several hidden categories together — there's no single
              // category_id behind it, so it has nothing sensible to link through to.
              const isOthers = row.category_name === "Others";

              return (
                <Pressable
                  key={row.category_id}
                  disabled={isOthers}
                  onPress={() =>
                    router.push({
                      pathname: "/category-detail",
                      params: {
                        categoryId: row.category_id,
                        categoryName: row.category_name,
                        type,
                        year: String(selected.year),
                        month: String(selected.month),
                      },
                    })
                  }
                  style={styles.row}
                >
                  <View
                    style={[styles.pctPill, { backgroundColor: row.color }]}
                  >
                    <Text style={styles.pctText}>{pct}%</Text>
                  </View>
                  <Text style={styles.categoryName} numberOfLines={1}>
                    {row.category_name}
                  </Text>
                  <Text style={styles.amount}>
                    {Number(row.total).toFixed(2)}
                  </Text>
                  {!isOthers && <Text style={styles.arrow}>›</Text>}
                </Pressable>
              );
            })}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  typeToggle: {
    flexDirection: "row",
    borderRadius: 8,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#ddd",
  },
  typeButton: { flex: 1, paddingVertical: 10, alignItems: "center" },
  typeButtonActive: { backgroundColor: "#007AFF" },
  typeText: { color: "#333" },
  typeTextActive: { color: "#fff", fontWeight: "600" },
  monthRow: { flexDirection: "row", gap: 8, marginTop: 16 },
  monthPill: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 20,
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  monthPillActive: { borderColor: "#007AFF", backgroundColor: "#EAF3FF" },
  monthText: { color: "#333" },
  monthTextActive: { color: "#007AFF", fontWeight: "600" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  pctPill: {
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginRight: 10,
  },
  pctText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  categoryName: { flex: 1, fontSize: 14 },
  amount: { fontSize: 14, fontWeight: "600", marginRight: 6 },
  arrow: { fontSize: 18, color: "#ccc" },
  error: { color: "red", marginTop: 20, textAlign: "center" },
});
