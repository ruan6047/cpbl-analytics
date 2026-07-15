const VENUE_ALIASES: Readonly<Record<string, string>> = {
  台中: "國體",
  桃園: "樂天桃園",
  亞太副場: "亞太副",
};

export function canonicalVenue(venue: string): string {
  return VENUE_ALIASES[venue] ?? venue;
}

export function hasSplitRows<T>(split: { top: T[]; bottom: T[] }): boolean {
  return split.top.length > 0 || split.bottom.length > 0;
}
