import { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { OTHER_COLOR } from "@/constants/chartColors";
import { useWidgetData } from "@/hooks/use-widget-data";
import {
  BreakdownItem,
  otherLabel,
  rankBreakdown,
  summarizeTop,
} from "@/utils/breakdown";
import { formatNumber } from "@/utils/format";
import { WidgetCard } from "./widget-card";

const TOP_COUNT = 3;

interface Props {
  year: number;
  month: number;
  refreshKey: number;
}

// The Cash Flow expense breakdown, cut down to its three biggest categories with the rest
// folded into one "+x other categories" line. It reads the same endpoint as Cash Flow, so
// the two can never disagree.
export function TopExpensesWidget({ year, month, refreshKey }: Props) {
  const router = useRouter();
  const { data, loading, error } = useWidgetData<BreakdownItem[]>(
    `${API_URL}/summary/category-breakdown/${CURRENT_USER_ID}?type=expense&year=${year}&month=${month}`,
    refreshKey,
  );

  const { top, other } = useMemo(
    () => summarizeTop(rankBreakdown(data ?? []), TOP_COUNT),
    [data],
  );

  return (
    <WidgetCard
      title="Top Expenses"
      loading={loading && !data}
      error={error}
      showArrow
      onPress={() => router.push("/cash-flow" as any)}
    >
      {data && top.length === 0 ? (
        <Text style={styles.empty}>No expenses for this month.</Text>
      ) : (
        <>
          {top.map((row, i) => {
            const content = (
              <>
                <View style={[styles.pctPill, { backgroundColor: row.color }]}>
                  <Text style={styles.pctText}>{row.percent}%</Text>
                </View>
                <Text style={styles.name} numberOfLines={1}>
                  {row.name}
                </Text>
                <Text style={styles.amount}>{formatNumber(row.amount)}</Text>
              </>
            );

            // "Others" folds several hidden categories together, so there's no single
            // category to open — same as on Cash Flow, it isn't a link.
            return row.isOthersBucket ? (
              <View
                key={row.categoryId}
                style={[styles.row, i > 0 && styles.rowDivider]}
              >
                {content}
              </View>
            ) : (
              <Pressable
                key={row.categoryId}
                style={[styles.row, i > 0 && styles.rowDivider]}
                onPress={() =>
                  router.push({
                    pathname: "/category-detail",
                    params: {
                      categoryId: row.categoryId,
                      categoryName: row.name,
                      type: "expense",
                      year: String(year),
                      month: String(month),
                    },
                  })
                }
              >
                {content}
              </Pressable>
            );
          })}
        </>
      )}
    </WidgetCard>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 10 },
  rowDivider: { borderTopWidth: 1, borderColor: "#f0f0f0" },
  pctPill: {
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginRight: 10,
  },
  pctText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  name: { flex: 1, fontSize: 14 },
  otherName: { color: "#888" },
  amount: { fontSize: 14, fontWeight: "600", marginRight: 6 },
  arrow: { fontSize: 18, color: "#ccc" },
  empty: { color: "#999", fontSize: 13 },
});
