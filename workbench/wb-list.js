/* =============================================================================
 * ct-base · 列表管理组件 (List Management Component) — window.WBList
 * -----------------------------------------------------------------------------
 * 框架级可复用的「管理列表」：筛选 + 排序 + 分页 + 行内增删改。
 * 设计约束（详见 workbench_ui.md §11，遵循工作台铁律 9/10）：
 *   · 单向数据流：load → apply(筛选/排序/分页) → render（唯一渲染入口，禁止渲染函数互调）
 *   · 事件处理只改 state，再调 apply()/render()；不在渲染函数内触发其它渲染函数
 *   · 仅用 --wb-* 令牌（样式在 wb-list.css）；图标全内联 SVG，禁止 emoji
 *   · 双语：读 window.WB_LANG + window.WB_T（键 wbl_*），或 opt.i18nExtra 覆盖
 *
 * 用法：
 *   const list = WBList.create({
 *     mount:"wb-list-mount",
 *     columns:[ {key:"title", label:{zh:"标题",en:"Title"}, searchable:true, sortable:true},
 *               {key:"date",  label:{zh:"日期",en:"Date"},  sortable:true, align:"right"} ],
 *     pageSize:10, selectable:true,
 *     fetchData: async () => [...],        // 业务提供数据；或传 data:[...]
 *     onEdit:(row)=>{...}, onDelete:(row)=>{...}, onSelect:(ids)=>{...}
 *   });
 *   // 卡片行模板（决策 C）：传入 rowRender 则整列表切到「卡片列表」布局（分页/排序/筛选/单条删除均复用）
 *   //   rowRender(row, lang) 返回卡片内部 HTML；选择框与操作按钮由组件自动叠加。
 *   //   WBList.create({ mount, rowRender:(r,l)=>`<article>...</article>`, fetchData, onDelete });
 *   // 不传 rowRender 时仍走原 <table> 表格布局（决策 A）。
 *   // 切语言时重建文案：在技能的 wbOnLangChange 里调 list.rerender()
 * ========================================================================== */
