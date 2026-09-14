"""Science-KOL 面板的 filter + 四层卡片渲染（对齐 War-KOL 2026-09-07 规格）。

被 build_dashboard.py 引入。分离出来的原因：这部分含大段 JS/CSS，
混在主文件里会让 f-string 的花括号转义变得极易出错。

交互模型（与 War-KOL 一致）：
  两排 filter button（时间档 / 门类）可叠加 → 卡片网格动态过滤
  → 点卡片展开四层：L1 一句话 / L2 总结 / L3 原文翻译 / L4 出处元信息
"""
from __future__ import annotations

FILTER_CSS = """
/* ── filter 按钮栏（时间档 + 门类，可叠加）── */
.fbar{margin:10px 0 4px}
.frow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:5px 0}
.flab{font-size:11.5px;color:#8a929c;width:42px;flex:none}
.fbtn{font-size:12px;color:#4a545f;background:#fff;border:1px solid #dfe3e8;
 border-radius:3px;padding:3px 11px;cursor:pointer;font-family:inherit;
 transition:all .12s}
.fbtn:hover{border-color:#9aa8b5}
.fbtn.on{background:#3b4754;border-color:#3b4754;color:#fff}
.fbtn i{font-style:normal;margin-left:5px;opacity:.62;font-size:11px}
.fstat{font-size:11.5px;color:#8a929c;margin:6px 0 2px}
.fstat b{color:#3b4754;font-weight:600}
.fsum{margin:4px 0 8px}
.fsum summary{font-size:11.5px;color:#6a7480;cursor:pointer}
.fsum .sline{font-size:11.5px;color:#6a7480;padding:3px 0 2px;line-height:1.7}

/* ── 卡片网格 ── */
.cgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(295px,1fr));
 gap:9px;margin-top:8px}
.ccard{border:1px solid #e6e9ec;border-top:2px solid #9aa8b5;border-radius:3px;
 background:#fff;padding:9px 11px 10px;display:flex;flex-direction:column}
.ccard.hide{display:none}
.cc-top{display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap}
.cc-tag{font-size:10.5px;color:#fff;padding:1px 6px;border-radius:2px}
.cc-date{font-size:11px;color:#8a929c;margin-left:auto}
.cc-who{font-size:11.5px;color:#4a545f;margin-bottom:2px}
.cc-title{font-size:13px;color:#1b1e23;line-height:1.5;margin:2px 0 5px;
 font-weight:500}
.cc-lead{font-size:12px;color:#5a636d;line-height:1.65;margin-bottom:6px}
.cc-src{font-size:11px;color:#96a0aa}
.cc-open{font-size:11.5px;color:#3b6ea5;background:none;border:1px solid #dfe3e8;
 border-radius:3px;padding:3px 10px;cursor:pointer;font-family:inherit;
 margin-top:auto;align-self:flex-start}
.cc-open:hover{border-color:#3b6ea5;background:#f4f8fc}
.cc-body{display:none;margin-top:8px;border-top:1px solid #eef1f4;padding-top:7px}
.cc-body.on{display:block}

/* ── 四层（L1 一句话 / L2 总结 / L3 原文翻译 / L4 出处）── */
.ly-one{font-size:12.5px;color:#2d3640;line-height:1.7;background:#f6f8fa;
 border-left:2px solid #9aa8b5;padding:7px 10px;margin-bottom:7px}
.ly-sec{margin:4px 0}
.ly-btn{width:100%;text-align:left;font-size:12px;color:#4a545f;background:none;
 border:none;border-bottom:1px dotted #e2e6ea;padding:5px 0;cursor:pointer;
 font-family:inherit;display:flex;align-items:center}
.ly-btn:hover{color:#1b1e23}
.ly-ar{display:inline-block;width:13px;color:#9aa8b5;transition:transform .13s}
.ly-btn.on .ly-ar{transform:rotate(90deg)}
.ly-n{margin-left:auto;font-size:10.5px;color:#96a0aa}
.ly-pend{color:#b08a5a}
.ly-wrap{display:none;padding:6px 0 8px 13px}
.ly-wrap.on{display:block}
.ly-sum,.ly-trans{font-size:12.5px;color:#3b444f;line-height:1.8}
.ly-trans p{margin:0 0 8px}
.ly-missing{font-size:11.5px;color:#8a929c;line-height:1.6;background:#fafbfc;
 border:1px dashed #e2e6ea;border-radius:3px;padding:7px 10px}
.ly-meta{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;font-size:11.5px}
.ly-meta>div{display:flex;gap:6px}
.ly-meta b{color:#8a929c;font-weight:500;width:52px;flex:none}
.ly-meta span{color:#3b444f;word-break:break-word}
.ly-meta .wide{grid-column:1/-1}
@media(max-width:700px){.ly-meta{grid-template-columns:1fr}}
.ly-en{font-size:12px;color:#6d757e;line-height:1.7;background:#fafbfc;
 border:1px solid #eef1f4;border-radius:3px;padding:8px 10px}
"""

