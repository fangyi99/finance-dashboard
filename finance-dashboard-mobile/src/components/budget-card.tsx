import { StyleSheet, Text, View } from "react-native";

import { ActionMenu } from "@/components/ActionMenu";
import { BudgetBar } from "@/components/budget-bar";
import { Budget, formatDollars } from "@/utils/budget";

interface BudgetCardProps {
  budget: Budget;
  onEdit: () => void;
  onDelete: () => void;
}

// One budget:
//   Name                                      ⋮
//   $spent/$budgeted spent
//   [██████████ 45% ░░░░░░░░░░░░░░░░░░░░░░░]
//                          Remaining: $amount
export function BudgetCard({ budget, onEdit, onDelete }: BudgetCardProps) {
  const over = Number(budget.remaining) < 0;

  return (
    <View style={styles.card}>
      <View style={styles.titleRow}>
        <Text style={styles.name} numberOfLines={1}>
          {budget.name}
        </Text>
        <ActionMenu
          actions={[
            { label: "Edit", onPress: onEdit },
            { label: "Delete", destructive: true, onPress: onDelete },
          ]}
        />
      </View>

      <Text style={styles.spent}>
        {formatDollars(budget.spent)}/{formatDollars(budget.amount)} spent
      </Text>

      <BudgetBar spent={budget.spent} amount={budget.amount} />

      {/* The label stays small and quiet; the amount is what you read at a glance. */}
      <Text style={styles.remaining}>
        Remaining:{" "}
        <Text style={[styles.remainingAmount, over && styles.remainingOver]}>
          {formatDollars(budget.remaining)}
        </Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    backgroundColor: "#fff",
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  name: { flex: 1, fontSize: 16, fontWeight: "600", marginRight: 8 },
  spent: { fontSize: 13, color: "#555", marginTop: 2, marginBottom: 8 },
  remaining: { marginTop: 8, textAlign: "right", fontSize: 13, color: "#555" },
  remainingAmount: { fontSize: 18, fontWeight: "700", color: "#111" },
  remainingOver: { color: "#d93025" },
});
