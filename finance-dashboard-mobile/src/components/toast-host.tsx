import { useContext, useEffect, useRef, useState } from "react";
import { Animated, Platform, StyleSheet, Text, View } from "react-native";
import { SafeAreaInsetsContext } from "react-native-safe-area-context";

import { subscribeToasts, Toast } from "@/utils/toast";

const DEFAULT_DURATION = 2500; // how long a toast stays, in ms

// Draws toasts over whatever screen is showing. Mount it ONCE, at the root of the app,
// beside the navigator — not on a screen — so a toast outlives the screen that raised it.
export function ToastHost({
  duration = DEFAULT_DURATION,
}: {
  duration?: number;
}) {
  const [toast, setToast] = useState<Toast | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Read the context directly rather than via useSafeAreaInsets(), which throws if there's
  // no provider; here a missing one just means no extra inset.
  const insets = useContext(SafeAreaInsetsContext) as { bottom: number } | null;
  const useNativeDriver = Platform.OS !== "web";

  useEffect(() => {
    const unsubscribe = subscribeToasts((next) => {
      if (timer.current) clearTimeout(timer.current);
      setToast(next);
      Animated.timing(opacity, {
        toValue: 1,
        duration: 150,
        useNativeDriver,
      }).start();
      timer.current = setTimeout(() => {
        Animated.timing(opacity, {
          toValue: 0,
          duration: 250,
          useNativeDriver,
        }).start(() =>
          // Only clear it if a newer toast hasn't replaced it meanwhile.
          setToast((current) =>
            current && current.id === next.id ? null : current,
          ),
        );
      }, duration);
    });
    return () => {
      unsubscribe();
      if (timer.current) clearTimeout(timer.current);
    };
  }, [duration]);

  if (!toast) return null;

  return (
    // Never intercepts touches: a toast must not get in the way of what's underneath it.
    // Sits above the tab bar on tab screens.
    <View
      pointerEvents="none"
      style={[styles.wrap, { bottom: (insets?.bottom ?? 0) + 64 }]}
    >
      <Animated.View
        style={[
          styles.toast,
          toast.kind === "error" && styles.toastError,
          { opacity },
        ]}
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
      >
        <Text style={styles.text}>{toast.message}</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    left: 0,
    right: 0,
    alignItems: "center",
    paddingHorizontal: 16,
  },
  toast: {
    backgroundColor: "#222",
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 18,
    maxWidth: "92%",
    elevation: 4,
  },
  toastError: { backgroundColor: "#B3261E" },
  text: { color: "#fff", fontSize: 14 },
});
