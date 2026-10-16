import { isAllowedSourceUrl, type PlayoffsNote } from "@/lib/playoffs-notes";

// `/playoffs` 全頁頁尾說明區（#285 續做 WP2；MOUNT-CONTRACT r3 §2.4）：所有區塊之後、頁面最下方。
// 0 條 ⇒ 整區不渲染（無標題、無空框）。每條 `<li id="note-<key>">`，格內狀態可連 `#note-<key>`。
// 純文字；來源連結只收站內相對路徑或官方站 https。⛔ 截斷、⛔ 摺疊。

export function PageNotes({ notes }: { notes: readonly PlayoffsNote[] }) {
  if (!notes.length) return null;
  return (
    <section aria-labelledby="page-notes-heading" className="border-t border-line pt-3" data-page-notes>
      <h2 id="page-notes-heading" className="text-xs font-bold text-muted">資料說明</h2>
      <ul className="mt-1.5 space-y-1 text-xs text-muted">
        {notes.map((n) => (
          <li key={n.key} id={`note-${n.key}`}>
            {n.text}
            {n.source && isAllowedSourceUrl(n.source.url) ? (
              <>
                {"（"}
                <a href={n.source.url} className="text-accent underline-offset-2 hover:underline"
                  {...(n.source.url.startsWith("/") ? {} : { target: "_blank", rel: "noopener noreferrer" })}>{n.source.label}</a>
                {"）"}
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default PageNotes;
