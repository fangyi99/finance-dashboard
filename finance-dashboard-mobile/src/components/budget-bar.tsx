import { StyleSheet, Text, View } from "react-native";

import { BUDGET_COLORS, budgetProgress } from "@/utils/budget";

// Below this much of the bar, the percentage wouldn't fit inside the coloured part, so it's
// written just after it instead.
const LABEL_INSIDE_AT = 15;

interface BudgetBarProps {
  spent: string | number;
  amount: string | number;
}

// A horizontal bar showing how much of a budget is used, with the percentage written on it.
// It fills to 100% at most, but the number keeps counting (120% when over), and the colour
// goes from green to amber to red as the budget gets used up.
export function BudgetBar({ spent, amount }: BudgetBarProps) {
  const { fill, label, status } = budgetProgress(spent, amount);
  const inside = fill >= LABEL_INSIDE_AT;

  return (
    <View
      style={styles.track}
      accessibilityRole="progressbar"
      accessibilityLabel={`${label}% of the budget used`}
      accessibilityValue={{ min: 0, max: 100, now: Math.round(fill) }}
    >
      <View
        style={[
          styles.fill,
          { width: `${fill}%`, backgroundColor: BUDGET_COLORS[status] },
        ]}
      >
        {inside && <Text style={styles.insideLabel}>{label}%</Text>}
      </View>
      {!inside && (
        <Text style={[styles.outsideLabel, { left: `${fill}%` }]}>
          {label}%
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: 22,
    borderRadius: 11,
    backgroundColor: "#eee",
    overflow: "hidden",
  },
  fill: {
    height: "100%",
    borderRadius: 11,
    justifyContent: "center",
    alignItems: "flex-end",
    paddingRight: 8,
  },
  insideLabel: { color: "#fff", fontSize: 12, fontWeight: "700" },
  outsideLabel: {
    position: "absolute",
    top: 0,
    bottom: 0,
    paddingLeft: 8,
    lineHeight: 22,
    fontSize: 12,
    fontWeight: "700",
    color: "#555",
  },
});
