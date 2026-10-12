import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Button,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
} from "react-native";
import { Stack, useFocusEffect, useRouter } from "expo-router";

import { BudgetCard } from "@/components/budget-card";
import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { Budget } from "@/utils/budget";
import { showToast } from "@/utils/toast";

// How far the header + sits from the right edge of the screen. A stack header (like the
// Categories page's) adds its own side padding; a tab header adds none, so it's set here
// instead. 16 lines the + up with the right edge of the cards below. If it ever looks off,
// this is the one number to change: bigger moves it left, smaller moves it right.
const HEADER_ADD_INSET = 16;

export default function BudgetScreen() {
  const router = useRouter();

  // Budgets are monthly, so this is always the current month, like the dashboard.
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const monthLabel = now.toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
  });

  const [budgets, setBudgets] = useState<Budget[] | null>(null); // null until the first load
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/budgets/${CURRENT_USER_ID}?year=${year}&month=${month}`,
      );
      if (!res.ok) throw new Error("Couldn't load your budgets");
      setBudgets(await res.json());
      setError("");
    } catch (err: any) {
      setError(err.message || "Couldn't load your budgets");
    }
  }, [year, month]);

  // Reloads every time the tab comes back into view, so spending added elsewhere, and
  // budgets added or edited on their own screen, show up straight away.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const edit = (budget: Budget) =>
    router.push({ pathname: "/budget-form", params: { id: budget.id } } as any);

  const remove = async (budget: Budget) => {
    try {
      const res = await fetch(`${API_URL}/budgets/${budget.id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error();
      showToast(`Deleted "${budget.name}"`);
      await load();
    } catch {
      showToast("Couldn't delete that budget", "error");
    }
  };

  // Adding a budget is the + in the header, drawn like the Categories page's (same text
  // character, size and colour). Only headerRight is set: the tab's title still comes from
  // the tab layout.
  const headerOptions = {
    headerRight: () => (
      <Pressable
        onPress={() => router.push("/budget-form" as any)}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel="Add budget"
      >
        <Text style={styles.headerAdd}>+</Text>
      </Pressable>
    ),
  };

  return (
    <ScrollView
      style={styles.page}
      contentContainerStyle={{ padding: 16 }}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <Stack.Screen options={headerOptions} />
      <Text style={styles.monthHeading}>{monthLabel}</Text>

      {budgets === null ? (
        error ? (
          <>
            <Text style={styles.error}>{error}</Text>
            <Button title="Try again" onPress={load} />
          </>
        ) : (
          <ActivityIndicator style={{ marginTop: 32 }} />
        )
      ) : (
        <>
          {error ? <Text style={styles.error}>{error}</Text> : null}

          {budgets.length === 0 ? (
            <>
              <Text style={styles.emptyTitle}>No budgets yet</Text>
              <Text style={styles.empty}>
                Tap + to set a monthly spending limit.
              </Text>
            </>
          ) : (
            budgets.map((budget) => (
              <BudgetCard
                key={budget.id}
                budget={budget}
                onEdit={() => edit(budget)}
                onDelete={() => remove(budget)}
              />
            ))
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  headerAdd: {
    fontSize: 24,
    color: "#007AFF",
    fontWeight: "400",
    marginRight: HEADER_ADD_INSET,
  },
  monthHeading: { fontSize: 22, fontWeight: "700", marginBottom: 12 },
  error: { color: "red", textAlign: "center", marginTop: 16 },
  emptyTitle: {
    fontWeight: "600",
    textAlign: "center",
    marginTop: 40,
    fontSize: 16,
  },
  empty: { color: "#999", textAlign: "center", marginTop: 6 },
});
