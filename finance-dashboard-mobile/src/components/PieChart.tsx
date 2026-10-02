import { View, Text as RNText, StyleSheet } from "react-native";
import Svg, { Path, Circle, Text as SvgText, G } from "react-native-svg";

export interface PieSlice {
  label: string;
  value: number; // always pass a non-negative magnitude, not a signed amount
  color: string;
}

interface PieChartProps {
  data: PieSlice[];
  size?: number;
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(angleRad), y: cy + r * Math.sin(angleRad) };
}

function describeArc(
  cx: number,
  cy: number,
  r: number,
  startAngle: number,
  endAngle: number,
) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 0 ${end.x} ${end.y} Z`;
}

// A no-dependency pie chart on react-native-svg. Labels sit beside each slice (name,
// then percentage) rather than in a separate legend list. Known limitation: many thin
// slices can crowd or overlap — no collision-avoidance is built for that case yet.
export function PieChart({ data, size = 200 }: PieChartProps) {
  const r = size / 2;
  // Extra room around the circle for labels extending outward.
  const labelPadding = 70;
  const canvasSize = size + labelPadding * 2;
  const cx = canvasSize / 2;
  const cy = canvasSize / 2;

  const total = data.reduce((sum, d) => sum + d.value, 0);

  if (total === 0) {
    return (
      <View style={{ alignItems: "center" }}>
        <Svg width={size} height={size}>
          <Circle
            cx={r}
            cy={r}
            r={r - 2}
            fill="none"
            stroke="#eee"
            strokeWidth={2}
          />
        </Svg>
        <RNText style={styles.emptyText}>No data for this period</RNText>
      </View>
    );
  }

  let angle = 0;
  const slices = data
    .filter((d) => d.value > 0)
    .map((d) => {
      const sweep = (d.value / total) * 360;
      const startAngle = angle;
      const endAngle = angle + sweep;
      angle = endAngle;
      return { ...d, startAngle, endAngle, sweep };
    });

  return (
    <Svg width={canvasSize} height={canvasSize}>
      {slices.map((slice, i) =>
        // A single slice covering (essentially) the whole chart can't be drawn as an
        // arc — its start and end points coincide, which collapses to nothing. Draw
        // a plain circle instead whenever one slice holds effectively 100% of the total.
        slice.sweep >= 359.99 ? (
          <Circle key={i} cx={cx} cy={cy} r={r} fill={slice.color} />
        ) : (
          <Path
            key={i}
            d={describeArc(cx, cy, r, slice.startAngle, slice.endAngle)}
            fill={slice.color}
          />
        ),
      )}

      {slices.map((slice, i) => {
        const midAngle = (slice.startAngle + slice.endAngle) / 2;
        const labelPoint = polarToCartesian(cx, cy, r + 16, midAngle);
        const textAnchor = labelPoint.x >= cx ? "start" : "end";
        const pct = ((slice.value / total) * 100).toFixed(0);

        return (
          <G key={`label-${i}`}>
            <SvgText
              x={labelPoint.x}
              y={labelPoint.y}
              fontSize={12}
              fontWeight="600"
              fill="#333"
              textAnchor={textAnchor}
            >
              {slice.label}
            </SvgText>
            <SvgText
              x={labelPoint.x}
              y={labelPoint.y + 14}
              fontSize={11}
              fill="#888"
              textAnchor={textAnchor}
            >
              {pct}%
            </SvgText>
          </G>
        );
      })}
    </Svg>
  );
}

const styles = StyleSheet.create({
  emptyText: { color: "#999", fontSize: 12, marginTop: 8 },
});
