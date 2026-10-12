import { useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { WheelPicker } from "@/components/wheelpicker";
import { maxCount, Unit, unitOptionLabel, UNITS } from "@/utils/recurring";

export interface RepeatValue {
  count: number;
  unit: Unit;
}

interface RepeatPickerProps {
  visible: boolean;
  value: RepeatValue;
  onChange: (value: RepeatValue) => void;
  onClose: () => void;
}

// The popup both repeat controls open: two scroll wheels — "Every [3] [month(s)]". The
// choice only counts once Done is pressed; tapping outside discards it.
export function RepeatPicker({
  visible,
  value,
  onChange,
  onClose,
}: RepeatPickerProps) {
  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose}>
        {/* Only built while open, so it starts afresh from the current value every time
            instead of remembering an earlier, unconfirmed scroll. */}
        {visible && (
          <Sheet
            value={value}
            onDone={(chosen) => {
              onChange(chosen);
              onClose();
            }}
          />
        )}
      </Pressable>
    </Modal>
  );
}

// "day(s)", "week(s)"... — fixed labels, so they never depend on the number beside them.
const UNIT_ITEMS = UNITS.map((unit) => ({
  label: unitOptionLabel(unit),
  value: unit,
}));

function Sheet({
  value,
  onDone,
}: {
  value: RepeatValue;
  onDone: (value: RepeatValue) => void;
}) {
  const [draft, setDraft] = useState<RepeatValue>(value);

  // Changing the unit can leave the number out of range (12 months -> years, which stops at
  // 5), so keep it within the new unit's limit.
  const changeUnit = (unit: Unit) =>
    setDraft((d) => ({ unit, count: Math.min(d.count, maxCount(unit)) }));

  const counts = Array.from({ length: maxCount(draft.unit) }, (_, i) => ({
    label: String(i + 1),
    value: i + 1,
  }));

  return (
    // Swallows taps, so touching the sheet's empty space doesn't close the popup.
    <Pressable style={styles.sheet} onPress={() => {}}>
      <Text style={styles.title}>Repeat</Text>

      <View style={styles.wheels}>
        <Text style={styles.every}>Every</Text>
        {/* keyed by unit so the number wheel starts fresh at the right row when its range changes */}
        <WheelPicker
          key={draft.unit}
          items={counts}
          value={draft.count}
          onChange={(count) => setDraft((d) => ({ ...d, count }))}
          width={90}
          accessibilityLabel="How many"
        />
        <WheelPicker
          items={UNIT_ITEMS}
          value={draft.unit}
          onChange={changeUnit}
          accessibilityLabel="Day, week, month or year"
        />
      </View>

      <Pressable style={styles.done} onPress={() => onDone(draft)}>
        <Text style={styles.doneText}>Done</Text>
      </Pressable>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.3)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 20,
    paddingBottom: 28,
  },
  title: {
    color: "#999",
    fontSize: 12,
    fontWeight: "600",
    textTransform: "uppercase",
    marginBottom: 8,
  },
  wheels: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 20,
  },
  every: { fontSize: 18, color: "#555", width: 56 },
  done: {
    backgroundColor: "#007AFF",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
  },
  doneText: { color: "#fff", fontWeight: "600", fontSize: 16 },
});