(function () {
  "use strict";

  // 默认文案（可被 I18N.wbl_* 或 opt.i18nExtra 覆盖）
  var DEF_I18N = {
    zh: { wblSearch: "搜索", wblSort: "排序", wblEmpty: "暂无数据", wblPage: "页",
          wblPrev: "上一页", wblNext: "下一页", wblSelected: "已选", wblConfirmDel: "确认删除该项？",
          wblActions: "操作", wblItems: "条" },
    en: { wblSearch: "Search", wblSort: "Sort", wblEmpty: "No data", wblPage: "page",
          wblPrev: "Prev", wblNext: "Next", wblSelected: "Selected", wblConfirmDel: "Delete this item?",
          wblActions: "Actions", wblItems: "items" }
  };

  function t(opt, key) {
    var l = window.WB_LANG || "zh";
    if (opt.i18nExtra && opt.i18nExtra[key] != null) return opt.i18nExtra[key];
    if (window.WB_T && window.WB_T["wbl_" + key] != null) return window.WB_T["wbl_" + key];
    return (DEF_I18N[l] || DEF_I18N.zh)[key];
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  // 内联 SVG 图标（禁止 emoji）
  var ICON = {
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    edit:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
    del:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/></svg>'
  };

  var WBList = {
    /** 创建列表控制器，返回 { refresh, rerender, getSelected } */
    create: function (opt) {
      var mount = document.getElementById(opt.mount);
      if (!mount) { console.warn("[WBList] 缺失挂载点 #" + opt.mount); return null; }

      var pageSize = opt.pageSize || 10;
      var columns = opt.columns || [];
      var selectable = !!opt.selectable;
      var rowId = opt.rowId || "id";
      var searchableKeys = opt.searchableKeys ||
        columns.filter(function (c) { return c.searchable; }).map(function (c) { return c.key; });

      var state = { all: [], filtered: [], page: 1, sortKey: null, sortDir: 1, q: "", selected: {}, _keepSearchFocus: false };

      function hasActions() { return !!(opt.onEdit || opt.onDelete); }
      function ridOf(r) { return opt.rowId ? r[rowId] : state.all.indexOf(r); }

      // ---------- 数据层 ----------
      function load() {
        var src = opt.fetchData ? opt.fetchData() : (opt.data || []);
        Promise.resolve(src).then(function (rows) {
          state.all = rows || [];
          state.page = 1;
          apply();                       // 单向：load → apply → render
        }).catch(function (e) {
          console.error("[WBList] fetchData 失败", e); state.all = []; apply();
        });
      }

      // ---------- 计算层：筛选 + 排序 + 分页切片 ----------
      function apply() {
        var rows = state.all;
        var q = (state.q || "").trim().toLowerCase();
        if (q && searchableKeys.length) {
          rows = rows.filter(function (r) {
            return searchableKeys.some(function (k) { return String(r[k] == null ? "" : r[k]).toLowerCase().indexOf(q) >= 0; });
          });
        }
        if (state.sortKey) {
          var col = columns.filter(function (c) { return c.key === state.sortKey; })[0];
          var dir = state.sortDir;
          rows = rows.slice().sort(function (a, b) {
            var av = col && col.sortValue ? col.sortValue(a) : a[state.sortKey];
            var bv = col && col.sortValue ? col.sortValue(b) : b[state.sortKey];
            if (av == null) av = ""; if (bv == null) bv = "";
            if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
            return String(av).localeCompare(String(bv), "zh-Hans-CN") * dir;
          });
        }
        state.filtered = rows;
        render();                        // 唯一渲染入口
      }

      // ---------- 渲染层（只读 state，禁止互调其它渲染函数） ----------
      function render() {
        var l = window.WB_LANG || "zh";
        var total = state.filtered.length;
        var totalPages = Math.max(1, Math.ceil(total / pageSize));
        if (state.page > totalPages) state.page = totalPages;
        var start = (state.page - 1) * pageSize;
        var pageRows = state.filtered.slice(start, start + pageSize);

        var headHtml = columns.map(function (c) {
          var label = (c.label && (c.label[l] || c.label.zh)) || c.key;
          var arrow = (state.sortKey === c.key) ? '<span class="arrow">' + (state.sortDir > 0 ? "▲" : "▼") + "</span>" : "";
          return '<th class="' + (c.align === "right" ? "wb-num " : "") + (c.sortable ? "sortable" : "") + '"' +
            (c.sortable ? ' data-sort="' + esc(c.key) + '"' : "") + ">" + esc(label) + arrow + "</th>";
        }).join("") +
          (selectable ? "<th></th>" : "") +
          (hasActions() ? '<th class="actions">' + esc(t(opt, "wblActions")) + "</th>" : "");

        var bodyHtml = pageRows.map(function (r) {
          var rid = ridOf(r);
          var cells = columns.map(function (c) {
            var v = c.render ? c.render(r, l) : esc(r[c.key]);
            return '<td class="' + (c.align === "right" ? "wb-num " : "") + '" data-label="' + esc((c.label && (c.label[l] || c.label.zh)) || c.key) + '">' + v + "</td>";
          }).join("");
          var sel = selectable ? '<td><input type="checkbox" class="wb-list-sel" data-rid="' + esc(rid) + '"' + (state.selected[rid] ? " checked" : "") + "></td>" : "";
          var acts = hasActions() ? '<td class="actions">' + actionsHtml(rid) + "</td>" : "";
          return '<tr class="' + (state.selected[rid] ? "sel" : "") + '" data-rid="' + esc(rid) + '">' + cells + sel + acts + "</tr>";
        }).join("");

        var barHtml =
          '<div class="wb-list-bar">' +
            '<label class="wb-list-search">' + ICON.search +
              '<input type="search" id="wbl-search" placeholder="' + esc(t(opt, "wblSearch")) + '" value="' + esc(state.q) + '"></label>' +
            sortSelectHtml(l) +
            (selectable ? '<span class="wb-list-count">' + esc(t(opt, "wblSelected")) + ': <b id="wbl-selcount">' + Object.keys(state.selected).length + "</b></span>" : "") +
            '<span class="wb-list-count">' + total + " " + esc(t(opt, "wblItems")) + "</span>" +
          "</div>";

        var listHtml;
        if (opt.rowRender && pageRows.length) {
          listHtml = renderCards(pageRows, l);          // 决策 C：卡片列表布局
        } else if (total === 0) {
          listHtml = '<div class="wb-list-empty">' + esc(t(opt, "wblEmpty")) + "</div>";
        } else {
          listHtml = '<table class="wb-list-table"><thead><tr>' + headHtml + "</tr></thead><tbody>" + bodyHtml + "</tbody></table>";
        }

        mount.innerHTML = '<div class="wb-list">' + barHtml + listHtml + pagerHtml(totalPages, total) + "</div>";

        bind();
        if (state._keepSearchFocus) {                 // 检索输入重建后保持焦点与光标
          var inp = document.getElementById("wbl-search");
          if (inp) { inp.focus(); var v = inp.value; inp.value = ""; inp.value = v; }
          state._keepSearchFocus = false;
        }
      }

      function actionsHtml(rid) {
        var h = "";
        if (opt.onEdit) h += '<button class="wb-list-act" data-act="edit" data-rid="' + esc(rid) + '" title="edit">' + ICON.edit + "</button>";
        if (opt.onDelete) h += '<button class="wb-list-act danger" data-act="del" data-rid="' + esc(rid) + '" title="delete">' + ICON.del + "</button>";
        return h;
      }
      function sortSelectHtml(l) {
        if (!columns.some(function (c) { return c.sortable; })) return "";
        var opts = '<option value="">' + esc(t(opt, "wblSort")) + "</option>" +
          columns.filter(function (c) { return c.sortable; }).map(function (c) {
            var label = (c.label && (c.label[l] || c.label.zh)) || c.key;
            var v = c.key;
            var sel = state.sortKey === v ? " selected" : "";
            return '<option value="' + esc(v) + '"' + sel + ">" + esc(label) + "</option>";
          }).join("");
        return '<select class="wb-list-sort" id="wbl-sort">' + opts + "</select>";
      }
      // 卡片行模板模式（决策 C）：rowRender 返回卡片内部 HTML，选择框/操作按钮由组件叠加
      function renderCards(pageRows, l) {
        var cards = pageRows.map(function (r) {
          var rid = ridOf(r);
          var inner = opt.rowRender ? opt.rowRender(r, l) : "";
          var sel = selectable ? '<label class="wb-list-selwrap"><input type="checkbox" class="wb-list-sel" data-rid="' + esc(rid) + '"' + (state.selected[rid] ? " checked" : "") + "></label>" : "";
          var acts = hasActions() ? '<div class="wb-list-cardacts">' + actionsHtml(rid) + "</div>" : "";
          return '<article class="wb-list-rowcard' + (state.selected[rid] ? " sel" : "") + '" data-rid="' + esc(rid) + '">' + sel +
            '<div class="wb-list-cardbody">' + inner + "</div>" + acts + "</article>";
        }).join("");
        return '<div class="wb-list-cards">' + cards + "</div>";
      }
      function pagerHtml(totalPages, total) {
        if (total === 0) return "";
        var p = state.page;
        var prev = '<button class="wb-list-pagebtn" data-page="prev"' + (p <= 1 ? " disabled" : "") + ">" + esc(t(opt, "wblPrev")) + "</button>";
        var next = '<button class="wb-list-pagebtn" data-page="next"' + (p >= totalPages ? " disabled" : "") + ">" + esc(t(opt, "wblNext")) + "</button>";
        var nums = "";
        var lo = Math.max(1, p - 2), hi = Math.min(totalPages, p + 2);
        for (var i = lo; i <= hi; i++) {
          nums += '<button class="wb-list-pagebtn' + (i === p ? " cur" : "") + '" data-page="' + i + '">' + i + "</button>";
        }
        return '<div class="wb-list-foot"><div class="wb-list-pager">' + prev + nums + next +
          '</div><span class="wb-list-info">' + p + " / " + totalPages + " " + esc(t(opt, "wblPage")) + "</span></div>";
      }

      // ---------- 事件绑定（每次 render 后执行；铁律 10.6） ----------
      function bind() {
        var search = document.getElementById("wbl-search");
        if (search) search.addEventListener("input", function () {
          state._keepSearchFocus = true; state.q = search.value; apply();
        });
        var sort = document.getElementById("wbl-sort");
        if (sort) sort.addEventListener("change", function () {
          state.sortKey = sort.value || null; state.sortDir = 1; state.page = 1; apply();
        });
        mount.querySelectorAll("th.sortable").forEach(function (th) {
          th.addEventListener("click", function () {
            var k = th.getAttribute("data-sort");
            if (state.sortKey === k) state.sortDir = -state.sortDir; else { state.sortKey = k; state.sortDir = 1; }
            state.page = 1; apply();
          });
        });
        mount.querySelectorAll(".wb-list-pagebtn").forEach(function (b) {
          b.addEventListener("click", function () {
            var v = b.getAttribute("data-page");
            if (v === "prev") state.page = Math.max(1, state.page - 1);
            else if (v === "next") state.page = Math.min(Math.ceil(state.filtered.length / pageSize), state.page + 1);
            else state.page = parseInt(v, 10);
            render();
          });
        });
        mount.querySelectorAll(".wb-list-act").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var rid = btn.getAttribute("data-rid");
            var row = rowByRid(rid);
            if (btn.getAttribute("data-act") === "edit" && opt.onEdit) opt.onEdit(row);
            if (btn.getAttribute("data-act") === "del") {
              if (window.confirm(t(opt, "wblConfirmDel")) && opt.onDelete) opt.onDelete(row);
            }
          });
        });
        if (selectable) mount.querySelectorAll(".wb-list-sel").forEach(function (cb) {
          cb.addEventListener("change", function () {
            var rid = cb.getAttribute("data-rid");
            if (cb.checked) state.selected[rid] = true; else delete state.selected[rid];
            var cnt = document.getElementById("wbl-selcount");
            if (cnt) cnt.textContent = Object.keys(state.selected).length;
            if (opt.onSelect) opt.onSelect(Object.keys(state.selected));
          });
        });
      }
      function rowByRid(rid) {
        if (opt.rowId) return state.all.filter(function (r) { return String(r[rowId]) === String(rid); })[0];
        return state.all[parseInt(rid, 10)];
      }

      // 立即加载并首渲染
      load();

      return {
        refresh: load,                 // 重新拉数据
        rerender: render,              // 仅重建文案（如切语言），不重新拉数据
        getSelected: function () { return Object.keys(state.selected); }
      };
    }
  };

  window.WBList = WBList;
})();
