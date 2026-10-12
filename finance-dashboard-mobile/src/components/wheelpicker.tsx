import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

export const WHEEL_ITEM_HEIGHT = 44;
const VISIBLE_ROWS = 3; // the chosen row in the middle, one above and one below

interface WheelPickerProps<T extends string | number> {
  items: { label: string; value: T }[];
  value: T;
  onChange: (value: T) => void;
  width?: number;
  accessibilityLabel?: string;
}

// A vertical scroll wheel: flick or drag it and the row that stops in the middle band is
// chosen. Built from a plain ScrollView (no native picker package).
//
// The value is committed a moment after scrolling STOPS, not on every frame — so the
// highlight follows your finger live, but the form only changes once you've settled. The
// "settle" step also snaps to the nearest row, which is what makes it work on the web,
// where `snapToInterval` isn't available.
export function WheelPicker<T extends string | number>({
  items,
  value,
  onChange,
  width,
  accessibilityLabel,
}: WheelPickerProps<T>) {
  const scrollRef = useRef<ScrollView>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef({ value, onChange, items });
  latest.current = { value, onChange, items };

  const chosenIndex = Math.max(
    0,
    items.findIndex((item) => item.value === value),
  );
  const [liveIndex, setLiveIndex] = useState(chosenIndex);
  const padding = WHEEL_ITEM_HEIGHT * ((VISIBLE_ROWS - 1) / 2);

  // Put the chosen row in the middle when the wheel appears, and whenever the value is
  // changed from outside (e.g. the number clamps when the unit changes).
  useEffect(() => {
    setLiveIndex(chosenIndex);
    const id = setTimeout(
      () =>
        scrollRef.current?.scrollTo({
          y: chosenIndex * WHEEL_ITEM_HEIGHT,
          animated: false,
        }),
      0,
    );
    return () => clearTimeout(id);
  }, [chosenIndex, items.length]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const indexAt = (y: number) =>
    Math.min(
      latest.current.items.length - 1,
      Math.max(0, Math.round(y / WHEEL_ITEM_HEIGHT)),
    );

  const settle = (y: number) => {
    const next = indexAt(y);
    if (Math.abs(y - next * WHEEL_ITEM_HEIGHT) > 1) {
      scrollRef.current?.scrollTo({
        y: next * WHEEL_ITEM_HEIGHT,
        animated: true,
      });
    }
    const chosen = latest.current.items[next];
    if (chosen && chosen.value !== latest.current.value)
      latest.current.onChange(chosen.value);
  };

  const handleScroll = (event: {
    nativeEvent: { contentOffset: { y: number } };
  }) => {
    const y = event.nativeEvent.contentOffset.y;
    setLiveIndex(indexAt(y));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => settle(y), 120);
  };

  return (
    <View
      style={[
        styles.wheel,
        { height: WHEEL_ITEM_HEIGHT * VISIBLE_ROWS },
        width ? { width } : { flex: 1 },
      ]}
      accessibilityLabel={accessibilityLabel}
    >
      {/* The band the chosen row sits in; drawn first so the text is on top of it. */}
      <View
        pointerEvents="none"
        style={[styles.band, { top: padding, height: WHEEL_ITEM_HEIGHT }]}
      />
      <ScrollView
        ref={scrollRef}
        showsVerticalScrollIndicator={false}
        snapToInterval={WHEEL_ITEM_HEIGHT}
        decelerationRate="fast"
        scrollEventThrottle={16}
        onScroll={handleScroll}
        nestedScrollEnabled
        contentContainerStyle={{ paddingVertical: padding }}
      >
        {items.map((item, index) => (
          <Pressable
            key={String(item.value)}
            style={styles.item}
            onPress={() => {
              scrollRef.current?.scrollTo({
                y: index * WHEEL_ITEM_HEIGHT,
                animated: true,
              });
              setLiveIndex(index);
              if (item.value !== value) onChange(item.value);
            }}
          >
            <Text
              style={
                index === liveIndex ? styles.itemSelected : styles.itemText
              }
            >
              {item.label}
            </Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wheel: { overflow: "hidden" },
  band: {
    position: "absolute",
    left: 0,
    right: 0,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: "#d8d8d8",
    backgroundColor: "#f4f8ff",
  },
  item: {
    height: WHEEL_ITEM_HEIGHT,
    alignItems: "center",
    justifyContent: "center",
  },
  itemText: { fontSize: 18, color: "#aaa" },
  itemSelected: { fontSize: 20, fontWeight: "600", color: "#000" },
});
