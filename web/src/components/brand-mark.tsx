type BrandMarkProps = {
  className?: string;
  title?: string;
};

/** 本壘板輪廓中的 R：品牌文字已提供名稱時，呼叫端應標為 aria-hidden。 */
export function BrandMark({ className, title }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title && <title>{title}</title>}
      <path fill="currentColor" d="M12 8h40l8 16-28 32L4 24z" />
      <path
        fill="var(--color-surface-2)"
        d="M23 18h13c8 0 13 4 13 11 0 5-3 8-7 9l9 12h-9L34 39h-3v11h-8zm8 7v8h5c3 0 5-1 5-4s-2-4-5-4z"
      />
    </svg>
  );
}
