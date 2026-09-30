import { useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

interface Action {
  label: string;
  onPress?: () => void;
  destructive?: boolean;
}

interface ActionMenuProps {
  actions: Action[];
  // Shown instead of the actions list when there's nothing the user can do here
  // (e.g. a default category) — keeps the menu honest rather than empty.
  disabledLabel?: string;
}

// Same Modal + backdrop + bottom sheet shape as Dropdown, so this doesn't introduce
// a second UI pattern for what's essentially the same kind of popover.
export function ActionMenu({ actions, disabledLabel }: ActionMenuProps) {
  const [open, setOpen] = useState(false);

  return (
    <View>
      <Pressable
        onPress={() => setOpen(true)}
        hitSlop={8}
        style={styles.trigger}
      >
        <Text style={styles.dots}>⋮</Text>
      </Pressable>

      <Modal
        visible={open}
        transparent
        animationType="fade"
        onRequestClose={() => setOpen(false)}
      >
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <View style={styles.sheet}>
            {disabledLabel ? (
              <View style={styles.option}>
                <Text style={styles.disabledText}>{disabledLabel}</Text>
              </View>
            ) : (
              actions.map((action) => (
                <Pressable
                  key={action.label}
                  style={styles.option}
                  onPress={() => {
                    setOpen(false);
                    action.onPress?.();
                  }}
                >
                  <Text
                    style={
                      action.destructive
                        ? styles.destructiveText
                        : styles.optionText
                    }
                  >
                    {action.label}
                  </Text>
                </Pressable>
              ))
            )}
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  trigger: { paddingHorizontal: 8, paddingVertical: 4 },
  dots: { fontSize: 18, color: "#666", fontWeight: "700" },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.3)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 8,
    paddingBottom: 24,
  },
  option: { padding: 16 },
  optionText: { fontSize: 16 },
  destructiveText: { fontSize: 16, color: "#FF3B30" },
  disabledText: { fontSize: 15, color: "#999" },
});