FILTER_JS = """
/* ── filter：时间档 × 门类，可叠加。纯前端，无依赖 ── */
(function () {
  function pass(card, period, field) {
    if (field !== 'all' && card.dataset.field !== field) return false;
    if (period === 'all') return true;
    var d = card.dataset.date;
    if (!d) return false;              /* 无发表日者不进任何时间档 */
    return d >= window.__SK_CUT[period];
  }
  function apply(scope) {
    var box = document.querySelector('[data-scope="' + scope + '"]');
    if (!box) return;
    var period = box.dataset.period || 'all';
    var field = box.dataset.field || 'all';
    var cards = box.querySelectorAll('.ccard');
    var n = 0;
    cards.forEach(function (c) {
      var ok = pass(c, period, field);
      c.classList.toggle('hide', !ok);
      if (ok) n++;
    });
    var out = box.querySelector('.fstat b');
    if (out) out.textContent = n;
    var empty = box.querySelector('.fempty');
    if (empty) empty.style.display = n ? 'none' : 'block';
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.fbtn');
    if (b) {
      var box = b.closest('[data-scope]');
      var kind = b.dataset.kind;
      box.dataset[kind] = b.dataset.val;
      box.querySelectorAll('.fbtn[data-kind="' + kind + '"]')
         .forEach(function (x) { x.classList.toggle('on', x === b); });
      apply(box.dataset.scope);
      return;
    }
    var op = e.target.closest('.cc-open');
    if (op) {
      var body = op.parentElement.querySelector('.cc-body');
      var on = body.classList.toggle('on');
      op.textContent = on ? '收起 ▴' : '展开四层 ▾';
      return;
    }
    var ly = e.target.closest('.ly-btn');
    if (ly) {
      var w = document.getElementById('ly-' + ly.dataset.ly);
      if (w) { w.classList.toggle('on'); ly.classList.toggle('on'); }
    }
  });
  window.__skApplyAll = function () {
    document.querySelectorAll('[data-scope]').forEach(function (b) {
      apply(b.dataset.scope);
    });
  };
  document.addEventListener('DOMContentLoaded', window.__skApplyAll);
})();
"""


# ── filter + 四层卡片渲染（对齐 War-KOL 规格）────────────────────
FIELD_COLOR_FB = "#8a929c"


def _ly_sec(uid: str, key: str, label: str, content: str,
            missing: str, esc, n_hint: str = "") -> str:
    """一个可折叠层。内容缺失时如实说明，绝不用别层内容顶替。"""
    has = bool((content or "").strip())
    tag = (f"<span class='ly-n'>{n_hint}</span>" if has and n_hint
           else ("" if has else "<span class='ly-n ly-pend'>未生成</span>"))
    inner = (f"<div class='ly-sum'>{esc(content)}</div>" if has
             else f"<div class='ly-missing'>{esc(missing)}</div>")
    return (f"<div class='ly-sec'>"
            f"<button type='button' class='ly-btn' data-ly='{uid}-{key}'>"
            f"<span class='ly-ar'>&#9656;</span>{label}{tag}</button>"
            f"<div class='ly-wrap' id='ly-{uid}-{key}'>{inner}</div></div>")


