import { useState } from "react";
import {
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

interface DropdownProps {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  placeholder?: string;
}

// A plain custom dropdown (no @react-native-picker/picker) so this doesn't add
// another native module to the project, after today's native-module troubles.
export function Dropdown({
  label,
  value,
  options,
  onChange,
  placeholder,
}: DropdownProps) {
  const [open, setOpen] = useState(false);

  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <Pressable style={styles.field} onPress={() => setOpen(true)}>
        <Text style={value ? styles.value : styles.placeholder}>
          {value || placeholder || "Select..."}
        </Text>
        <Text style={styles.chevron}>▾</Text>
      </Pressable>

      <Modal
        visible={open}
        transparent
        animationType="fade"
        onRequestClose={() => setOpen(false)}
      >
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <View style={styles.sheet}>
            <FlatList
              data={options}
              keyExtractor={(item) => item}
              renderItem={({ item }) => (
                <Pressable
                  style={styles.option}
                  onPress={() => {
                    onChange(item);
                    setOpen(false);
                  }}
                >
                  <Text
                    style={
                      item === value ? styles.optionSelected : styles.optionText
                    }
                  >
                    {item}
                  </Text>
                </Pressable>
              )}
            />
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

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
  placeholder: { color: "#999" },
  chevron: { color: "#999" },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.3)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: "#fff",
    maxHeight: "60%",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 8,
  },
  option: { padding: 14 },
  optionText: { fontSize: 16 },
  optionSelected: { fontSize: 16, fontWeight: "700", color: "#007AFF" },
});
