import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { useWidgetData } from "@/hooks/use-widget-data";
import {
  Budget,
  BUDGET_COLORS,
  budgetProgress,
  budgetStatusParts,
  otherBudgetsLabel,
  remainingWords,
  summarizeBudgets,
  WIDGET_BUDGET_COUNT,
} from "@/utils/budget";
import { WidgetCard } from "./widget-card";

interface Props {
  year: number;
  month: number;
  refreshKey: number;
}

// Your budgets at a glance: the three closest to their limit, with the rest folded into
// "+N other budgets". Not a total — budgets overlap (Food and Groceries count the same
// groceries), and a sum would hide one overspent budget behind comfortable ones. Instead a
// line under the title counts what needs attention — and is left out when nothing does. The
// bars carry no percentage (the Budget tab has those); the amount left says the rest. The
// whole card opens the Budget tab.
// It reads the same endpoint as the Budget tab, so the two can never disagree.
export function BudgetsWidget({ year, month, refreshKey }: Props) {
  const router = useRouter();
  const { data, loading, error } = useWidgetData<Budget[]>(
    `${API_URL}/budgets/${CURRENT_USER_ID}?year=${year}&month=${month}`,
    refreshKey,
  );

  const summary = useMemo(
    () => summarizeBudgets(data ?? [], WIDGET_BUDGET_COUNT),
    [data],
  );
  const statusParts = budgetStatusParts(summary.over, summary.near);

  return (
    <WidgetCard
      title="Budgets"
      loading={loading && !data}
      error={error}
      onPress={() => router.push("/budget" as any)}
      showArrow
    >
      {data && data.length === 0 ? (
        <Text style={styles.empty}>No budgets yet. Tap to set one.</Text>
      ) : (
        <>
          {statusParts.length > 0 && (
            <Text style={styles.status}>
              {statusParts.map((part, i) => (
                <Text key={part.text}>
                  {i > 0 && <Text style={styles.separator}> · </Text>}
                  <Text style={{ color: BUDGET_COLORS[part.tone] }}>
                    {part.text}
                  </Text>
                </Text>
              ))}
            </Text>
          )}

          {summary.top.map((budget, i) => {
            const { fill, label, status } = budgetProgress(
              budget.spent,
              budget.amount,
            );
            const remaining = remainingWords(budget.remaining);
            return (
              <View
                key={budget.id}
                style={[styles.row, i > 0 && styles.rowDivider]}
              >
                <View style={styles.line}>
                  <Text style={styles.name} numberOfLines={1}>
                    {budget.name}
                  </Text>
                  <Text
                    style={[
                      styles.remaining,
                      remaining.over && styles.remainingOver,
                    ]}
                  >
                    {remaining.text}
                  </Text>
                </View>
                <View
                  style={styles.barRow}
                  accessibilityRole="progressbar"
                  accessibilityLabel={`${budget.name}: ${label}% of the budget used`}
                  accessibilityValue={{
                    min: 0,
                    max: 100,
                    now: Math.round(fill),
                  }}
                >
                  <View style={styles.track}>
                    <View
                      style={[
                        styles.fill,
                        {
                          width: `${fill}%`,
                          backgroundColor: BUDGET_COLORS[status],
                        },
                      ]}
                    />
                  </View>
                </View>
              </View>
            );
          })}

          {summary.otherCount > 0 && (
            <Text style={[styles.other, styles.rowDivider]}>
              {otherBudgetsLabel(summary.otherCount)}
            </Text>
          )}
        </>
      )}
    </WidgetCard>
  );
}

const styles = StyleSheet.create({
  status: { fontSize: 12, marginBottom: 4 },
  separator: { color: "#999" },
  row: { paddingVertical: 8 },
  rowDivider: { borderTopWidth: 1, borderColor: "#f0f0f0" },
  line: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  name: { flex: 1, fontSize: 14, marginRight: 8 },
  remaining: { fontSize: 14, fontWeight: "600" },
  remainingOver: { color: "#d93025" },
  barRow: { marginTop: 6 },
  track: {
    height: 8,
    borderRadius: 4,
    backgroundColor: "#eee",
    overflow: "hidden",
  },
  fill: { height: "100%" },
  other: { color: "#888", fontSize: 13, paddingTop: 10 },
  empty: { color: "#999", fontSize: 13 },
});
