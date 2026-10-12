import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { useWidgetData } from "@/hooks/use-widget-data";
import { formatMoney } from "@/utils/format";
import { dueLabel, repeatLabel, ruleTitle, Unit } from "@/utils/recurring";
import { WidgetCard } from "./widget-card";

const WINDOW_DAYS = 30;
const MAX_ROWS = 4;

interface UpcomingItem {
  id: string;
  description: string | null;
  merchant_pattern?: string | null;
  category_name?: string | null;
  expected_amount: string;
  currency: string;
  interval_count: number;
  interval_unit: Unit;
  amount_varies: boolean;
  next_due_date: string;
}

interface UpcomingResponse {
  items: UpcomingItem[];
  suggestions_available: number;
}

export function UpcomingTransactionsWidget({
  refreshKey,
}: {
  refreshKey: number;
}) {
  const router = useRouter();
  const { data, loading, error } = useWidgetData<UpcomingResponse>(
    `${API_URL}/recurring/upcoming/${CURRENT_USER_ID}?days=${WINDOW_DAYS}`,
    refreshKey,
  );

  const items = data?.items ?? [];
  const suggestions = data?.suggestions_available ?? 0;

  return (
    <WidgetCard
      title="Upcoming Transactions"
      loading={loading && !data}
      error={error}
      showArrow
      onPress={() => router.push("/recurring" as any)}
    >
      {items.length === 0 ? (
        <Text style={styles.empty}>
          {suggestions > 0
            ? "Nothing is set up yet."
            : `Nothing due in the next ${WINDOW_DAYS} days.`}
        </Text>
      ) : (
        items.slice(0, MAX_ROWS).map((item, i) => (
          <View key={item.id} style={[styles.row, i > 0 && styles.rowDivider]}>
            <Text style={styles.meta}>
              {dueLabel(item.next_due_date)} ·{" "}
              {repeatLabel(item.interval_count, item.interval_unit)}
            </Text>
            <View style={styles.line}>
              <Text numberOfLines={1} style={styles.label}>
                {ruleTitle(item)}
              </Text>
              <Text
                style={[
                  styles.amount,
                  {
                    color:
                      Number(item.expected_amount) < 0 ? "#d93025" : "#1a9e4b",
                  },
                ]}
              >
                {item.amount_varies ? "~" : ""}
                {formatMoney(item.expected_amount, item.currency)}
              </Text>
            </View>
          </View>
        ))
      )}

      {items.length > MAX_ROWS && (
        <Text style={styles.more}>+ {items.length - MAX_ROWS} more</Text>
      )}

      {suggestions > 0 && (
        <Text style={styles.review}>
          {suggestions} suggestion{suggestions === 1 ? "" : "s"} to review
        </Text>
      )}
    </WidgetCard>
  );
}

const styles = StyleSheet.create({
  row: { paddingVertical: 8 },
  rowDivider: { borderTopWidth: 1, borderColor: "#f0f0f0" },
  // The second line: the name on the left, the amount on the right.
  line: { flexDirection: "row", alignItems: "center", marginTop: 2 },
  label: { flex: 1, fontSize: 14, marginRight: 8 },
  meta: { fontSize: 11, color: "#999" },
  amount: { fontSize: 14, fontWeight: "600" },
  more: { color: "#999", fontSize: 11, marginTop: 6 },
  review: { color: "#007AFF", fontSize: 12, fontWeight: "600", marginTop: 10 },
  empty: { color: "#999", fontSize: 13 },
});
