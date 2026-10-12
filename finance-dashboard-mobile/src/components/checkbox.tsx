import { Pressable, StyleSheet, Text, View } from "react-native";

interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}

export function Checkbox({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: CheckboxProps) {
  return (
    <Pressable
      style={[styles.row, disabled && { opacity: 0.6 }]}
      disabled={disabled}
      onPress={() => onChange(!checked)}
      accessibilityRole="checkbox"
      accessibilityState={{ checked, disabled: !!disabled }}
    >
      <View style={[styles.box, checked && styles.boxChecked]}>
        {checked ? <Text style={styles.tick}>✓</Text> : null}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.label}>{label}</Text>
        {hint ? <Text style={styles.hint}>{hint}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  box: {
    width: 22,
    height: 22,
    borderRadius: 5,
    borderWidth: 2,
    borderColor: "#bbb",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 1,
  },
  boxChecked: { backgroundColor: "#007AFF", borderColor: "#007AFF" },
  tick: { color: "#fff", fontSize: 14, fontWeight: "700", lineHeight: 16 },
  label: { fontSize: 15, fontWeight: "600" },
  hint: { color: "#999", fontSize: 12, marginTop: 2 },
});
