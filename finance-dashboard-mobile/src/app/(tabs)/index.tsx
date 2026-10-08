import { useCallback, useState } from "react";
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { DEFAULT_WIDGETS } from "@/constants/widgets";
import { FinancialSummaryWidget } from "@/components/widgets/financial-summary-widget";
import { TopExpensesWidget } from "@/components/widgets/top-expenses-widget";
import { TotalBalanceWidget } from "@/components/widgets/total-balance-widget";
import { UpcomingTransactionsWidget } from "@/components/widgets/upcoming-transactions-widget";

export default function DashboardScreen() {
  const router = useRouter();
  const [widgetKeys, setWidgetKeys] = useState<string[] | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  // The dashboard is always the current month. Worked out on every render, so it rolls
  // over by itself if the app is left open across midnight on the 1st.
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const monthLabel = now.toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
  });

  const loadWidgetPreferences = useCallback(() => {
    return fetch(`${API_URL}/widget-preferences/${CURRENT_USER_ID}`)
      .then((res) => res.json())
      .then((prefs) => {
        // The API returns these already sorted by display_order. Empty means the picker
        // was never completed, so fall back to the defaults rather than a blank screen.
        const keys = Array.isArray(prefs)
          ? prefs
              .filter((p: any) => p.is_enabled)
              .map((p: any) => p.widget_key as string)
          : [];
        setWidgetKeys(keys.length > 0 ? keys : [...DEFAULT_WIDGETS]);
      })
      .catch(() => setWidgetKeys((current) => current ?? [...DEFAULT_WIDGETS]));
  }, []);

  // Refetch everything whenever this tab comes back into view, so numbers are fresh after
  // an import or a category change made on another screen.
  useFocusEffect(
    useCallback(() => {
      loadWidgetPreferences();
      setRefreshKey((k) => k + 1);
    }, [loadWidgetPreferences]),
  );

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadWidgetPreferences();
    setRefreshKey((k) => k + 1);
    // Each widget fetches for itself, so there's nothing single to await here.
    setTimeout(() => setRefreshing(false), 700);
  }, [loadWidgetPreferences]);

  const renderWidget = (key: string) => {
    switch (key) {
      case "balance_summary":
        return <TotalBalanceWidget key={key} refreshKey={refreshKey} />;
      case "monthly_summary":
        return (
          <FinancialSummaryWidget
            key={key}
            year={year}
            month={month}
            refreshKey={refreshKey}
          />
        );
      case "top_expenses":
        return (
          <TopExpensesWidget
            key={key}
            year={year}
            month={month}
            refreshKey={refreshKey}
          />
        );
      case "upcoming_transactions":
        return <UpcomingTransactionsWidget key={key} />;
      default:
        return null; // a saved key this version doesn't know about (e.g. a removed widget)
    }
  };

  return (
    <ScrollView
      style={styles.page}
      contentContainerStyle={{ padding: 16 }}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <Text style={styles.monthHeading}>{monthLabel}</Text>

      {widgetKeys === null ? null : widgetKeys.length === 0 ? (
        <Text style={styles.empty}>No widgets selected.</Text>
      ) : (
        widgetKeys.map(renderWidget)
      )}

      <Pressable
        onPress={() =>
          router.push({
            pathname: "/onboarding",
            params: { from: "settings" },
          } as any)
        }
      >
        <Text style={styles.customize}>Customize widgets</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  monthHeading: { fontSize: 22, fontWeight: "700", marginBottom: 16 },
  empty: { color: "#999", textAlign: "center", marginTop: 32 },
  customize: {
    color: "#007AFF",
    textAlign: "center",
    marginTop: 4,
    marginBottom: 24,
    fontSize: 13,
  },
});
