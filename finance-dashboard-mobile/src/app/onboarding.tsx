import { useState } from "react";
import { View, Text, Pressable, Button, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { API_URL, CURRENT_USER_ID } from "@/constants/config";

const AVAILABLE_WIDGETS = [
  {
    key: "balance_summary",
    label: "Balance Summary",
    description: "Total balance across all accounts",
  },
  {
    key: "monthly_summary",
    label: "Monthly Summary",
    description: "Income, expenses, and savings this month",
  },
  {
    key: "top_expenses",
    label: "Top Expenses",
    description: "Your biggest transactions this month",
  },
  {
    key: "upcoming_transactions",
    label: "Upcoming Transactions",
    description: "Recurring charges due soon",
  },
  {
    key: "recent_transactions",
    label: "Recent Transactions",
    description: "Your latest activity",
  },
];

export default function OnboardingScreen() {
  const router = useRouter();
  const DEFAULT_SELECTED = [
    "balance_summary",
    "monthly_summary",
    "upcoming_transactions",
  ];
  const [selected, setSelected] = useState<Set<string>>(
    new Set(DEFAULT_SELECTED),
  );

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const handleContinue = async () => {
    const preferences = Array.from(selected).map((key, index) => ({
      widget_key: key,
      is_enabled: true,
      display_order: index,
    }));

    try {
      await fetch(`${API_URL}/widget-preferences`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: CURRENT_USER_ID, preferences }),
      });
      router.replace("/tab-onboarding"); // instead of router.replace('/')
    } catch (err) {
      console.error("Failed to save widget preferences", err);
    }
  };

  return (
    <View style={{ padding: 20, paddingTop: 60 }}>
      <Text style={{ fontSize: 22, fontWeight: "bold", marginBottom: 8 }}>
        Customize your dashboard
      </Text>
      <Text style={{ color: "#666", marginBottom: 20 }}>
        Pick the widgets you want to see
      </Text>

      {AVAILABLE_WIDGETS.map((widget) => {
        const isSelected = selected.has(widget.key);
        return (
          <Pressable
            key={widget.key}
            onPress={() => toggle(widget.key)}
            style={[styles.widgetRow, isSelected && styles.widgetRowSelected]}
          >
            <Text style={{ fontWeight: "600" }}>{widget.label}</Text>
            <Text style={{ color: "#666", fontSize: 12 }}>
              {widget.description}
            </Text>
          </Pressable>
        );
      })}

      <View style={{ marginTop: 20 }}>
        <Button
          title="Continue"
          onPress={handleContinue}
          disabled={selected.size === 0}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  widgetRow: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
  },
  widgetRowSelected: {
    borderColor: "#007AFF",
    backgroundColor: "#EAF3FF",
  },
});
