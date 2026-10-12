import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { RepeatPicker, RepeatValue } from "@/components/repeat-picker";
import { repeatLabel } from "@/utils/recurring";

interface RepeatButtonProps {
  value: RepeatValue;
  onChange: (value: RepeatValue) => void;
}

// An icon-only button that opens the repeat popup. The current choice isn't written on the
// button: it's in the accessibility label, and the form shows it in a line of text beside
// the date.
export function RepeatButton({ value, onChange }: RepeatButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <View>
      <Pressable
        style={styles.button}
        onPress={() => setOpen(true)}
        hitSlop={6}
        accessibilityRole="button"
        accessibilityLabel={`Repeat: ${repeatLabel(value.count, value.unit)}`}
      >
        <Ionicons name="repeat" size={22} color="#007AFF" />
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

const styles = StyleSheet.create({
  // Same height as a text input beside it (12px padding + a line of text), so the two line up.
  button: {
    width: 46,
    height: 46,
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
});
