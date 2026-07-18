export const ANCHOR_LAYERS = ["overview", "approach", "splits", "career"] as const;

export type AnchorLayer = (typeof ANCHOR_LAYERS)[number];

/** URL hash 是錨點變體跨 Next.js remount 的唯一定位來源。 */
export function anchorLayerFromHash(hash: string): AnchorLayer | null {
  const id = hash.startsWith("#") ? hash.slice(1) : hash;
  return (ANCHOR_LAYERS as readonly string[]).includes(id) ? id as AnchorLayer : null;
}

/** role tab 被捲入視窗時 DOM scrollspy 可能暫時回到總覽；已存在的 hash 才是使用者原本的層。 */
export function anchorHashForRoleSwitch(currentHash: string, visibleLayer: AnchorLayer): string {
  return anchorLayerFromHash(currentHash) ? currentHash : `#${visibleLayer}`;
}
