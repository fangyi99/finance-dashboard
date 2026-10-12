import { Pressable, StyleSheet, Text, View } from "react-native";

interface RadioRowProps<T extends string> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}

// A radio group drawn as separate buttons in a row — like tabs, but each one stands on its
// own (its own border, a gap between them, no shared bar behind them). Exactly one is
// chosen at a time, and the chosen one is filled. Underneath it's still a radio group.
export function RadioRow<T extends string>({
  options,
  value,
  onChange,
}: RadioRowProps<T>) {
  return (
    <View style={styles.row}>
      {options.map((option, index) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            style={[
              styles.button,
              // A real margin rather than `gap`, so they can never end up touching.
              index < options.length - 1 && styles.spaced,
              selected && styles.buttonSelected,
            ]}
            onPress={() => onChange(option.value)}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
          >
            <Text style={selected ? styles.labelSelected : styles.label}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row" },
  // The same corners and height as the text inputs and the Add button, so it reads as a
  // normal button rather than a capsule.
  button: {
    flex: 1,
    alignItems: "center",
    paddingVertical: 11,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#ccc",
    backgroundColor: "#fff",
  },
  spaced: { marginRight: 10 },
  buttonSelected: { backgroundColor: "#007AFF", borderColor: "#007AFF" },
  label: { color: "#222", fontSize: 14 },
  labelSelected: { color: "#fff", fontSize: 14, fontWeight: "600" },
});
