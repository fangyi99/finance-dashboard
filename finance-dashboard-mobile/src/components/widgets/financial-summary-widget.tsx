import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { useWidgetData } from "@/hooks/use-widget-data";
import { formatNumber } from "@/utils/format";
import { WidgetCard } from "./widget-card";

interface SummaryResponse {
  income: string;
  expenses: string;
  savings: string;
  month: string;
}

interface Props {
  year: number;
  month: number;
  refreshKey: number;
}

export function FinancialSummaryWidget({ year, month, refreshKey }: Props) {
  const router = useRouter();
  const { data, loading, error } = useWidgetData<SummaryResponse>(
    `${API_URL}/summary/monthly/${CURRENT_USER_ID}?year=${year}&month=${month}`,
    refreshKey,
  );

  const savings = data ? Number(data.savings) : 0;
  const isEmpty =
    !!data && Number(data.income) === 0 && Number(data.expenses) === 0;

  return (
    <WidgetCard
      title="Financial Summary"
      loading={loading && !data}
      error={error}
      showArrow
      onPress={() => router.push("/cash-flow" as any)}
    >
      {isEmpty ? (
        <Text style={styles.empty}>Nothing recorded for this month yet.</Text>
      ) : (
        <View style={styles.row}>
          <Stat
            label="Income"
            value={data ? formatNumber(data.income) : "—"}
            color="#1a9e4b"
          />
          <Stat
            label="Expenses"
            value={data ? formatNumber(data.expenses) : "—"}
            color="#d93025"
          />
          <Stat
            label="Savings"
            value={data ? formatNumber(data.savings) : "—"}
            color={savings < 0 ? "#d93025" : "#007AFF"}
          />
        </View>
      )}
    </WidgetCard>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text
        style={[styles.statValue, { color }]}
        numberOfLines={1}
        adjustsFontSizeToFit
      >
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: 8 },
  stat: { flex: 1 },
  statLabel: { fontSize: 12, color: "#999", marginBottom: 4 },
  statValue: { fontSize: 18, fontWeight: "700" },
  empty: { color: "#999", fontSize: 13 },
});
