/* 提案稿共用：主題切換（?theme=dark 或頁內按鈕）與頁籤鍵盤操作。不寫入 localStorage、不連網。 */
(function () {
  var root = document.documentElement;
  root.dataset.theme = new URLSearchParams(location.search).get("theme") === "dark" ? "dark" : "light";
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      var sync = function () { b.setAttribute("aria-pressed", root.dataset.theme === "dark" ? "true" : "false"); };
      sync();
      b.addEventListener("click", function () { root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark"; sync(); });
    });
    document.querySelectorAll('[role="tablist"]').forEach(function (list) {
      var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
      var select = function (t) {
        tabs.forEach(function (x) {
          var on = x === t;
          x.setAttribute("aria-selected", on ? "true" : "false");
          x.tabIndex = on ? 0 : -1;
          var p = document.getElementById(x.getAttribute("aria-controls"));
          if (p) p.hidden = !on;
        });
      };
      tabs.forEach(function (t, i) {
        t.addEventListener("click", function () { select(t); });
        t.addEventListener("keydown", function (e) {
          var n = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
          if (n === null) return;
          var nt = tabs[(n + tabs.length) % tabs.length]; select(nt); nt.focus();
          nt.scrollIntoView({ block: "nearest", inline: "nearest" }); /* 窄版頁籤橫向捲動時，focus 不一定把部分可見的頁籤捲進來 */
          e.preventDefault();
        });
      });
    });
  });
})();