def four_layer_body(r: dict, uid: str, esc, meta_rows: list) -> str:
    """四层钻取体：L1 一句话 / L2 总结 / L3 原文翻译 / L4 出处元信息。"""
    h = ""
    lead = (r.get("l1_lead") or "").strip()
    if lead:
        h += f"<div class='ly-one'>{esc(lead)}</div>"

    l2 = (r.get("l2_summary") or "").strip()
    h += _ly_sec(uid, "s", "总结", l2,
                 "该条尚未生成总结（四层生成任务未覆盖到）。如实标注，不用摘要冒充。",
                 esc, f"{len(l2)} 字" if l2 else "")

    l3 = (r.get("l3_translation") or "").strip()
    st = r.get("l3_status") or ""
    if l3:
        body = "".join(f"<p>{esc(p)}</p>" for p in l3.split("\n\n") if p.strip())
        h += (f"<div class='ly-sec'>"
              f"<button type='button' class='ly-btn' data-ly='{uid}-t'>"
              f"<span class='ly-ar'>&#9656;</span>原文翻译"
              f"<span class='ly-n'>{len(l3)} 字</span></button>"
              f"<div class='ly-wrap' id='ly-{uid}-t'>"
              f"<div class='ly-trans'>{body}</div></div></div>")
    else:
        why = {"abstract_only": "该来源只提供摘要、没有可取的全文，因此没有全文译文。"
                                "上一层的总结即基于该摘要。",
               "translate_failed": "全文已取到但翻译失败，下轮重试。",
               }.get(st, "该条正文不可得（付费墙 / 403 / 正文过短）。"
                         "绝不用摘要冒充译文——可直接看下一层的原始出处。")
        h += (f"<div class='ly-sec'>"
              f"<button type='button' class='ly-btn' data-ly='{uid}-t'>"
              f"<span class='ly-ar'>&#9656;</span>原文翻译"
              f"<span class='ly-n ly-pend'>仅有摘要</span></button>"
              f"<div class='ly-wrap' id='ly-{uid}-t'>"
              f"<div class='ly-missing'>{esc(why)}</div></div></div>")

    cells = "".join(
        f"<div{' class=&quot;wide&quot;' if wide else ''}>"
        f"<b>{esc(k)}</b><span>{v}</span></div>"
        for k, v, wide in meta_rows)
    h += (f"<div class='ly-sec'>"
          f"<button type='button' class='ly-btn' data-ly='{uid}-o'>"
          f"<span class='ly-ar'>&#9656;</span>出处与元信息</button>"
          f"<div class='ly-wrap' id='ly-{uid}-o'>"
          f"<div class='ly-meta'>{cells}</div></div></div>")
    return h


def filter_bar(scope: str, fields: list, counts: dict, stat_html: str) -> str:
    """两排 filter button：时间档 + 门类。"""
    per = [("all", "全部"), ("day", "本日"), ("week", "本周"),
           ("month", "本月"), ("year", "本年")]
    pb = "".join(
        f"<button type='button' class='fbtn{' on' if k == 'all' else ''}' "
        f"data-kind='period' data-val='{k}'>{lab}</button>" for k, lab in per)
    fb = ("<button type='button' class='fbtn on' data-kind='field' "
          "data-val='all'>全部</button>")
    for f in fields:
        n = counts.get(f, 0)
        if not n:
            continue
        fb += (f"<button type='button' class='fbtn' data-kind='field' "
               f"data-val='{f}'>{f}<i>{n}</i></button>")
    # ★ 不在此闭合 </div>：卡片网格必须在 data-scope 容器【内部】，
    #   否则 JS 里 box.querySelectorAll('.ccard') 找不到卡片
    #   （2026-09-14 实测：点筛选按钮统计归零但卡片全显示）。
    return (f"<div class='fbar' data-scope='{scope}' data-period='all' "
            f"data-field='all'>"
            f"<div class='frow'><span class='flab'>时间</span>{pb}</div>"
            f"<div class='frow'><span class='flab'>门类</span>{fb}</div>"
            f"{stat_html}")
