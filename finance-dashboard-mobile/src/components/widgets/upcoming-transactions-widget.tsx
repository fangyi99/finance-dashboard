import { StyleSheet, Text } from "react-native";

import { WidgetCard } from "./widget-card";

// Stays a placeholder until recurring transactions exist.
export function UpcomingTransactionsWidget() {
  return (
    <WidgetCard title="Upcoming Transactions">
      <Text style={styles.text}>Coming soon.</Text>
    </WidgetCard>
  );
}

const styles = StyleSheet.create({ text: { color: "#999", fontSize: 13 } });
