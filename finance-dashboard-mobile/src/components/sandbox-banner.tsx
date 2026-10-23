import { Pressable, StyleSheet, Text, View } from "react-native";

import { leaveSandbox, useSession } from "@/utils/session";

// A thin strip that says you're looking at sample data, with a way out. Shows nothing otherwise.
export function SandboxBanner() {
  const { sandbox } = useSession();
  if (!sandbox) return null;
  return (
    <View style={styles.bar}>
      <Text style={styles.text}>Sandbox mode · sample data</Text>
      <Pressable onPress={leaveSandbox} hitSlop={8}>
        <Text style={styles.exit}>Exit</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#fff4d6",
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  text: { fontSize: 12, fontWeight: "600", color: "#7a5b00" },
  exit: { fontSize: 12, fontWeight: "700", color: "#1a73e8" },
});
