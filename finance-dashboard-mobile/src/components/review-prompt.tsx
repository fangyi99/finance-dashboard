import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { formatMoney } from "@/utils/format";
import { loadReviewSummary, ReviewSummary } from "@/utils/review";
import { useSession } from "@/utils/session";

// A card for the top of the dashboard: "some of your transactions need a category", and what that costs you
// (spending that isn't in your budgets). Shows nothing when there's nothing to review, and nothing if the
// check fails: a prompt shouldn't nag you with errors.
export function ReviewPrompt({ refreshKey = 0 }: { refreshKey?: number }) {
  const router = useRouter();
  const { version } = useSession(); // reload when the data underneath changes (sandbox on/off, reset)
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const lastVersion = useRef(version);

  useEffect(() => {
    let active = true;
    if (lastVersion.current !== version) {
      lastVersion.current = version;
      setSummary(null); // never show the previous user's numbers while the new ones load
    }
    loadReviewSummary()
      .then((s) => active && setSummary(s))
      .catch(() => active && setSummary(null));
    return () => {
      active = false;
    };
  }, [refreshKey, version]);

  if (!summary || summary.transactions === 0) return null;

  const groups = `${summary.groups} ${summary.groups === 1 ? "group" : "groups"}`;
  const spend = Number(summary.spend_total);
  return (
    <Pressable
      style={styles.card}
      onPress={() => router.push("/review" as any)}
    >
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>Needs a category</Text>
        <Text style={styles.headline}>
          {groups} · {summary.transactions}{" "}
          {summary.transactions === 1 ? "transaction" : "transactions"}
        </Text>
        <Text style={styles.body}>
          {spend > 0
            ? `${formatMoney(summary.spend_total, summary.currency)} of spending isn't counted in your budgets yet.`
            : "These aren't in your budgets or summaries until they have a category."}
        </Text>
      </View>
      <Text style={styles.cta}>Review ›</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff8e6",
    borderWidth: 1,
    borderColor: "#ffe0a3",
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  },
  title: {
    fontSize: 12,
    fontWeight: "700",
    color: "#8a6100",
    textTransform: "uppercase",
  },
  headline: { fontSize: 16, fontWeight: "700", marginTop: 4 },
  body: { fontSize: 13, color: "#6b6b6b", marginTop: 2 },
  cta: { fontSize: 14, fontWeight: "700", color: "#1a73e8", marginLeft: 12 },
});
