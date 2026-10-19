#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 hitch-all.json 生成一个可浏览的单页 HTML
==========================================
  python make_html.py            # -> 顺风车车源.html

依赖同目录的 model-meta.json（官方车型分类表，model_meta.py 生成）。
"""

import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "hitch-all.json")
META = os.path.join(HERE, "model-meta.json")
OUT = os.path.join(HERE, "顺风车车源.html")

import sys                                                   # noqa: E402
sys.path.insert(0, HERE)
from car_class import classify, by_name_index, meta_for       # noqa: E402
from car_rank import score as rank_of                          # noqa: E402


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    items = d.get("items") or []
    try:
        meta = json.load(open(META, encoding="utf-8"))
    except Exception:
        meta = {}
    by_name = by_name_index(meta)

    rows = []
    for i in items:
        m = meta_for(i.get("modelId"), i.get("modelName"), meta, by_name)
        name = i.get("modelName") or ""
        rows.append({
            "id": str(i.get("hitchId")),
            "model": name,
            "cls": classify(name, m.get("energy"), m.get("body")),
            "rank": rank_of(name, m.get("body") or ""),
            "body": m.get("body") or "",
            "seats": m.get("seats") or "",
            "energy": m.get("energy") or "",
            "price": str(i.get("realTotalPrice") or ""),
            "from": i.get("pickupCityName") or "",
            "to": i.get("returnCityName") or "",
            "bd": i.get("beginDate") or "",
            "ed": i.get("endDate") or "",
            "days": i.get("limitTenancyDay") or "",
            "pic": i.get("modelPic") or "",
        })

    data_js = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>神州顺风车车源 %(cnt)d 条</title>
<style>
  :root{--bd:#e5e7eb;--fg:#111827;--muted:#6b7280;--red:#d92b2b;--bg:#f7f8fa;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
       font:14px/1.5 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
  header{background:#fff;border-bottom:1px solid var(--bd);padding:16px 20px;
         position:sticky;top:0;z-index:5}
  h1{margin:0 0 4px;font-size:18px}
  .sub{color:var(--muted);font-size:12px}
  .bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px}
  select,input,button{font:inherit;padding:6px 10px;border:1px solid var(--bd);
        border-radius:8px;background:#fff;color:var(--fg)}
  #search{width:200px}
  button{cursor:pointer}
  button.on{background:var(--red);color:#fff;border-color:var(--red)}
  .stat{margin-left:auto;color:var(--muted);font-size:12px}
  table{width:100%%;border-collapse:collapse;background:#fff}
  th,td{padding:8px 10px;border-bottom:1px solid var(--bd);text-align:left;
        white-space:nowrap}
  th{position:sticky;top:0;background:#fff;font-size:12px;color:var(--muted);
     cursor:pointer;user-select:none;border-bottom:2px solid var(--bd)}
  tbody tr:hover{background:#fafafa}
  td.p{font-weight:700;color:var(--red)}
  /* 档次配色：车越好颜色越"贵"（金 → 银 → 铜 → 素），整行淡染 + 首列色条 */
  tr.t1{background:#fdf6e3} tr.t1 td:first-child{border-left:4px solid #d4a017}
  tr.t2{background:#f3f6f9} tr.t2 td:first-child{border-left:4px solid #7b8794}
  tr.t3{background:#fbf4ee} tr.t3 td:first-child{border-left:4px solid #c08552}
  tr.t4 td:first-child{border-left:4px solid #e4e8ee}
  .tag{display:inline-block;background:#eef2f7;color:#374151;border-radius:6px;
       padding:1px 7px;font-size:11.5px}
  .tag.en{background:#e8f3ec;color:#14713f}
  .tag.lx{background:#fdf1d6;color:#8a5a00}
  .tag.nv{background:#e8f3ec;color:#14713f}
  .tag.pc{background:#eef2f7;color:#4b5563}
  /* 档次标签：金 / 银 / 铜 / 素 */
  .tag.lv{font-weight:700}
  .tag.lv1{background:#fbf0d2;color:#8a5a00}
  .tag.lv2{background:#e9edf2;color:#42506b}
  .tag.lv3{background:#f7ece2;color:#8a5230}
  .tag.lv4{background:#f0f2f5;color:#6b7280}
  /* 城市筛选：可搜索下拉 */
  .ss{position:relative}
  .ss-btn{display:flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--bd);
          border-radius:8px;background:#fff;color:var(--fg);cursor:pointer;min-width:132px}
  .ss-btn .ss-txt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ss-btn .ss-car{font-size:9px;color:var(--muted);font-style:normal}
  .ss-pop{position:absolute;z-index:30;top:calc(100%% + 6px);left:0;width:250px;background:#fff;
          border:1px solid var(--bd);border-radius:10px;box-shadow:0 10px 30px rgba(17,24,39,.16);padding:8px}
  .ss-pop[hidden]{display:none}
  .ss-q{width:100%%;margin-bottom:6px}
  .ss-list{max-height:300px;overflow:auto}
  .ss-item{padding:7px 9px;border-radius:7px;cursor:pointer;font-size:13.5px}
  .ss-item:hover,.ss-item.on{background:#eef2f7}
  .ss-none{padding:9px;color:var(--muted);font-size:12.5px;text-align:center}
  .wrap{padding:0 0 40px;overflow-x:auto}
  .empty{padding:40px;text-align:center;color:var(--muted)}
</style>
</head>
<body>
<header>
  <h1>神州租车 · 顺风车车源</h1>
  <div class="sub">共 <b id="total"></b> 条 ｜ 抓取于 %(ts)s ｜ 数据来源 m.zuche.com（读取免登录）</div>
  <div class="bar">
    <div class="ss" id="ssFrom"></div>
    <div class="ss" id="ssTo"></div>
    <select id="cls"><option value="">全部类别</option></select>
    <button id="only1">只看 ¥1 捡漏</button>
    <input id="search" placeholder="搜车型，如 GL8">
    <button id="reset">重置</button>
    <span class="stat">显示 <b id="shown">0</b> 条<button id="more" style="margin-left:8px;display:none">加载更多</button></span>
  </div>
</header>
<div class="wrap"><table>
  <thead><tr>
    <th data-k="model">车型</th><th data-k="rank">档次</th><th data-k="cls">类别</th><th data-k="energy">能源</th>
    <th data-k="price">一口价</th>
    <th data-k="from">取车城市</th><th data-k="to">还车城市</th>
    <th data-k="bd">开始</th><th data-k="ed">结束</th>
    <th data-k="days">天数</th><th data-k="id">hitchId</th>
  </tr></thead>
  <tbody id="tb"></tbody>
</table><div class="empty" id="empty" style="display:none">没有符合条件的车源</div></div>
<script>
const DATA = %(data)s;
const PAGE = 200;
let view = DATA.slice(), shown = 0, sortK = null, sortAsc = true;

const $ = s => document.querySelector(s);
$('#total').textContent = DATA.length;

// 车源类别：新能源 / 高端车 / 普通车（后端按 car_class.py 规则算好放在 cls 字段）
const CLSCLS = {'新能源':'nv','高端车':'lx','普通车':'pc'};
function clsTag(c){ return c ? ('<span class="tag '+(CLSCLS[c]||'pc')+'">'+esc(c)+'</span>') : ''; }
// 档次配色：分数 → 1 尊享(金) / 2 高级(银) / 3 中档(铜) / 4 入门(素)
const TIER_NAME = {1:'尊享',2:'高级',3:'中档',4:'入门'};
function tier(r){ r=Number(r)||0; return r>=90?1:(r>=80?2:(r>=70?3:4)); }
function uniq(a){ return [...new Set(a.filter(Boolean))].sort((x,y)=>x.localeCompare(y,'zh')); }
function fill(sel, label, vals){
  for (const c of vals){ const o=document.createElement('option'); o.value=c; o.textContent=c; sel.appendChild(o); }
}
// 可搜索下拉：城市有几十个，原生 select 找起来费劲 → 打开就能搜
function makeSearchSelect(root, allLabel, onChange){
  let val='', open=false, opts=[allLabel];
  const btn=document.createElement('button');
  btn.type='button'; btn.className='ss-btn';
  const txt=document.createElement('span'); txt.className='ss-txt'; txt.textContent=allLabel;
  const car=document.createElement('i'); car.className='ss-car'; car.textContent='▼';
  btn.appendChild(txt); btn.appendChild(car);
  const pop=document.createElement('div'); pop.className='ss-pop'; pop.hidden=true;
  const q=document.createElement('input'); q.className='ss-q'; q.type='search';
  q.placeholder='输入城市名筛选…'; q.autocomplete='off';
  const list=document.createElement('div'); list.className='ss-list';
  pop.appendChild(q); pop.appendChild(list);
  root.appendChild(btn); root.appendChild(pop);

  function draw(kw){
    const k=(kw||'').trim().toLowerCase();
    const arr=opts.filter(c=>!k||c.toLowerCase().includes(k));
    list.innerHTML='';
    if(!arr.length){ list.innerHTML='<div class="ss-none">没有匹配的城市</div>'; return; }
    for(const c of arr){
      const it=document.createElement('div');
      it.className='ss-item'+((c===allLabel?'':c)===val?' on':'');
      it.textContent=c;
      it.onclick=()=>{ set(c===allLabel?'':c); close(); };
      list.appendChild(it);
    }
  }
  function set(v, fire){ val=v||''; txt.textContent=val||allLabel; if(fire!==false) onChange(val); }
  function openPop(){
    open=true; pop.hidden=false;
    const r=root.getBoundingClientRect();
    if(r.left+260>window.innerWidth){ pop.style.left='auto'; pop.style.right='0'; }
    else { pop.style.left='0'; pop.style.right='auto'; }
    q.value=''; draw(''); q.focus();
  }
  function close(){ open=false; pop.hidden=true; }
  btn.onclick=e=>{ e.stopPropagation(); if(open) close(); else openPop(); };
  q.oninput=()=>draw(q.value);
  q.onkeydown=e=>{
    if(e.key==='Enter'){ e.preventDefault(); const f=list.querySelector('.ss-item'); if(f) f.click(); }
    else if(e.key==='Escape'){ close(); }
  };
  document.addEventListener('click', e=>{ if(open && !root.contains(e.target)) close(); });
  return {
    get value(){ return val; },
    set(v){ set(v, false); },
    setOptions(vals){ opts=[allLabel].concat(vals||[]); if(val && !(vals||[]).includes(val)) set('', false); draw(q.value); },
  };
}
const ssFrom = makeSearchSelect($('#ssFrom'), '全部取车城市', ()=>apply());
const ssTo   = makeSearchSelect($('#ssTo'),   '全部还车城市', ()=>apply());
ssFrom.setOptions(uniq(DATA.map(d=>d.from)));
ssTo.setOptions(uniq(DATA.map(d=>d.to)));
// 类别（新能源/高端车/普通车）按条数从多到少排
const ccnt = {};
DATA.forEach(d=>{ if(d.cls) ccnt[d.cls]=(ccnt[d.cls]||0)+1; });
fill($('#cls'), '', Object.keys(ccnt).sort((a,b)=>ccnt[b]-ccnt[a]));

function apply(){
  const cf = ssFrom.value, ct = ssTo.value, cl = $('#cls').value,
        t = $('#search').value.trim().toLowerCase(), only1 = $('#only1').classList.contains('on');
  view = DATA.filter(d=>{
    if (cf && d.from !== cf) return false;
    if (ct && d.to !== ct) return false;
    if (cl && d.cls !== cl) return false;
    if (only1 && d.price !== '1') return false;
    if (t && !((d.model+' '+(d.cls||'')+' '+(d.body||'')).toLowerCase().includes(t))) return false;
    return true;
  });
  if (sortK){
    view.sort((a,b)=>{
      let x=a[sortK], y=b[sortK];
      if (sortK==='price'||sortK==='days'||sortK==='id'||sortK==='rank'){ x=Number(x)||0; y=Number(y)||0;
        return sortAsc? x-y : y-x; }
      return sortAsc ? String(x).localeCompare(String(y),'zh') : String(y).localeCompare(String(x),'zh');
    });
  } else {
    // 默认：同类别内按档次分降序（越好的车越靠前）
    view.sort((a,b)=>(b.rank||0)-(a.rank||0));
  }
  shown = 0; $('#tb').innerHTML=''; render();
}
function render(){
  const tb = $('#tb'), frag = document.createDocumentFragment();
  const part = view.slice(shown, shown+PAGE);
  for (const d of part){
    const tr = document.createElement('tr');
    const t = tier(d.rank);
    tr.className = 't'+t;
    const bd  = d.body ? ('<span class="tag">'+esc(d.body)+(d.seats?' '+esc(d.seats):'')+'</span>') : '';
    const en  = d.energy ? ('<span class="tag en">'+esc(d.energy)+'</span>') : '';
    const lv  = '<span class="tag lv lv'+t+'">'+TIER_NAME[t]+'</span>';
    tr.innerHTML = '<td>'+esc(d.model)+'</td><td>'+lv+'</td><td>'+clsTag(d.cls)+bd+'</td><td>'+en+
      '</td><td class="p">¥'+esc(d.price)+'</td><td>'+
      esc(d.from)+'</td><td>'+esc(d.to)+'</td><td>'+esc(d.bd)+'</td><td>'+esc(d.ed)+
      '</td><td>'+esc(d.days)+'</td><td>'+esc(d.id)+'</td>';
    frag.appendChild(tr);
  }
  tb.appendChild(frag);
  shown += part.length;
  $('#shown').textContent = shown;
  $('#more').style.display = shown < view.length ? 'inline-block' : 'none';
  $('#empty').style.display = view.length ? 'none' : 'block';
}
function esc(s){ return String(s).replace(/[&<>"]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])); }

document.querySelectorAll('th').forEach(th=>th.onclick=()=>{
  const k = th.dataset.k;
  if (sortK === k) sortAsc = !sortAsc; else { sortK = k; sortAsc = true; }
  apply();
});
$('#cls').onchange = apply;
$('#search').oninput = apply;
$('#only1').onclick = e => { e.target.classList.toggle('on'); apply(); };
$('#reset').onclick = () => { ssFrom.set(''); ssTo.set(''); $('#cls').value='';
  $('#search').value=''; $('#only1').classList.remove('on'); sortK=null; sortAsc=true; apply(); };
$('#more').onclick = render;
apply();
</script>
</body>
</html>
""" % {"data": data_js, "ts": ts, "cnt": len(rows)}

    open(OUT, "w", encoding="utf-8").write(html)
    print("生成 %s（%d 条，%.0f KB）" % (OUT, len(rows), os.path.getsize(OUT) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
