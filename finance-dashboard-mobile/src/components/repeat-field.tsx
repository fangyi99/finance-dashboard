import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { RepeatPicker, RepeatValue } from "@/components/repeat-picker";
import { repeatLabel } from "@/utils/recurring";

interface RepeatFieldProps {
  label?: string;
  value: RepeatValue;
  onChange: (value: RepeatValue) => void;
}

// A normal-looking input field showing the current repeat ("Monthly", "Every 3 months").
// Tapping it opens the same scroll-wheel popup as the icon button on the add form.
export function RepeatField({
  label = "Repeat",
  value,
  onChange,
}: RepeatFieldProps) {
  const [open, setOpen] = useState(false);
  const shown = repeatLabel(value.count, value.unit);

  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <Pressable
        style={styles.field}
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={`${label}: ${shown}`}
      >
        <Text style={styles.value}>{shown}</Text>
        <Text style={styles.chevron}>▾</Text>
      </Pressable>
      <RepeatPicker
        visible={open}
        value={value}
        onChange={onChange}
        onClose={() => setOpen(false)}
      />
    </View>
  );
}

// Matches the Dropdown field, so it sits naturally among the other inputs.
const styles = StyleSheet.create({
  label: { fontWeight: "600", marginTop: 16, marginBottom: 8 },
  field: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    padding: 12,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  value: { color: "#000" },
  chevron: { color: "#999" },
});
