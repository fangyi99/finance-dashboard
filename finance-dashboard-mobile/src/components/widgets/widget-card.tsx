import { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

interface WidgetCardProps {
  title: string;
  loading?: boolean; // only true while there's nothing to show yet, so a refresh doesn't flicker
  error?: string;
  onPress?: () => void;
  showArrow?: boolean; // a chevron on the right, to show the whole card is a link
  children?: ReactNode;
}

export function WidgetCard({
  title,
  loading,
  error,
  onPress,
  showArrow,
  children,
}: WidgetCardProps) {
  const content = (
    <>
      <View style={styles.header}>
        <Text style={styles.title}>{title}</Text>
        {showArrow ? <Text style={styles.arrow}>›</Text> : null}
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginVertical: 16 }} />
      ) : error ? (
        <Text style={styles.error}>{error}</Text>
      ) : (
        children
      )}
    </>
  );

  return onPress ? (
    <Pressable style={styles.card} onPress={onPress}>
      {content}
    </Pressable>
  ) : (
    <View style={styles.card}>{content}</View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    backgroundColor: "#fff",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 10,
  },
  title: {
    fontSize: 13,
    fontWeight: "700",
    color: "#666",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
  arrow: { fontSize: 22, color: "#ccc", lineHeight: 22 },
  error: { color: "red", fontSize: 13 },
});
