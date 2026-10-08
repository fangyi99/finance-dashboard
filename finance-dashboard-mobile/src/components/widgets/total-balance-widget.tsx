import { StyleSheet, Text } from "react-native";
import { useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { useWidgetData } from "@/hooks/use-widget-data";
import { formatMoney } from "@/utils/format";
import { WidgetCard } from "./widget-card";

interface BalanceResponse {
  currencies: { currency: string; total: string; accounts: number }[];
}

export function TotalBalanceWidget({ refreshKey }: { refreshKey: number }) {
  const router = useRouter();
  const { data, loading, error } = useWidgetData<BalanceResponse>(
    `${API_URL}/summary/total-balance/${CURRENT_USER_ID}`,
    refreshKey,
  );

  const currencies = data?.currencies ?? [];

  return (
    <WidgetCard
      title="Total Balance"
      loading={loading && !data}
      error={error}
      showArrow
      onPress={() => router.push("/accounts" as any)}
    >
      {data && currencies.length === 0 ? (
        <Text style={styles.empty}>No balances yet</Text>
      ) : (
        // Normally one line. If accounts are in different currencies each gets its own
        // line — they're never added together, as there's no exchange-rate conversion.
        currencies.map((c) => (
          <Text
            key={c.currency}
            style={
              currencies.length === 1 ? styles.bigTotal : styles.mediumTotal
            }
          >
            {formatMoney(c.total, c.currency)}
          </Text>
        ))
      )}
    </WidgetCard>
  );
}

const styles = StyleSheet.create({
  bigTotal: { fontSize: 30, fontWeight: "700" },
  mediumTotal: { fontSize: 22, fontWeight: "700", marginBottom: 2 },
  empty: { color: "#999", fontSize: 13 },
});
