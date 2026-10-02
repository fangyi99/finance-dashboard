import { View, Text, StyleSheet } from "react-native";

export interface BarItem {
  label: string;
  value: number; // always pass a non-negative magnitude, same convention as PieChart
  color: string;
}

interface BarChartProps {
  data: BarItem[];
  // Shows the raw value at the end of each bar if given (e.g. money formatting);
  // otherwise just the percentage of the largest bar.
  formatValue?: (value: number) => string;
}

// Same reasoning as PieChart: no charting library, just plain Views, since bar-width
// math is simpler than the pie chart's arc geometry and doesn't need one either.
export function BarChart({ data, formatValue }: BarChartProps) {
  const max = Math.max(0, ...data.map((d) => d.value));

  if (data.length === 0 || max === 0) {
    return <Text style={styles.emptyText}>No data for this period</Text>;
  }

  return (
    <View>
      {data.map((item, i) => {
        const widthPct = (item.value / max) * 100;
        return (
          <View key={i} style={styles.row}>
            <Text style={styles.label} numberOfLines={1}>
              {item.label}
            </Text>
            <View style={styles.track}>
              <View
                style={[
                  styles.fill,
                  { width: `${widthPct}%`, backgroundColor: item.color },
                ]}
              />
            </View>
            <Text style={styles.value}>
              {formatValue
                ? formatValue(item.value)
                : `${widthPct.toFixed(0)}%`}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { marginBottom: 12 },
  label: { fontSize: 13, marginBottom: 4 },
  track: {
    height: 14,
    backgroundColor: "#f0f0f0",
    borderRadius: 7,
    overflow: "hidden",
  },
  fill: { height: "100%", borderRadius: 7 },
  value: { fontSize: 11, color: "#666", marginTop: 2, textAlign: "right" },
  emptyText: {
    color: "#999",
    fontSize: 12,
    textAlign: "center",
    marginTop: 16,
  },
});
