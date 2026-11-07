import { Text, type BaseTickContentProps } from "recharts";

/**
 * 雷達軸名的預設刻度（樣式物件版的等價 render function）。
 *
 * recharts 3 的 PolarAngleAxis 會依刻度角度注入 verticalAnchor（左右兩側 middle、下半部 start），
 * 2.x 不傳、Text 一律用預設 end；同一份 `tick={{ fontSize, fill }}` 升級後軸名因此下移
 * 0.355em／0.71em（#423 審核：名單抽屜「續航」「控球」下移約 4 px）。
 * 這裡把 verticalAnchor 固定回 end，其餘屬性、class 與字串照 3.x 預設刻度原樣交給 Text，
 * 只為讓軸名回到升級前的位置；不改樣式與圖表結構。
 */
export function legacyAngleTick(style: { fontSize: number; fill: string }) {
  function LegacyAngleTick(props: BaseTickContentProps) {
    return (
      <Text {...props} {...style} verticalAnchor="end" className="recharts-polar-angle-axis-tick-value">
        {props.payload.value}
      </Text>
    );
  }
  return LegacyAngleTick;
}
