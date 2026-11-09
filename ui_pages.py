"""LoLStat interface: the app window and the in-game overlay (served locally, shown in WebView2)."""

BASE_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&display=swap');
:root{
  --ink:#0c1220; --panel:#131b2e; --raised:#1a2440; --line:#26314d; --line2:#33405f;
  --text:#ece6d6; --muted:#8e96ab; --dim:#5f6880;
  --gold:#d9b871; --gold2:#f1d595; --teal:#19c8b4; --red:#ff5d6c;
  --gS1:#f6d27a; --gS:#ff9a3c; --gA:#3ad08f; --gB:#4aa3ff; --gC:#8e96ab; --gD:#ff5d6c;
  --tSilver:#c3cbd6; --tGold:#e7c35f; --tPrismatic:#c98cff;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--ink);color:var(--text);
  font:14px/1.45 'Sora','Segoe UI',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;cursor:pointer;border:0;background:none}
input{font:inherit;color:var(--text)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px;border-radius:6px}
img{display:block}
.grade{display:inline-grid;place-items:center;min-width:30px;height:24px;padding:0 7px;border-radius:7px;
  font-weight:800;font-size:12.5px;color:#0c1220;background:var(--gC)}
.g-Sp{background:linear-gradient(135deg,#fff1b8,var(--gS1) 45%,#e0a43a);box-shadow:0 0 14px rgba(246,210,122,.45)}
.g-S{background:var(--gS)} .g-A{background:var(--gA)} .g-B{background:var(--gB)}
.g-C{background:var(--gC)} .g-D{background:var(--gD)} .g-none{background:var(--line2);color:var(--muted)}
.tier-Silver{--tier:var(--tSilver)} .tier-Gold{--tier:var(--tGold)} .tier-Prismatic{--tier:var(--tPrismatic)}
.ico{border-radius:8px;background:var(--raised);object-fit:cover}
.muted{color:var(--muted)}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:10px;border:2px solid var(--ink)}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}
"""

COMMON_JS = r"""
const KEY = new URLSearchParams(location.search).get('key') || '';
const q = (s, el=document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = v => (v == null ? '' : (v * 100).toFixed(1) + '%');
const gcls = g => g === 'S+' ? 'g-Sp' : g ? 'g-' + g : 'g-none';
const grade = g => `<span class="grade ${gcls(g)}">${esc(g || '–')}</span>`;
const img = (src, cls, size) => src ? `<img class="${cls}" src="${esc(src)}" width="${size}" height="${size}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">` : `<span class="${cls}" style="display:block;width:${size}px;height:${size}px"></span>`;
async function api(path, body) {
  const url = path + (path.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(KEY);
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 5000);   // never hang the live refresh
  try {
    const r = await fetch(url, Object.assign({cache:'no-store', signal:ctl.signal}, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {}));
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}
const act = (action, extra={}) => api('/api/action', Object.assign({action}, extra)).then(render).catch(()=>{});
"""

APP_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LoLStat</title>
<style>
""" + BASE_CSS + r"""
body{display:grid;grid-template-columns:76px 1fr;grid-template-rows:100vh;overflow:hidden}
/* rail */
.rail{background:var(--rail,#0a0f1b);border-right:1px solid var(--line);display:flex;flex-direction:column;align-items:center;padding:14px 0;gap:6px}
.rail .logo{margin-bottom:14px}
.nav{width:52px;height:52px;border-radius:14px;display:grid;place-items:center;color:var(--dim);position:relative}
.nav:hover{color:var(--text);background:var(--panel)}
.nav.on{color:var(--gold);background:var(--panel)}
.nav.on::before{content:"";position:absolute;left:-12px;top:12px;bottom:12px;width:3px;border-radius:3px;background:var(--gold)}
.nav svg{width:24px;height:24px}
.nav .tip{position:absolute;left:62px;white-space:nowrap;background:var(--raised);border:1px solid var(--line);
  padding:4px 9px;border-radius:7px;font-size:12px;color:var(--text);opacity:0;pointer-events:none;transition:opacity .12s}
.nav:hover .tip{opacity:1}
.rail .spacer{flex:1}
.livedot{width:10px;height:10px;border-radius:50%;background:var(--dim)}
.livedot.on{background:var(--teal);box-shadow:0 0 0 4px rgba(25,200,180,.15)}
/* main */
main{overflow:auto;padding:0 28px 28px}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:14px;padding:18px 0 14px;background:linear-gradient(var(--ink) 75%,transparent)}
.top h1{margin:0;font-size:22px;font-weight:700;letter-spacing:-.01em}
.pill{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;background:var(--panel);border:1px solid var(--line);font-size:12.5px;color:var(--muted)}
.pill.live{color:var(--teal);border-color:rgba(25,200,180,.35)}
.top .grow{flex:1}
.page{display:none}.page.on{display:block}
.box{background:var(--panel);border:1px solid var(--line);border-radius:var(--r,14px);padding:18px}
.box h2{margin:0 0 12px;font-size:15px;font-weight:600}
.row{display:flex;gap:16px}
.btn{padding:9px 14px;border-radius:10px;background:var(--raised);border:1px solid var(--line2);font-weight:600;font-size:13px}
.btn:hover{border-color:var(--gold)}
.btn.gold{background:var(--gold);color:#1a1405;border-color:var(--gold)}
/* switch */
.switch{width:52px;height:30px;border-radius:30px;background:var(--line2);position:relative;transition:background .15s;flex:none}
.switch::after{content:"";position:absolute;top:4px;left:4px;width:22px;height:22px;border-radius:50%;background:#fff;transition:transform .15s}
.switch.on{background:var(--teal)}.switch.on::after{transform:translateX(22px)}
/* home */
.hero{display:grid;grid-template-columns:1.4fr 1fr;gap:16px}
.status-big{font-size:34px;font-weight:800;letter-spacing:-.02em;margin:6px 0 4px}
.status-sub{color:var(--muted)}
.accept-row{display:flex;align-items:center;justify-content:space-between;margin-top:22px;padding-top:18px;border-top:1px solid var(--line)}
.stat{font-size:28px;font-weight:700}
.qr{background:#fff;border-radius:10px;padding:8px;width:156px;height:156px}
.qr img{width:100%;height:100%}
.feed{display:flex;flex-direction:column;gap:2px;font-size:13px}
.feed div{display:grid;grid-template-columns:76px 1fr;gap:10px;padding:6px 0;border-bottom:1px solid var(--line)}
.feed div:last-child{border:0}.feed time{color:var(--dim)}
.homegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:16px}
/* mayhem */
.matchup{display:flex;align-items:center;gap:22px}
.me{display:flex;align-items:center;gap:14px}
.me img{width:84px;height:84px;border-radius:18px;border:2px solid var(--gold)}
.me .nm{font-size:24px;font-weight:700}
.vs{color:var(--dim);font-weight:700}
.enemies{display:flex;gap:10px}
.enemy{text-align:center;width:66px}
.enemy img{width:56px;height:56px;border-radius:14px;margin:0 auto 5px;border:1px solid var(--line2)}
.enemy span{font-size:11.5px;color:var(--muted);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.notes{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.note{font-size:12px;color:var(--muted);background:var(--raised);border:1px solid var(--line);padding:4px 9px;border-radius:7px}
.plan{display:grid;grid-template-columns:1.2fr repeat(5,1fr);gap:8px;margin-top:14px}
.plan input{width:100%;background:var(--raised);border:1px solid var(--line2);border-radius:9px;padding:9px 10px}
.plan label{font-size:11.5px;color:var(--muted);display:block;margin-bottom:4px}
/* offer: the moment */
.offer{margin-top:16px;border-radius:calc(var(--r,14px) + 2px);padding:18px;background:radial-gradient(120% 140% at 50% 0%,var(--hi,#1d2a4d) 0%,var(--panel) 60%);border:1px solid var(--line2)}
.offer.idle{background:var(--panel);border-style:dashed}
.offer h2{display:flex;align-items:center;gap:10px}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.card{position:relative;border-radius:var(--r,14px);padding:16px;background:var(--raised);border:1px solid var(--line2);overflow:hidden;text-align:left}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:var(--tier,var(--line2))}
.card.best{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold),0 12px 30px rgba(217,184,113,.15)}
.card .big{position:absolute;right:12px;top:8px;font-size:64px;font-weight:800;line-height:1;opacity:.95;letter-spacing:-.04em}
.card .big.g-Sp{background:none;box-shadow:none;color:var(--gS1);text-shadow:0 0 24px rgba(246,210,122,.5)}
.card .big.g-S{background:none;color:var(--gS)} .card .big.g-A{background:none;color:var(--gA)}
.card .big.g-B{background:none;color:var(--gB)} .card .big.g-C{background:none;color:var(--gC)}
.card .big.g-D{background:none;color:var(--gD)} .card .big.g-none{background:none;color:var(--dim)}
.card .cimg{width:58px;height:58px;border-radius:12px;background:var(--iconbg,#1a2440)}
.aug img,.chip img{background:var(--iconbg,#1a2440)}
.card .cn{font-size:17px;font-weight:700;margin:12px 0 4px;padding-right:70px}
.card .ct{font-size:12.5px;color:var(--muted);min-height:54px}
.card .picks{display:flex;gap:14px;margin-top:10px;font-size:12.5px}
.card .picks b{font-size:15px;color:var(--text);display:block}
.card .flag{position:absolute;left:16px;top:-1px;background:var(--gold);color:#1a1405;font-size:11px;font-weight:700;padding:3px 8px;border-radius:0 0 7px 7px}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.cards.fresh .card{animation:rise .35s ease-out both}.cards.fresh .card:nth-child(2){animation-delay:.06s}.cards.fresh .card:nth-child(3){animation-delay:.12s}
button.card:hover{border-color:var(--gold)}
/* lower grid */
.lower{display:grid;grid-template-columns:1.35fr 1fr;gap:16px;margin-top:16px;align-items:start}
.tabs{display:inline-flex;background:var(--ink);border:1px solid var(--line);border-radius:10px;padding:3px;margin-bottom:14px}
.tabs:empty{display:none}
.tabs button{padding:7px 12px;border-radius:8px;font-size:12.5px;font-weight:600;color:var(--muted)}
.tabs button.on{background:var(--raised);color:var(--text)}
.blurb{color:var(--muted);font-size:12.5px;margin:-4px 0 14px}
.items{display:flex;flex-direction:column;gap:10px}
.item{display:grid;grid-template-columns:22px 48px 1fr;gap:12px;align-items:center}
.item .n{color:var(--dim);font-weight:700;text-align:right}
.item img{width:48px;height:48px;border-radius:10px;border:1px solid var(--line2)}
.item.owned img{border-color:var(--teal)}
.item b{font-weight:600;display:block}
.item .why{font-size:12.5px;color:var(--muted)}
.own{color:var(--teal);font-size:11.5px;font-weight:600;margin-left:6px}
.chips{display:flex;flex-wrap:wrap;gap:8px;min-height:36px}
.chip{display:flex;align-items:center;gap:8px;background:var(--raised);border:1px solid var(--line2);border-radius:10px;padding:5px 8px 5px 5px}
.chip img{width:26px;height:26px;border-radius:7px}
.chip .x{color:var(--dim);padding:0 4px}.chip .x:hover{color:var(--red)}
.search{display:flex;gap:8px;margin:14px 0 10px}
.search input{flex:1;background:var(--raised);border:1px solid var(--line2);border-radius:10px;padding:9px 12px}
.seg{display:inline-flex;gap:4px}
.seg button{padding:7px 10px;border-radius:9px;font-size:12px;font-weight:600;color:var(--muted);border:1px solid var(--line)}
.seg button.on{color:#0c1220;background:var(--tier,var(--gold));border-color:transparent}
.auglist{max-height:520px;overflow:auto;margin:0 -6px;padding:0 6px}
.aug{width:100%;display:grid;grid-template-columns:36px 1fr auto 62px;gap:10px;align-items:center;padding:7px 8px;border-radius:10px;text-align:left}
.aug:hover{background:var(--raised)}
.aug img{width:36px;height:36px;border-radius:9px;border:1px solid var(--line)}
.aug .an{font-weight:600;font-size:13px}
.aug .at{font-size:11.5px;color:var(--tier)}
.aug .ap{font-size:12px;color:var(--muted);text-align:right}
.scan{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted)}
.scan i{width:8px;height:8px;border-radius:50%;background:var(--dim)}
.scan.on i{background:var(--teal)}
/* automation */
.auto{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.chk{display:flex;align-items:flex-start;gap:10px;padding:12px;border-radius:12px;background:var(--raised);border:1px solid var(--line);cursor:pointer}
.chk input{appearance:none;width:20px;height:20px;border-radius:6px;border:2px solid var(--line2);flex:none;margin:1px 0 0;display:grid;place-items:center;cursor:pointer}
.chk input:checked{background:var(--teal);border-color:var(--teal)}
.chk input:checked::after{content:"";width:9px;height:5px;border:2.5px solid #06121a;border-top:0;border-right:0;transform:rotate(-45deg) translate(1px,-1px)}
.chk b{display:block;font-size:13.5px}.chk span{font-size:12px;color:var(--muted)}
.spells{display:flex;gap:8px;align-items:center;margin-top:10px;flex-wrap:wrap}
select{background:var(--raised);color:var(--text);border:1px solid var(--line2);border-radius:9px;padding:7px 9px;font:inherit;font-size:13px}
details.act summary{cursor:pointer;list-style:none;display:flex;align-items:center;justify-content:space-between;font-weight:600}
details.act summary::-webkit-details-marker{display:none}
details.act summary::after{content:"Show";font-size:12px;color:var(--muted);font-weight:500}
details.act[open] summary::after{content:"Hide"}
details.act[open] .feed{margin-top:10px}
/* live stats + reader */
.livestats{display:flex;gap:22px;margin-top:14px;flex-wrap:wrap}
.livestats div{font-size:12px;color:var(--muted)}.livestats b{display:block;font-size:20px;color:var(--text)}
.reader{display:grid;grid-template-columns:minmax(0,1.6fr) 1fr;gap:16px;margin-top:16px;align-items:start}
.reader img{width:100%;border-radius:10px;border:1px solid var(--line2);background:var(--ink);min-height:120px}
.slider{display:flex;align-items:center;gap:10px;margin:10px 0}.slider label{width:110px;font-size:12.5px;color:var(--muted)}
input[type=range]{flex:1;accent-color:var(--gold)}
/* pick modal */
.modal{position:fixed;inset:0;z-index:30;background:rgba(5,8,15,.55);backdrop-filter:blur(6px);display:none;place-items:center;padding:24px}
.modal.on{display:grid}
.sheet{width:min(1100px,100%);background:var(--panel);border:1px solid var(--gold);border-radius:calc(var(--r,14px) + 4px);padding:20px;box-shadow:0 30px 80px rgba(0,0,0,.5)}
.sheet .cards .card{cursor:pointer}.sheet .cards .card:hover{border-color:var(--gold);transform:translateY(-2px)}
.sheet .cards .card{transition:transform .12s,border-color .12s}
.pickhint{font-size:12px;color:var(--muted);margin-top:10px}
/* games */
.sum{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px}
.game{display:grid;grid-template-columns:52px 1.1fr .8fr 1.4fr 1fr;gap:16px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line)}
.game:last-child{border:0}
.game img{width:52px;height:52px;border-radius:12px}
.win{color:var(--gA);font-weight:700}.loss{color:var(--gD);font-weight:700}
.split{height:8px;border-radius:8px;overflow:hidden;display:flex;background:var(--line);margin-top:6px}
.split i{display:block;height:100%}
.dmg{font-size:20px;font-weight:700}
/* themes */
.themes{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:10px}
.th{border-radius:12px;padding:10px;border:2px solid var(--line);text-align:left;cursor:pointer}
.th.on{border-color:var(--gold)}
.th .sw{display:flex;gap:4px;margin-top:8px}.th .sw i{width:18px;height:18px;border-radius:5px;display:block}
.creator{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin-top:12px}
.creator label{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12.5px;color:var(--muted);background:var(--raised);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.creator input[type=color]{width:36px;height:26px;border:0;background:none;padding:0;cursor:pointer}
/* scouting */
.scout{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
.side{display:flex;flex-direction:column;gap:8px}
.side h3{margin:0 0 2px;font-size:13px;color:var(--muted);font-weight:600}
.pl{display:grid;grid-template-columns:44px 1fr auto;gap:12px;align-items:center;padding:10px 12px;border-radius:12px;background:var(--panel);border:1px solid var(--line)}
.pl.me{border-color:var(--gold)}
.pl img{width:44px;height:44px;border-radius:10px}
.pl .n{font-weight:600;font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pl .r{font-size:12px;color:var(--muted)}
.pl .t{display:flex;gap:5px;flex-wrap:wrap;margin-top:4px}
.tag{font-size:11px;padding:2px 7px;border-radius:6px;background:var(--raised);border:1px solid var(--line2)}
.tag.good{color:var(--gA);border-color:color-mix(in srgb,var(--gA) 40%,transparent)}
.tag.bad{color:var(--gD);border-color:color-mix(in srgb,var(--gD) 40%,transparent)}
.pl .wr{text-align:right;font-size:12px;color:var(--muted)}.pl .wr b{display:block;font-size:16px;color:var(--text)}
/* runes */
.runes{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.runes img{width:34px;height:34px;border-radius:50%;background:var(--iconbg,#1a2440);padding:2px}
.runes img.ks{width:48px;height:48px}
/* profile */
.ranks{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:14px}
.rk{padding:14px;border-radius:12px;background:var(--raised);border:1px solid var(--line)}
.rk b{display:block;font-size:18px}.rk span{font-size:12px;color:var(--muted)}
.mrow{display:grid;grid-template-columns:44px 1.2fr .9fr .8fr .8fr 1.3fr auto;gap:12px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}
.mrow:last-child{border:0}.mrow img.c{width:44px;height:44px;border-radius:10px}
.mrow .its{display:flex;gap:3px}.mrow .its img{width:24px;height:24px;border-radius:5px;background:var(--raised)}
.mrow.w{box-shadow:inset 3px 0 0 var(--gA)}.mrow.l{box-shadow:inset 3px 0 0 var(--gD)}
.two{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;margin-top:16px;align-items:start}
.ctab{display:grid;grid-template-columns:36px 1fr auto auto auto;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:13px}
.ctab img{width:36px;height:36px;border-radius:8px}
.chero{display:flex;gap:18px;align-items:center}
.chero img{width:96px;height:96px;border-radius:18px;border:2px solid var(--gold)}
@media (max-width:1100px){.scout,.two{grid-template-columns:1fr}.mrow{grid-template-columns:44px 1fr 1fr auto}.mrow .its,.mrow .hide{display:none}}
/* friends + compare */
.fr{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.fr button{font-size:12px;padding:5px 10px;border-radius:999px;border:1px solid var(--line2);background:var(--raised);display:flex;align-items:center;gap:6px}
.fr button:hover{border-color:var(--gold)}
.fr i{width:7px;height:7px;border-radius:50%;background:var(--dim);flex:none}.fr i.on{background:var(--gA)}.fr i.ingame{background:var(--gold)}
.cmp{display:grid;grid-template-columns:1fr 1.2fr 1fr;align-items:center;font-size:14px}
.cmp div{padding:9px 6px;border-bottom:1px solid var(--line)}
.cmp .lab{text-align:center;color:var(--muted);font-size:12.5px}
.cmp .a{text-align:right}.cmp .b{text-align:left}
.cmp .best{color:var(--gA);font-weight:700}
/* champion art background */
#bgart{position:fixed;inset:0;z-index:0;pointer-events:none;background-size:cover;background-position:center 20%;opacity:0;transition:opacity .4s}
#bgart.on{opacity:.42}
#bgart::after{content:"";position:absolute;inset:0;background:linear-gradient(100deg,var(--ink) 8%,color-mix(in srgb,var(--ink) 55%,transparent) 55%,color-mix(in srgb,var(--ink) 80%,transparent))}
.rail,main{position:relative;z-index:1}
.ctpick{display:grid;grid-template-columns:1fr 1.4fr auto;gap:10px;margin-top:10px}
.ctpick label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted)}
.ctpick select{width:100%}
.ctpick label.chk{flex-direction:row;align-items:center;color:var(--text)}
.ctprev{margin-top:10px;height:150px;border-radius:12px;border:1px solid var(--line2);background-size:cover;background-position:center 20%;position:relative;overflow:hidden}
.ctprev .sw{position:absolute;left:12px;bottom:12px;display:flex;gap:5px}.ctprev .sw i{width:22px;height:22px;border-radius:6px;border:1px solid rgba(255,255,255,.25)}
.ctprev b{position:absolute;left:12px;top:10px;font-size:18px;color:#fff;text-shadow:0 2px 8px rgba(0,0,0,.7)}
/* friends */
.hl{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:16px}
.hl .box{display:flex;gap:12px;align-items:center;padding:14px}
.hl img{width:46px;height:46px;border-radius:10px}
.frow{display:grid;grid-template-columns:26px minmax(0,1.6fr) 1.2fr .7fr .7fr .8fr .7fr 44px;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);font-size:13px;cursor:pointer}
.frow:last-child{border:0}.frow:hover{background:color-mix(in srgb,var(--raised) 60%,transparent)}
.frow.me{box-shadow:inset 3px 0 0 var(--gold)}
.frow .n{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.frow .p{font-size:11.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.frow .p.ig{color:var(--gold)}
.frow img{width:40px;height:40px;border-radius:9px}
.frow .pos{color:var(--dim);font-weight:700;text-align:right}
.frow.head{cursor:default;color:var(--muted);font-size:11.5px}.frow.head:hover{background:none}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--dim);margin-right:6px}
.dot.on{background:var(--gA)}.dot.ingame{background:var(--gold)}.dot.away{background:#e7b84a}
@media (max-width:1100px){.frow{grid-template-columns:22px 1.6fr 1fr .8fr 40px}.frow .x{display:none}.ctpick{grid-template-columns:1fr}}
/* champ select */
.cs{margin-top:16px}
.cs-top{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.bench{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.bt{width:86px;text-align:center;padding:8px 6px;border-radius:12px;background:var(--raised);border:1px solid var(--line2)}
.bt:hover{border-color:var(--gold)}
.bt img{width:58px;height:58px;border-radius:12px;margin:0 auto 6px}
.bt span{display:block;font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bt span.grade{display:inline-grid;margin-top:5px;min-width:26px;height:20px;font-size:11px}
.team{display:flex;gap:8px;margin-left:auto}
.team img{width:40px;height:40px;border-radius:10px;border:1px solid var(--line2)}
.lock{display:flex;gap:8px;margin-top:12px}
.lock input{background:var(--raised);border:1px solid var(--line2);border-radius:10px;padding:9px 12px;width:240px}
.cs-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:14px}
.cs-title{font-size:22px;font-weight:700;margin-top:2px}
.cs-sub{font-size:12.5px;color:var(--muted);margin-bottom:8px}
.cs-grid{display:grid;grid-template-columns:auto 1fr;gap:20px;align-items:start}
.ccards{display:flex;gap:12px;flex-wrap:wrap}
.ccard{position:relative;border-radius:var(--r,14px);overflow:hidden;border:2px solid var(--line2);background:#05080f;padding:0;flex:none}
.ccard img{width:100%;height:100%;object-fit:cover;display:block}
.ccard .nm{position:absolute;inset:auto 0 0 0;padding:28px 10px 9px;background:linear-gradient(transparent,rgba(5,8,15,.92));text-align:left;color:#f3eee2}
.ccard .nm b{display:block;font-size:14px;line-height:1.2}.ccard .nm i{font-style:normal;font-size:11px;color:#b9bfcc}
.ccard .cg{position:absolute;top:8px;right:8px}
.ccard .flag{position:absolute;left:10px;top:-1px;background:var(--gold);color:#1a1405;font-size:11px;font-weight:700;padding:3px 8px;border-radius:0 0 7px 7px;z-index:1}
.ccard.pick,.ccard.swap{cursor:pointer;transition:transform .12s,border-color .12s}
.ccard.pick:hover,.ccard.swap:hover{border-color:var(--gold);transform:translateY(-3px)}
.ccard.mine{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold),0 14px 34px rgba(0,0,0,.35)}
.ccard.mate .nm b{font-size:11.5px}.ccard.mate .nm i{display:none}.ccard.mate .cg{display:none}
.ccard.empty{border-style:dashed;background:var(--raised)}
@media (max-width:900px){.cs-grid{grid-template-columns:1fr}}
/* toast */
.toast{position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:20;background:var(--raised);border:1px solid var(--gold);
  color:var(--text);padding:10px 16px;border-radius:12px;font-weight:600;box-shadow:0 12px 30px rgba(0,0,0,.35);display:none}
.toast.on{display:block;animation:rise .3s ease-out}
/* settings */
.set{display:flex;align-items:center;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--line)}
.set:last-child{border:0}
.set p{margin:2px 0 0;color:var(--muted);font-size:12.5px;max-width:560px}
.fine{color:var(--dim);font-size:12px;max-width:760px}
.feed{display:flex;flex-direction:column;gap:2px;font-size:13px}
.feed div{display:grid;grid-template-columns:76px 1fr;gap:10px;padding:6px 0;border-bottom:1px solid var(--line)}
.feed div:last-child{border:0}.feed time{color:var(--dim)}
main>.top,main>.page{max-width:1640px;margin-left:auto;margin-right:auto}
.diag{width:100%;min-height:150px;background:var(--ink);border:1px solid var(--line2);border-radius:10px;color:var(--muted);
  font:12px/1.5 Consolas,'Segoe UI',monospace;padding:10px;margin-top:10px;resize:vertical}
@media (max-width:1100px){.lower,.hero{grid-template-columns:1fr}.homegrid{grid-template-columns:1fr 1fr}
  .plan{grid-template-columns:repeat(3,1fr)}.cards{gap:10px}.card .big{font-size:48px}.card .cn{padding-right:52px}}
@media (max-width:900px){main{padding:0 16px 16px}.homegrid{grid-template-columns:1fr}.cards{grid-template-columns:1fr}
  .matchup{flex-wrap:wrap}.top h1{font-size:19px}}
</style></head>
<body>
<div id="bgart" aria-hidden="true"></div>
<nav class="rail" aria-label="Main">
  <img class="logo" src="/logo.png" width="44" height="44" alt="LoLStat">
  <button class="nav on" data-page="home" aria-label="Home"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/></svg><span class="tip">Home</span></button>
  <button class="nav" data-page="mayhem" aria-label="ARAM Mayhem"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 2l8.5 5v10L12 22l-8.5-5V7z"/><path d="M13 7l-3.5 6H13l-1.5 4.5" stroke-linecap="round"/></svg><span class="tip">Champ select and builds</span></button>
  <button class="nav" data-page="live" aria-label="Live game"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7"/></svg><span class="tip">Live game scouting</span></button>
  <button class="nav" data-page="champs" aria-label="Champions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><span class="tip">Champions</span></button>
  <button class="nav" data-page="profile" aria-label="Profile"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/></svg><span class="tip">Profile</span></button>
  <button class="nav" data-page="friends" aria-label="Friends"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c1-3.5 3.6-5.5 6.5-5.5s5.5 2 6.5 5.5"/><circle cx="17" cy="9" r="2.8"/><path d="M16 14.6c2.6-.3 4.8 1.4 5.6 4.4"/></svg><span class="tip">Friends</span></button>
  <button class="nav" data-page="games" aria-label="Games"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg><span class="tip">Games and damage</span></button>
  <button class="nav" data-page="settings" aria-label="Settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg><span class="tip">Settings</span></button>
  <div class="spacer"></div>
  <span class="livedot" id="railLive" title="League client"></span>
</nav>

<main>
  <div class="toast" id="toast" role="status"></div>
  <div class="modal" id="shareModal" role="dialog" aria-modal="true" aria-labelledby="shareTitle"><div class="sheet" style="max-width:1180px">
    <div style="display:flex;justify-content:space-between;align-items:center"><h2 id="shareTitle" style="margin:0">Share stats</h2><button class="btn" onclick="q('#shareModal').classList.remove('on')">Close</button></div>
    <canvas id="card" width="1100" height="600" style="width:100%;border-radius:12px;margin-top:14px;border:1px solid var(--line2)"></canvas>
    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap"><button class="btn gold" id="copyImg">Copy image</button><button class="btn" id="saveImg">Save image</button><button class="btn" id="copyCode">Copy share code</button>
      <span class="muted" style="font-size:12.5px;align-self:center" id="shareHint"></span></div>
  </div></div>
  <div class="modal" id="pickModal" role="dialog" aria-modal="true" aria-labelledby="pickTitle"><div class="sheet">
    <div style="display:flex;justify-content:space-between;align-items:center"><h2 id="pickTitle" style="margin:0">Augment cards: click the one you're taking</h2><button class="btn" id="pickHide">Hide</button></div>
    <div class="cards" id="pickCards" style="margin-top:14px"></div>
    <div class="pickhint">LoLStat also notices the card you click in game. Picking here just makes sure.</div>
  </div></div>
  <div class="top">
    <h1 id="title">Home</h1>
    <span class="grow"></span>
    <span class="pill" id="clientPill">Waiting for League</span>
    <span class="pill" id="patchPill">Patch</span>
  </div>

  <!-- HOME -->
  <section class="page on" id="p-home">
    <div class="hero">
      <div class="box">
        <div class="muted" id="phaseSmall">League client</div>
        <div class="status-big" id="phaseBig">Open League to start</div>
        <div class="status-sub" id="phaseSub">LoLStat connects as soon as the client is running.</div>
        <div class="accept-row">
          <div><b style="font-size:16px">Auto-accept</b><div class="muted" style="font-size:12.5px">Accepts every match the moment it pops.</div></div>
          <button class="switch" id="acceptSwitch" aria-label="Auto-accept"></button>
        </div>
      </div>
      <div class="box row" style="align-items:center;gap:20px">
        <div class="qr"><img id="qr" alt="Phone remote QR code"></div>
        <div><h2>Phone remote</h2><div class="muted" style="font-size:12.5px">Scan with your phone camera on the same Wi-Fi to accept, decline or switch auto-accept off from the couch.</div></div>
      </div>
    </div>
    <div class="homegrid">
      <div class="box"><div class="muted">Matches accepted</div><div class="stat" id="accCount">0</div><div class="muted" style="font-size:12.5px" id="accLast">None yet this session</div></div>
      <div class="box"><div class="muted">Overlay</div><div class="stat" id="ovState">On</div><div class="muted" style="font-size:12.5px">Shows over League in your games.</div></div>
      <div class="box"><div class="muted">Game data</div><div class="stat" id="dataPatch">–</div><div class="muted" style="font-size:12.5px" id="dataStatus"></div></div>
    </div>
    <div class="box" style="margin-top:16px"><h2>Automation</h2><div class="auto" id="autoBox"></div><div class="spells" id="spellBox"></div></div>
    <div class="box" style="margin-top:16px" id="lastGame"></div>
    <div class="box" style="margin-top:16px"><details class="act" id="actDetails"><summary>Activity</summary><div class="feed" id="feed"></div></details></div>
  </section>

  <!-- MAYHEM -->
  <section class="page" id="p-mayhem">
    <div class="box" id="matchBox">
      <div class="matchup" id="matchup"></div>
      <div class="notes" id="notes"></div>
      <div class="plan" id="plan"></div>
    </div>
    <div class="box cs" id="cs" style="display:none"></div>
    <div class="offer idle" id="offer"></div>
    <div class="box" id="runeBox" style="margin-top:16px;display:none"></div>
    <div class="lower">
      <div class="box">
        <div class="tabs" id="buildTabs"></div>
        <div class="blurb" id="buildBlurb"></div>
        <div class="items" id="buildItems"></div>
      </div>
      <div class="box" id="augBox">
        <h2>Your augments</h2>
        <div class="chips" id="chosen"></div>
        <div id="combos"></div>
        <div class="search">
          <input id="augSearch" placeholder="Find an augment" aria-label="Find an augment">
          <div class="seg" id="tierSeg"></div>
        </div>
        <div class="muted" style="font-size:12px;margin-bottom:6px" id="rankNote"></div>
        <div class="auglist" id="augList"></div>
      </div>
    </div>
    <datalist id="champNames"></datalist>
  </section>

  <!-- LIVE -->
  <section class="page" id="p-live">
    <div class="box"><div class="cs-head" style="margin:0"><div><h2 style="margin:0">Live game scouting</h2><div class="muted" style="font-size:12.5px" id="scoutStatus"></div></div><div class="muted" style="font-size:12px">Ranks and recent form come from each player's League profile. Champ select stays private.</div></div></div>
    <div class="scout" id="scout"></div>
  </section>

  <!-- CHAMPIONS -->
  <section class="page" id="p-champs">
    <div class="box"><div class="search" style="margin:0"><input id="champQ" list="champNames" placeholder="Search a champion" aria-label="Search a champion"><div class="seg" id="modeSeg"></div></div></div>
    <div id="champOut"></div>
  </section>

  <!-- PROFILE -->
  <section class="page" id="p-profile">
    <div class="box"><div class="search" style="margin:0;flex-wrap:wrap">
      <input id="lookQ" placeholder="Look up a player: Name#TAG" aria-label="Look up a player">
      <button class="btn gold" id="lookBtn">Look up</button><button class="btn" id="meBtn">My profile</button>
      <input id="codeQ" placeholder="Paste a friend's share code" aria-label="Paste a share code" style="max-width:300px">
    </div><div class="fr" id="friends"></div></div>
    <div id="cmpOut"></div>
    <div id="profOut" style="margin-top:16px"><div class="box muted">Open League and your profile appears here.</div></div>
  </section>

  <!-- FRIENDS -->
  <section class="page" id="p-friends">
    <div class="box"><div class="cs-head" style="margin:0"><div><h2 style="margin:0">Friends leaderboard</h2><div class="muted" style="font-size:12.5px" id="frStatus"></div></div><div class="seg" id="frSort"></div></div></div>
    <div class="hl" id="frHi"></div>
    <div class="box" style="margin-top:16px;padding:6px 18px"><div id="frRows"></div></div>
  </section>

  <!-- GAMES -->
  <section class="page" id="p-games">
    <div class="sum" id="gameSum"></div>
    <div class="box"><h2>Recent games</h2><div id="gameList"></div></div>
  </section>

  <!-- SETTINGS -->
  <section class="page" id="p-settings">
    <div class="box" style="max-width:860px">
      <div class="set"><div><b>Auto-accept</b><p>Accept ready checks automatically.</p></div><button class="switch" data-set="accept"></button></div>
      <div class="set"><div><b>In-game overlay</b><p>Grade letters sit right above each augment card automatically, and a small LoLStat button opens a panel with your builds and augments. Click the button or press Ctrl+Shift+L to open or close it. Set League's Window Mode to Borderless.</p></div><button class="switch" data-set="overlay"></button></div>
      <div class="set"><div><b>Read augment cards automatically</b><p>Spots the cards on screen, rerolls included, and the one you pick. Uses Windows' built-in text recognition; nothing leaves your PC.</p></div><button class="switch" data-set="scan"></button></div>
      <div class="set"><div><b>Item sets in the League client</b><p>During champ select, LoLStat saves its three builds as item sets for your champion so they show up in the in-game shop. They update when you swap and are removed after the game. Your own item sets are never touched.</p></div><button class="switch" data-set="itemsets"></button></div>
      <div class="set"><div><b>Game data</b><p id="setData">Items, champions and augments refresh every time LoLStat opens and every 6 hours.</p></div><button class="btn" id="refreshBtn">Update now</button></div>
    </div>
    <div class="box" style="max-width:860px;margin-top:16px">
      <h2>Appearance</h2><div class="muted" style="font-size:12.5px">Pick a theme. The in-game overlay uses it too.</div>
      <div class="themes" id="themeGrid"></div>
      <h2 style="margin-top:20px">Champion themes</h2><div class="muted" style="font-size:12.5px">A theme for every champion and skin, colored from its splash art.</div>
      <div class="ctpick">
        <label>Champion<select id="ctChamp" aria-label="Champion"></select></label>
        <label>Skin<select id="ctSkin" aria-label="Skin"></select></label>
        <label class="chk" style="padding:9px 12px;align-self:end"><input type="checkbox" id="ctOwned"><div><b>Only skins I own</b></div></label>
      </div>
      <div class="ctprev" id="ctPrev"></div>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center"><button class="btn gold" id="ctUse">Use this theme</button>
        <label class="chk" style="padding:9px 12px"><input type="checkbox" id="ctFollow" onchange="act('setting',{name:'theme_follow'})"><div><b>Match my champion automatically</b><span>Switches to the champion and skin you're playing</span></div></label></div>
      <h2 style="margin-top:20px">Custom theme</h2><div class="muted" style="font-size:12.5px">Start from any theme, change colors and transparency, and save it as your own. Changes preview live.</div>
      <div class="creator" id="creator"></div>
      <div class="slider"><label for="cAlpha">Panel opacity</label><input type="range" id="cAlpha" min="0.4" max="1" step="0.02"></div>
      <div class="slider"><label for="cRadius">Roundness</label><input type="range" id="cRadius" min="2" max="24" step="1"></div>
      <div class="slider"><label for="cOverlay">Overlay opacity</label><input type="range" id="cOverlay" min="0.5" max="1" step="0.02"></div>
      <div style="display:flex;gap:8px;margin-top:6px"><button class="btn" id="cFrom">Copy current theme</button><button class="btn gold" id="cSave">Save custom theme</button></div>
    </div>
    <div class="box" style="max-width:860px;margin-top:16px"><details class="act" id="trouble"><summary>Troubleshooting</summary>
      <p class="muted" style="font-size:12.5px;margin:10px 0 0" id="scanState">–</p>
      <div class="reader" style="margin-top:10px"><div><img id="readerImg" alt="What LoLStat sees on your screen"><div class="muted" style="font-size:12px;margin-top:6px" id="readerNote"></div></div>
        <div><div class="muted" style="font-size:12.5px">Only needed if something looks wrong. Copy report puts a status report on your clipboard to send to support.</div>
          <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap"><button class="btn" onclick="act('test_overlay')">Test overlay</button><button class="btn gold" id="copyDiag">Copy report</button></div></div></div>
      <textarea class="diag" id="diagText" readonly aria-label="Diagnostics report"></textarea>
    </details></div>
    <p class="fine" style="margin-top:18px" id="about"></p>
  </section>
</main>

<script>
""" + COMMON_JS + r"""
let lastToast = 0, autoNav = false;
let S = null, page = 'home', buildIdx = 0, tierF = '', augs = [], augVer = -1, lastOfferKey = '', champsLoaded = false;
const PHASE = {None:['In the client','Ready when you are'],Lobby:['In a lobby','Queue up whenever you like'],
  Matchmaking:['In queue','Auto-accept has you covered'],ReadyCheck:['Match found','Accepting now'],
  ChampSelect:['Champ select','Good luck'],GameStart:['Loading in','Here we go'],InProgress:['In game','Have fun'],
  WaitingForStats:['Post game','GG'],PreEndOfGame:['Post game','GG'],EndOfGame:['Post game','GG'],Reconnect:['Reconnect','Hop back in']};

document.querySelectorAll('.nav').forEach(b => b.onclick = () => go(b.dataset.page));
function go(p){ page=p; try { localStorage.setItem('lolstat.page', p); } catch(e){} document.querySelector('main').scrollTop = 0; document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('on',b.dataset.page===p));
  document.querySelectorAll('.page').forEach(s=>s.classList.toggle('on',s.id==='p-'+p));
  q('#title').textContent = pageTitle(p); if (p==='live') loadScout(); if (p==='profile'){ loadProfile(); loadFriends(); } if (p==='friends') loadBoard(); if (p==='settings') initCT(); if (p==='champs') initChamps(); }
const PAGE_TITLES_EXTRA = {friends:'Friends'};
const MODE_NAME = {sr:"Summoner's Rift", aram:'ARAM', mayhem:'ARAM Mayhem'};
function pageTitle(p){ return {home:'Home', mayhem: S && S.mayhem.mode ? MODE_NAME[S.mayhem.mode] : 'Champ select and builds', live:'Live game', champs:'Champions', profile:'Profile', friends:'Friends', games:'Games and damage', settings:'Settings'}[p]; }
q('#acceptSwitch').onclick = () => act('toggle_accept');
document.querySelectorAll('[data-set]').forEach(b => b.onclick = () => act('setting', {name:b.dataset.set}));
async function loadDiag(){ try { const r = await fetch('/api/diagnostics?key=' + encodeURIComponent(KEY)); q('#diagText').value = await r.text(); } catch(e){} }
q('#copyDiag').onclick = async () => { await loadDiag(); try { await navigator.clipboard.writeText(q('#diagText').value); q('#copyDiag').textContent = 'Copied'; } catch(e){ q('#diagText').select(); document.execCommand('copy'); q('#copyDiag').textContent = 'Copied'; } setTimeout(()=>q('#copyDiag').textContent='Copy report', 2000); };
setInterval(()=>{ if (page === 'settings' && q('#trouble').open) loadDiag(); }, 2000);
q('#refreshBtn').onclick = () => { q('#setData').textContent = 'Updating…'; act('refresh_data'); };
q('#augSearch').oninput = drawAugs;
q('#tierSeg').innerHTML = ['','Prismatic','Gold','Silver'].map(t => `<button class="${t?'tier-'+t:''}" data-t="${t}">${t||'All'}</button>`).join('');
q('#tierSeg').onclick = e => { const b = e.target.closest('button'); if(!b) return; tierF = b.dataset.t; drawAugs(); };
q('#qr').src = '/api/qr.svg?key=' + encodeURIComponent(KEY);

function render(st){
  S = st; const a = st.accept, m = st.mayhem;
  const on = a.connected;
  q('#railLive').classList.toggle('on', on);
  q('#clientPill').className = 'pill' + (m.live ? ' live' : '');
  q('#clientPill').textContent = m.live ? (m.is_mayhem ? 'Live: ARAM Mayhem' : 'Live game') : on ? 'Client connected' : 'Waiting for League';
  q('#patchPill').textContent = 'Patch ' + (m.patch || '–');
  // home
  const ph = PHASE[a.phase] || (on ? [a.phase,''] : ['League client','Open League to start']);
  q('#phaseSmall').textContent = on ? 'League client connected' : 'League client';
  q('#phaseBig').textContent = on ? ph[0] : 'Open League to start';
  q('#phaseSub').textContent = on ? ph[1] : 'LoLStat connects as soon as the client is running.';
  q('#acceptSwitch').classList.toggle('on', a.enabled);
  q('#accCount').textContent = a.accepted_count;
  q('#accLast').textContent = a.last_accepted ? 'Last one at ' + a.last_accepted : 'None yet this session';
  q('#ovState').textContent = st.settings.overlay ? 'On' : 'Off';
  q('#dataPatch').textContent = m.patch || '–';
  q('#dataStatus').textContent = 'Data ' + (m.data_status || '');
  q('#feed').innerHTML = (st.log||[]).slice().reverse().map(l=>{ const t=l.slice(1,9), x=l.slice(11); return `<div><time>${esc(t)}</time><span>${esc(x)}</span></div>`; }).join('') || '<span class="muted">Nothing yet.</span>';
  document.querySelectorAll('[data-set]').forEach(b => b.classList.toggle('on', b.dataset.set==='accept' ? a.enabled : !!st.settings[b.dataset.set]));
  q('#setData').textContent = `Patch ${m.patch}, ${m.data_status}. Refreshes every time LoLStat opens and every 6 hours.`;
  q('#about').textContent = `LoLStat ${st.app.version}. ${st.app.notice} Mayhem data: DeepARAM (MIT). Item and champion data: Riot Data Dragon.`;
  q('#scanState').textContent = 'Right now: ' + (m.scanner || '–');
  const t = q('#toast');
  if (m.toast && m.toast.t !== lastToast){ lastToast = m.toast.t; t.textContent = m.toast.text; t.classList.add('on'); clearTimeout(window._tt); window._tt = setTimeout(()=>t.classList.remove('on'), 5000); }
  if (a.phase === 'ChampSelect' && m.champ_select && page === 'home' && !autoNav){ autoNav = true; go('mayhem'); }
  if (a.phase !== 'ChampSelect') autoNav = false;
  if (page === 'mayhem') q('#title').textContent = pageTitle('mayhem');
  drawRunes(m);
  const may = !m.mode || m.mode === 'mayhem';
  q('#offer').style.display = may ? '' : 'none';
  q('#augBox').style.display = may ? '' : 'none';
  document.querySelector('#p-mayhem .lower').style.gridTemplateColumns = may ? '' : '1fr';
  drawAuto(st); drawLastGame(m); drawGames(m); drawReader(m, st.settings); drawModal(m); applyThemeFrom(st.settings);
  drawMayhem(m);
}

function drawMayhem(m){
  // matchup
  if (m.champion){
    q('#matchup').innerHTML = `<div class="me">${img(m.champion.icon,'',84)}<div><div class="muted" style="font-size:12.5px">${m.live ? 'You are playing' : m.champ_select ? 'In champ select' : 'Planning as'}</div><div class="nm">${esc(m.champion.name)}</div>${m.live && m.level ? `<div class="muted" style="font-size:12.5px">Level ${m.level}</div>` : ''}</div></div>`
      + (m.live && m.stats ? `<div class="livestats" style="margin:0 0 0 18px">${statCells(m.stats)}</div>` : '')
      + (m.enemies.length ? `<span class="vs">vs</span><div class="enemies">${m.enemies.map(e=>`<div class="enemy">${img(e.icon,'',56)}<span>${esc(e.name)}</span></div>`).join('')}</div>` : '');
  } else {
    q('#matchup').innerHTML = `<div><div class="nm" style="font-size:20px;font-weight:700">Waiting for your next game</div><div class="muted">Your champion and the enemy team fill in when the game loads. To plan ahead, pick them below.</div></div>`;
  }
  q('#notes').innerHTML = m.notes.map(n=>`<span class="note">${esc(n)}</span>`).join('');
  if (!m.live && !m.champ_select) drawPlan(m); else { q('#plan').innerHTML = ''; delete q('#plan').dataset.ready; }
  drawChampSelect(m.champ_select);
  q('#matchBox').style.display = m.champ_select ? 'none' : '';
  q('#cs').style.marginTop = m.champ_select ? '0' : '';
  // offer
  const o = q('#offer');
  if (m.offer){
    const key = m.offer.cards.map(c=>c.id).join(',');
    o.className = 'offer';
    o.innerHTML = `<h2>Augment cards on your screen</h2><div class="cards ${key!==lastOfferKey?'fresh':''}">${m.offer.cards.map((c,i)=>card(c, i===m.offer.best, false)).join('')}</div>`;
    lastOfferKey = key;
  } else if (m.unconfirmed){
    o.className = 'offer';
    o.innerHTML = `<h2>Which card did you take?</h2><div class="cards">${m.unconfirmed.cards.map(c=>card(c,false,true)).join('')}</div><div style="margin-top:12px"><button class="btn" onclick="act('dismiss_unconfirmed')">None of these</button></div>`;
    lastOfferKey = '';
  } else {
    lastOfferKey = '';
    o.className = 'offer idle';
    const on = /Watching/.test(m.scanner);
    o.innerHTML = `<h2>Augment cards</h2><div class="muted">When cards appear in game they show up here with their grades, and the one you pick is added for you.</div><div class="scan ${on?'on':''}" style="margin-top:10px"><i></i>${esc(m.scanner)}</div>`;
  }
  // builds
  const B = m.builds;
  if (B.length){
    buildIdx = Math.min(buildIdx, B.length-1);
    q('#buildTabs').innerHTML = B.map((b,i)=>`<button class="${i===buildIdx?'on':''}" onclick="buildIdx=${i};drawMayhem(S.mayhem)">${esc(b.style.charAt(0)+b.style.slice(1).toLowerCase())}</button>`).join('');
    const b = B[buildIdx];
    q('#buildBlurb').textContent = b.blurb;
    const rows = (b.boots ? [Object.assign({n:'B'}, b.boots)] : []).concat(b.items.map((it,i)=>Object.assign({n:i+1}, it)));
    q('#buildItems').innerHTML = rows.map(it=>`<div class="item ${it.owned?'owned':''}"><span class="n">${it.n}</span>${img(it.icon,'',48)}<div><b>${esc(it.name)}${it.owned?'<span class="own">Owned</span>':''}</b><div class="why">${esc(it.why)}</div></div></div>`).join('');
  } else {
    q('#buildTabs').innerHTML = ''; q('#buildBlurb').textContent = '';
    q('#buildItems').innerHTML = `<div class="muted">Builds appear as soon as LoLStat knows your champion.</div>`;
  }
  // chosen
  q('#chosen').innerHTML = m.chosen.length ? m.chosen.map(c=>`<span class="chip tier-${esc(c.tier)}">${img(c.icon,'',26)}${grade(c.grade)}<span>${esc(c.name)}</span><button class="x" aria-label="Remove ${esc(c.name)}" onclick="act('remove_aug',{id:'${c.id}'})">✕</button></span>`).join('')
    : `<span class="muted" style="font-size:12.5px">None yet. Picked cards are added automatically, or click one below.</span>`;
  q('#combos').innerHTML = (m.combos||[]).length ? `<div class="muted" style="font-size:12.5px;margin:12px 0 6px">Pairs well with what you have on ${esc(m.champion ? m.champion.name : 'your champion')}</div>` + m.combos.map(a=>`<button class="aug tier-${esc(a.tier)}" onclick="act('add_aug',{id:'${a.id}'})" title="${esc(a.text)}">${img(a.icon,'',36)}<div><div class="an">${esc(a.name)}</div><div class="at">pairs with ${esc(a.with_)}</div></div><div class="ap">${pct(a.pair_pick)} take both</div>${grade(a.grade)}</button>`).join('') : '';
  q('#rankNote').textContent = m.rank_source === 'champ' ? `Ranked for ${m.champion.name}, best first. Daily stats from ${m.rank_date}.` : `Ranked overall, best first. Daily stats from ${m.rank_date}.`;
  const v = m.ranks_version + '|' + (m.champion ? m.champion.name : '');
  if (v !== augVer){ augVer = v; api('/api/augments').then(r=>{augs=r; drawAugs();}).catch(()=>{}); }
}

// ---------------- automation
const AUTO = [['accept','Auto-accept','Accepts every match the moment it pops'],['itemsets','Item sets','Saves LoLStat builds to the client in champ select'],
  ['spells','Summoner spells','Sets your spells in champ select'],['overlay','In-game overlay','Letters over cards and the LoLStat panel'],['scan','Read augment cards','Spots cards and your pick on screen']];
const SPELLS = ['Smart','Flash','Mark','Ignite','Exhaust','Ghost','Heal','Barrier','Cleanse','Clarity'];
function autoHtml(st){
  return AUTO.map(([k,t,d])=>{ const on = k==='accept' ? st.accept.enabled : !!st.settings[k];
    return `<label class="chk"><input type="checkbox" ${on?'checked':''} onchange="${k==='accept'?"act('toggle_accept')":`act('setting',{name:'${k}'})`}"><div><b>${t}</b><span>${d}</span></div></label>`; }).join('');
}
function spellHtml(st){
  const sel = (n,v) => `<select aria-label="${n}" onchange="act('set_value',{name:'${n}',value:this.value})">${SPELLS.map(x=>`<option ${x===v?'selected':''}>${x}</option>`).join('')}</select>`;
  return `<span class="muted" style="font-size:12.5px">Spells: D</span>${sel('spell_d', st.settings.spell_d||'Smart')}<span class="muted" style="font-size:12.5px">F</span>${sel('spell_f', st.settings.spell_f||'Smart')}<span class="muted" style="font-size:12px">Smart picks damage spells for your champion.</span>`;
}
function drawAuto(st){
  const sig = JSON.stringify([st.accept.enabled, st.settings]);
  if (q('#autoBox').dataset.sig === sig) return;
  q('#autoBox').dataset.sig = sig;
  q('#autoBox').innerHTML = autoHtml(st); q('#spellBox').innerHTML = spellHtml(st);
}
// ---------------- last game + history
const fmt = n => (n||0).toLocaleString();
function splitBar(g){ const t = (g.physical+g.magic+g.true)||1;
  return `<div class="split" title="Physical ${fmt(g.physical)}, magic ${fmt(g.magic)}, true ${fmt(g.true)}"><i style="width:${g.physical/t*100}%;background:#ff8a3d"></i><i style="width:${g.magic/t*100}%;background:#4aa3ff"></i><i style="width:${g.true/t*100}%;background:#ece6d6"></i></div>`; }
function champIcon(name){ const c = (S && S._champs || {})[name]; return c ? c.icon : ''; }
function drawLastGame(m){
  const el = q('#lastGame'), g = (m.history||[])[0];
  if (m.live && m.stats){ el.innerHTML = `<h2>Live game</h2><div class="livestats">${statCells(m.stats)}</div><div class="muted" style="font-size:12px;margin-top:10px">Damage numbers arrive the moment the game ends. League's live data doesn't include damage.</div>`; return; }
  if (!g){ el.innerHTML = `<h2>Last game</h2><div class="muted">Play a game and your damage report shows up here.</div>`; return; }
  el.innerHTML = `<h2>Last game: ${esc(g.champion)} <span class="${g.win?'win':'loss'}" style="font-size:13px;margin-left:6px">${g.win?'Victory':'Defeat'}</span></h2>
    <div class="livestats"><div><b>${fmt(g.damage)}</b>damage to champions</div><div><b>${fmt(g.dpm)}</b>damage per minute</div><div><b>${g.share}%</b>of team damage</div><div><b>${g.k}/${g.d}/${g.a}</b>K/D/A</div><div><b>${fmt(g.taken)}</b>damage taken</div><div><b>${fmt(g.healed)}</b>healed</div></div>${splitBar(g)}`;
}
function statCells(s){ return `<div><b>${s.k}/${s.d}/${s.a}</b>K/D/A</div><div><b>${s.kda}</b>KDA</div><div><b>${s.kp}%</b>kill participation</div><div><b>${s.cs}</b>CS</div><div><b>${fmt(s.gold)}</b>gold</div>`; }
function drawGames(m){
  const H = m.history || [];
  const sig = H.length + '|' + (H[0]||{}).id;
  if (q('#gameList').dataset.sig === sig) return; q('#gameList').dataset.sig = sig;
  if (!H.length){ q('#gameSum').innerHTML=''; q('#gameList').innerHTML = `<div class="muted">Your games and damage show up here after each game.</div>`; return; }
  const avg = k => Math.round(H.reduce((a,g)=>a+(g[k]||0),0)/H.length);
  const best = H.reduce((a,g)=>g.damage>a.damage?g:a, H[0]);
  const wins = H.filter(g=>g.win).length;
  q('#gameSum').innerHTML = [[fmt(avg('damage')),'average damage'],[fmt(avg('dpm')),'average damage per minute'],[avg('share')+'%','average team share'],[fmt(best.damage),'best game ('+esc(best.champion)+')']]
    .map(([v,l])=>`<div class="box"><div class="stat">${v}</div><div class="muted" style="font-size:12.5px">${l}</div></div>`).join('');
  api('/api/champions').then(cs=>{ const by = {}; cs.forEach(c=>by[c.name]=c);
    q('#gameList').innerHTML = H.map(g=>`<div class="game">${img((by[g.champion]||{}).icon,'',52)}<div><b>${esc(g.champion)}</b><div class="${g.win?'win':'loss'}" style="font-size:12.5px">${g.win?'Victory':'Defeat'}</div><div class="muted" style="font-size:12px">${esc(g.when)}, ${g.minutes} min</div></div>
      <div><b>${g.k}/${g.d}/${g.a}</b><div class="muted" style="font-size:12px">${fmt(g.gold)} gold</div></div>
      <div><span class="dmg">${fmt(g.damage)}</span> <span class="muted" style="font-size:12px">${fmt(g.dpm)}/min, ${g.share}% of team</span>${splitBar(g)}</div>
      <div class="muted" style="font-size:12px">${(g.augments||[]).map(esc).join(', ') || 'No augments recorded'}</div></div>`).join('');
  }).catch(()=>{});
}
// ---------------- live reader view + letter sliders
let readerT = 0;
function drawReader(m, set){
  if (m.preview_t && m.preview_t !== readerT && page === 'settings' && q('#trouble').open){ readerT = m.preview_t; q('#readerImg').src = '/api/reader.jpg?key=' + encodeURIComponent(KEY) + '&t=' + readerT; }
  q('#readerNote').textContent = m.live ? 'Live: ' + (m.scanner || '') : 'Starts when your game loads. Recognized cards are boxed.';
}
// ---------------- pick pop-up
let modalKey = '', modalHidden = '';
q('#pickHide').onclick = () => { modalHidden = modalKey; q('#pickModal').classList.remove('on'); };
function drawModal(m){
  const src = m.offer || m.unconfirmed;
  if (!src){ q('#pickModal').classList.remove('on'); modalKey = ''; return; }
  const key = src.cards.map(c=>c.id).join(',');
  if (key !== modalKey){ modalKey = key; q('#pickCards').innerHTML = src.cards.map((c,i)=>card(c, m.offer && i===m.offer.best, false).replace('<div class="card', `<div onclick="act('pick_aug',{id:'${c.id}'});q('#pickModal').classList.remove('on')" class="card`)).join(''); }
  if (key !== modalHidden) q('#pickModal').classList.add('on');
}


// ---------------- runes
function runesHtml(r){
  if (!r) return '';
  const ic = r.icons || [];
  return `<div class="runes">${ic[0] ? `<img class="ks" src="${esc(ic[0])}" alt="${esc(r.keystone)}" title="${esc(r.keystone)}">` : ''}${ic.slice(1).map((u,i)=>`<img src="${esc(u)}" alt="" title="${esc(r.runes[i+1]||'')}">`).join('')}
    <div style="margin-left:6px"><b>${esc(r.keystone)}</b> <span class="muted" style="font-size:12.5px">${esc(r.primary)} + ${esc(r.secondary)}, ${esc(r.label)} page</span><div class="muted" style="font-size:12px">${r.runes.map(esc).join(', ')}</div></div></div>`;
}
function drawRunes(m){
  const el = q('#runeBox');
  if (!m.runes){ el.style.display = 'none'; return; }
  el.style.display = 'block';
  const h = `<h2>Rune page</h2>${runesHtml(m.runes)}<div class="muted" style="font-size:12px;margin-top:8px">${S.settings.runes ? 'Imported to your client automatically in champ select.' : 'Turn on Rune pages in Automation to import it automatically.'}</div>`;
  if (el.dataset.h !== h){ el.dataset.h = h; el.innerHTML = h; }
}
AUTO.splice(3, 0, ['runes','Rune pages','Imports a damage rune page (Summoner\'s Rift and ARAM)']);

// ---------------- live scouting
let champIcons = {};
async function ensureChampIcons(){ if (Object.keys(champIcons).length) return; try { (await api('/api/champions')).forEach(c=>champIcons[c.name]=c); } catch(e){} }
async function loadScout(){
  if (page !== 'live') return;
  await ensureChampIcons();
  try {
    const r = await api('/api/scout');
    q('#scoutStatus').textContent = r.live ? r.status : 'Start a game and every player shows up here with their rank and recent form.';
    const row = p => { const c = champIcons[p.champion] || {}; const rk = p.rank;
      const tags = (p.tags||[]).map(t=>`<span class="tag ${/streak|On fire|High KDA|One-trick/.test(t) ? (/loss/.test(t)?'bad':'good') : ''}">${esc(t)}</span>`).join('');
      return `<div class="pl ${p.me?'me':''}">${img(c.icon,'',44)}<div style="min-width:0"><div class="n">${esc(p.name)}</div><div class="r">${esc(p.champion||'')}${rk ? ' · ' + esc(rk.label) + (rk.tier && rk.tier!=='NONE' ? ` ${rk.lp} LP` : '') + (rk.wr!=null ? `, ${rk.wr}% (${rk.wins}W ${rk.losses}L)` : '') : ''}</div><div class="t">${tags}</div></div>
        <div class="wr">${p.recent_wr!=null ? `<b>${p.recent_wr}%</b>last ${p.recent_games}` : ''}${p.champ_games!=null ? `<div>${p.champ_games} on champ${p.champ_wr!=null?`, ${p.champ_wr}%`:''}</div>` : ''}</div></div>`; };
    const allies = r.players.filter(p=>p.team==='ally'), enemies = r.players.filter(p=>p.team==='enemy');
    q('#scout').innerHTML = r.players.length ? `<div class="side"><h3>Your team</h3>${allies.map(row).join('')}</div><div class="side"><h3>Enemy team</h3>${enemies.map(row).join('')}</div>` : '';
  } catch(e){ console.error('scout render', e && e.stack || e); setTimeout(loadScout, 800); }
}
setInterval(loadScout, 2500);

// ---------------- champions
let champMode = 'sr', champsInit = false;
function initChamps(){
  if (champsInit) return; champsInit = true;
  q('#modeSeg').innerHTML = [['sr',"Summoner's Rift"],['aram','ARAM'],['mayhem','ARAM Mayhem']].map(([k,l])=>`<button data-m="${k}" class="${k===champMode?'on':''}">${l}</button>`).join('');
  q('#modeSeg').onclick = e => { const b = e.target.closest('button'); if (!b) return; champMode = b.dataset.m; document.querySelectorAll('#modeSeg button').forEach(x=>x.classList.toggle('on', x===b)); loadChamp(); };
  q('#champQ').onchange = loadChamp;
  api('/api/champions').then(r=>{ q('#champNames').innerHTML = r.map(c=>`<option value="${esc(c.name)}">`).join(''); champsLoaded = true; });
  if (S && S.mayhem.champion){ q('#champQ').value = S.mayhem.champion.name; loadChamp(); }
}
async function loadChamp(){
  const name = q('#champQ').value.trim(); if (!name) return;
  q('#champOut').innerHTML = `<div class="box muted" style="margin-top:16px">Loading ${esc(name)}…</div>`;
  try {
    const r = await api('/api/champion?name=' + encodeURIComponent(name) + '&mode=' + champMode);
    if (r.error){ q('#champOut').innerHTML = `<div class="box muted" style="margin-top:16px">No champion called “${esc(name)}”. Pick one from the list.</div>`; return; }
    const c = r.champion;
    const fav = S && (S.settings.favorites||[]).includes(c.name), pin = S && (S.settings.pinned||{})[c.name];
    let h = `<div class="box" style="margin-top:16px"><div class="chero">${img(c.icon,'',96)}<div><div style="font-size:24px;font-weight:700">${esc(c.name)} <button class="star ${fav?'on':''}" title="${fav?'Remove from':'Add to'} favorites" aria-label="Favorite" data-n="${esc(c.name)}" onclick="act('favorite',{name:this.dataset.n}).then(loadChamp)">${fav?'★':'☆'}</button></div><div class="muted" style="font-size:12.5px">${esc((r.classes||[]).join(', '))}, ${r.damage==='ap'?'magic':r.damage==='ad'?'physical':'mixed'} damage</div>
      ${r.tier ? `<div style="margin-top:6px">${grade(r.tier)} <span class="muted" style="font-size:12.5px;margin-left:6px">ARAM Mayhem tier, ${pct(r.pick)} pick rate</span></div>` : ''}</div></div>`;
    if (r.runes) h += `<h2 style="margin-top:18px">Rune page</h2>${runesHtml(r.runes)}`;
    h += `</div><div class="two"><div class="box">`;
    r.builds.forEach((b,bi)=>{ const rows = (b.boots ? [Object.assign({n:'B'}, b.boots)] : []).concat(b.items.map((it,i)=>Object.assign({n:i+1}, it)));
      const on = (pin ?? 0) === bi && pin != null;
      h += `<h2 style="margin-top:6px">${esc(b.style.charAt(0)+b.style.slice(1).toLowerCase())}<button class="pin ${on?'on':''}" data-n="${esc(c.name)}" onclick="act('pin_build',{name:this.dataset.n,index:${bi}}).then(loadChamp)" title="Put this build first in your item sets">${on?'Your item set pick':'Use for item sets'}</button></h2><div class="blurb">${esc(b.blurb)}</div><div class="items" style="margin-bottom:14px">${rows.map(it=>`<div class="item"><span class="n">${it.n}</span>${img(it.icon,'',48)}<div><b>${esc(it.name)}</b><div class="why">${esc(it.why)}</div></div></div>`).join('')}</div>`; });
    h += `</div><div class="box"><h2>Best ARAM Mayhem augments</h2>` + (r.augments.length ? r.augments.map(a=>`<div class="aug tier-${esc(a.tier)}" style="cursor:default">${img(a.icon,'',36)}<div><div class="an">${esc(a.name)}</div><div class="at">${esc(a.tier)}</div></div><div class="ap">${a.cpick!=null?pct(a.cpick)+' on '+esc(c.name):''}</div>${grade(a.grade)}</div>`).join('') : '<div class="muted">No Mayhem stats for this champion yet.</div>') + `<div class="muted" style="font-size:12px;margin-top:10px">Builds and runes are built by LoLStat's damage engine from champion data. Mayhem augment grades come from daily stats.</div></div></div>`;
    q('#champOut').innerHTML = h;
  } catch(e){ console.error('champion render', e && e.stack || e); q('#champOut').innerHTML = `<div class="box muted" style="margin-top:16px">Couldn't load that champion. Try again.</div>`; }
}

setInterval(()=>loadProfile(), 30000);


// ---------------- other players, friends, compare, share
let viewing = null, myProf = null, cmpWith = null;
function profHtml(p){
  const ci = n => (champIcons[n]||{}).icon;
  const itemUrl = id => id ? `https://ddragon.leagueoflegends.com/cdn/${esc(S ? S.mayhem.patch : '')}/img/item/${id}.png` : '';
  const sm = p.summary || {};
  const ses = p.session;
  const lp = ses ? Object.entries(ses.lp||{}).map(([q,v])=>`${esc(q)} ${v>=0?'+':''}${v} LP`).join(', ') : '';
  let h = `<div class="box"><div class="cs-head" style="margin:0"><div><div class="cs-title">${esc(p.name)}</div><div class="muted" style="font-size:12.5px">${p.level ? 'Level ' + p.level + '. ' : ''}${p.code ? 'From a share code.' : 'Updated ' + esc(p.updated) + '.'}</div></div>
    <div style="display:flex;gap:8px">${p.other || p.code ? `<button class="btn" onclick="compareWithMe()">Compare with me</button>` : `<button class="btn" onclick="act('refresh_profile');setTimeout(()=>loadProfile(true),2500)">Refresh</button>`}<button class="btn gold" onclick="openShare()">Share</button></div></div>
    <div class="ranks">${(p.ranks||[]).map(r=>`<div class="rk"><span>${esc(r.queue)}</span><b>${esc(r.label)}${r.tier && r.tier!=='NONE' && r.label!=='Unranked' ? ` · ${r.lp} LP` : ''}</b><span>${r.wins+r.losses ? `${r.wins}W ${r.losses}L, ${r.wr}% win rate` : 'No games this season'}</span></div>`).join('')}
      ${ses ? `<div class="rk"><span>Today</span><b>${ses.wins}W ${ses.losses}L</b><span>${lp || (ses.games ? '' : 'No games yet today')}${p.streak ? (lp ? ', ' : '') + (p.streak>0 ? p.streak+' win streak' : (-p.streak)+' loss streak') : ''}</span></div>` : ''}
      ${sm.games ? `<div class="rk"><span>Last ${sm.games} games</span><b>${sm.wr}% · ${sm.kda} KDA</b><span>${fmt(sm.dpm)} damage/min, ${sm.csm} CS/min</span></div>` : ''}</div></div>`;
  if (p.code){   // a pasted share code carries a summary, not full match history
    h += `<div class="two"><div class="box"><h2>Top champions</h2>${(p.champions||[]).map(c=>`<div class="ctab">${img(ci(c.champion),'',36)}<b>${esc(c.champion)}</b><span>${c.games} games</span><span class="${c.wr>=50?'win':'loss'}">${c.wr}%</span><span class="muted">${c.kda} KDA</span></div>`).join('')}</div><div></div></div>`;
    return h;
  }
  h += `<div class="two"><div class="box"><h2>Recent matches</h2>` + (p.games||[]).map(g=>`<div class="mrow ${g.remake?'':g.win?'w':'l'}">${img(ci(g.champion),'c',44)}<div><b>${esc(g.champion)}</b><div class="${g.remake?'muted':g.win?'win':'loss'}" style="font-size:12px">${g.remake?'Remake':g.win?'Victory':'Defeat'}</div></div>
      <div><b>${g.k}/${g.d}/${g.a}</b><div class="muted" style="font-size:12px">${((g.k+g.a)/Math.max(1,g.d)).toFixed(2)} KDA</div></div><div class="hide"><b>${g.cs}</b><div class="muted" style="font-size:12px">${g.csm} CS/min</div></div><div class="hide"><b>${fmt(g.damage)}</b><div class="muted" style="font-size:12px">damage</div></div>
      <div><div class="its">${g.items.filter(Boolean).map(i=>`<img src="${itemUrl(i)}" alt="" onerror="this.style.visibility='hidden'">`).join('')}</div><div class="muted" style="font-size:12px;margin-top:3px">${esc(g.queue)}, ${g.minutes} min, ${new Date(g.when).toLocaleDateString()}</div></div>
      ${p.other ? '<span></span>' : `<button class="btn" title="Download or watch the replay in League" onclick="act('replay',{id:${g.id}})">Replay</button>`}</div>`).join('') + `</div>`;
  h += `<div><div class="box"><h2>Champions (recent games)</h2>${(p.champions||[]).slice(0,10).map(c=>`<div class="ctab">${img(ci(c.champion),'',36)}<b>${esc(c.champion)}</b><span>${c.games} games</span><span class="${c.wr>=50?'win':'loss'}">${c.wr}%</span><span class="muted">${c.kda} KDA</span></div>`).join('') || '<div class="muted">No games yet.</div>'}</div>
    <div class="box" style="margin-top:16px"><h2>Mastery</h2>${(p.mastery||[]).map(m=>`<div class="ctab">${img(ci(m.champion),'',36)}<b>${esc(m.champion)}</b><span>Level ${m.level}</span><span class="muted">${fmt(m.points)} pts</span><span></span></div>`).join('') || '<div class="muted">No mastery data.</div>'}</div></div></div>`;
  return h;
}
async function loadProfile(force){
  if (page !== 'profile' && !force) return;
  await ensureChampIcons();
  try {
    const p = await api('/api/profile');
    if (p.empty){ if (!viewing) q('#profOut').innerHTML = `<div class="box muted">${p.connected ? 'Loading your profile from the League client…' : 'Open League and your profile appears here.'}</div>`; return; }
    myProf = p;
    if (!viewing) q('#profOut').innerHTML = profHtml(p);
    if (cmpWith) drawCompare();
  } catch(e){ console.error('profile render', e && e.stack || e); setTimeout(()=>loadProfile(), 1500); }
}
async function lookUp(riot, puuid){
  await ensureChampIcons();
  q('#profOut').innerHTML = `<div class="box muted">Looking up ${esc(riot || 'player')}…</div>`; q('#cmpOut').innerHTML = ''; cmpWith = null;
  try {
    const r = await api('/api/player?riot=' + encodeURIComponent(riot || '') + (puuid ? '&puuid=' + encodeURIComponent(puuid) : ''));
    if (r.error){ q('#profOut').innerHTML = `<div class="box muted">${esc(r.error)}</div>`; return; }
    viewing = r; q('#profOut').innerHTML = profHtml(r);
  } catch(e){ q('#profOut').innerHTML = `<div class="box muted">Couldn't look that player up. Try again.</div>`; }
}
q('#lookBtn').onclick = () => { const v = q('#lookQ').value.trim(); if (v) lookUp(v); };
q('#lookQ').addEventListener('keydown', e => { if (e.key === 'Enter') q('#lookBtn').click(); });
q('#meBtn').onclick = () => { viewing = null; cmpWith = null; q('#cmpOut').innerHTML = ''; loadProfile(true); };
q('#codeQ').addEventListener('change', () => { const p = decodeShare(q('#codeQ').value.trim()); if (!p){ toastMsg('That share code doesn’t look right. Copy the whole code and try again.'); return; } viewing = p; q('#profOut').innerHTML = profHtml(p); compareWithMe(); });
async function loadFriends(){
  try { const fr = await api('/api/friends');
    q('#friends').innerHTML = fr.length ? `<span class="muted" style="font-size:12px;align-self:center">Friends:</span>` + fr.slice(0, 40).map(f=>`<button data-p="${esc(f.puuid||'')}" data-n="${esc(f.name)}" onclick="lookUp(this.dataset.n, this.dataset.p)"><i class="${f.playing==='inGame'?'ingame':f.status!=='offline'?'on':''}"></i>${esc(f.name)}</button>`).join('') : '';
  } catch(e){}
}
function toastMsg(t){ const el = q('#toast'); el.textContent = t; el.classList.add('on'); clearTimeout(window._tt); window._tt = setTimeout(()=>el.classList.remove('on'), 4000); }
function compareWithMe(){ if (!viewing) return; if (!myProf){ toastMsg('Your profile is still loading. Try again in a moment.'); return; } cmpWith = viewing; drawCompare(); }
function drawCompare(){
  const a = myProf, b = cmpWith; if (!a || !b) return;
  const solo = p => (p.ranks||[]).find(r=>r.type==='RANKED_SOLO_5x5') || {};
  const score = r => { const T = ['IRON','BRONZE','SILVER','GOLD','PLATINUM','EMERALD','DIAMOND','MASTER','GRANDMASTER','CHALLENGER']; const d = ['IV','III','II','I'].indexOf((r.label||'').split(' ').pop()); return r.tier && T.includes(r.tier) ? T.indexOf(r.tier)*400 + Math.max(0,d)*100 + (r.lp||0) : -1; };
  const sa = a.summary||{}, sb = b.summary||{};
  const rows = [
    ['Solo/Duo rank', solo(a).label ? solo(a).label + (solo(a).lp!=null && solo(a).label!=='Unranked' ? ` ${solo(a).lp} LP` : '') : '–', solo(b).label ? solo(b).label + (solo(b).lp!=null && solo(b).label!=='Unranked' ? ` ${solo(b).lp} LP` : '') : '–', score(solo(a)), score(solo(b))],
    ['Season win rate', solo(a).wr!=null ? solo(a).wr+'%' : '–', solo(b).wr!=null ? solo(b).wr+'%' : '–', solo(a).wr??-1, solo(b).wr??-1],
    ['Recent win rate', sa.games ? sa.wr+'%' : '–', sb.games ? sb.wr+'%' : '–', sa.wr??-1, sb.wr??-1],
    ['KDA', sa.kda ?? '–', sb.kda ?? '–', sa.kda??-1, sb.kda??-1],
    ['Average K / D / A', sa.games ? `${sa.k} / ${sa.d} / ${sa.a}` : '–', sb.games ? `${sb.k} / ${sb.d} / ${sb.a}` : '–', 0, 0],
    ['Damage per minute', sa.dpm!=null ? fmt(sa.dpm) : '–', sb.dpm!=null ? fmt(sb.dpm) : '–', sa.dpm??-1, sb.dpm??-1],
    ['CS per minute', sa.csm ?? '–', sb.csm ?? '–', sa.csm??-1, sb.csm??-1],
    ['Most played', ((a.champions||[])[0]||{}).champion || '–', ((b.champions||[])[0]||{}).champion || '–', 0, 0],
  ];
  q('#cmpOut').innerHTML = `<div class="box" style="margin-top:16px"><div class="cs-head" style="margin:0 0 6px"><h2 style="margin:0">You vs ${esc(b.name)}</h2><button class="btn" onclick="cmpWith=null;q('#cmpOut').innerHTML=''">Close</button></div>
    <div class="cmp"><div class="a"><b>${esc(a.name)}</b></div><div class="lab"></div><div class="b"><b>${esc(b.name)}</b></div>
    ${rows.map(([l,x,y,nx,ny])=>`<div class="a ${nx>ny&&nx>=0?'best':''}">${esc(x)}</div><div class="lab">${l}</div><div class="b ${ny>nx&&ny>=0?'best':''}">${esc(y)}</div>`).join('')}</div></div>`;
}
// share code: a compact summary anyone can paste into LoLStat (no server needed)
function encodeShare(p){
  const o = {v:1, n:p.name, l:p.level, r:(p.ranks||[]).map(r=>[r.queue, r.type, r.tier, r.label, r.lp, r.wins, r.losses]), s:p.summary||{},
             c:(p.champions||[]).slice(0,5).map(c=>[c.champion, c.games, c.wr, c.kda]), t:Date.now()};
  return 'LOLSTAT1:' + btoa(unescape(encodeURIComponent(JSON.stringify(o))));
}
function decodeShare(code){
  try { const m = code.match(/LOLSTAT1:([A-Za-z0-9+/=]+)/); if (!m) return null; const o = JSON.parse(decodeURIComponent(escape(atob(m[1]))));
    return {name:o.n, level:o.l, code:true, other:true, summary:o.s, ranks:o.r.map(r=>({queue:r[0], type:r[1], tier:r[2], label:r[3], lp:r[4], wins:r[5], losses:r[6], wr: r[5]+r[6] ? Math.round(r[5]/(r[5]+r[6])*100) : null})),
            champions:o.c.map(c=>({champion:c[0], games:c[1], wr:c[2], kda:c[3]})), updated:new Date(o.t).toLocaleString()};
  } catch(e){ return null; }
}
// stats card image
function loadImg(src){ return new Promise(res=>{ if (!src) return res(null); const i = new Image(); i.crossOrigin = 'anonymous'; i.onload = ()=>res(i); i.onerror = ()=>res(null); i.src = src; }); }
async function drawCard(p){
  const cv = q('#card'), x = cv.getContext('2d'), css = getComputedStyle(document.documentElement), v = n => css.getPropertyValue(n).trim();
  const W = cv.width, H = cv.height, F = "'Sora','Segoe UI',sans-serif";
  const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, v('--ink') || '#0c1220'); g.addColorStop(1, v('--hi') || '#1d2a4d');
  x.fillStyle = g; x.fillRect(0, 0, W, H);
  x.strokeStyle = v('--gold') || '#d9b871'; x.lineWidth = 3; x.strokeRect(1.5, 1.5, W - 3, H - 3);
  const logo = await loadImg('/logo.png'); if (logo) x.drawImage(logo, 40, 36, 56, 56);
  x.fillStyle = v('--text') || '#ece6d6'; x.font = `800 40px ${F}`; x.fillText(p.name || 'Player', 112, 76);
  x.fillStyle = v('--muted') || '#8e96ab'; x.font = `500 18px ${F}`; x.fillText((p.level ? 'Level ' + p.level + '   ' : '') + 'LoLStat', 114, 104);
  const ranks = (p.ranks||[]).filter(r=>r.queue!=='Arena' || r.wins).slice(0,4);
  ranks.forEach((r,i)=>{ const bx = 40 + i * 262, by = 140; x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(bx, by, 246, 104);
    x.fillStyle = v('--muted'); x.font = `500 16px ${F}`; x.fillText(r.queue, bx + 16, by + 28);
    x.fillStyle = v('--text'); x.font = `700 26px ${F}`; x.fillText(r.label + (r.label!=='Unranked' && r.tier && r.tier!=='NONE' ? ` ${r.lp} LP` : ''), bx + 16, by + 62);
    x.fillStyle = v('--muted'); x.font = `500 15px ${F}`; x.fillText(r.wins + r.losses ? `${r.wins}W ${r.losses}L · ${r.wr}%` : 'No games', bx + 16, by + 88); });
  const s = p.summary || {};
  const cells = [[s.games ? s.wr + '%' : '–', 'recent win rate'], [s.kda ?? '–', 'KDA'], [s.dpm!=null ? fmt(s.dpm) : '–', 'damage / min'], [s.csm ?? '–', 'CS / min'], [s.games ?? 0, 'games']];
  cells.forEach(([val, lab], i)=>{ const bx = 40 + i * 210, by = 290; x.fillStyle = v('--gold') || '#d9b871'; x.font = `800 38px ${F}`; x.fillText(String(val), bx, by + 40);
    x.fillStyle = v('--muted'); x.font = `500 15px ${F}`; x.fillText(lab, bx, by + 66); });
  x.fillStyle = v('--muted'); x.font = `600 16px ${F}`; x.fillText('Top champions', 40, 410);
  const champs = (p.champions||[]).slice(0,4);
  for (let i = 0; i < champs.length; i++){ const c = champs[i], bx = 40 + i * 262, by = 426;
    const im = await loadImg((champIcons[c.champion]||{}).icon); x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(bx, by, 246, 84);
    if (im){ try { x.drawImage(im, bx + 12, by + 12, 60, 60); } catch(e){} }
    x.fillStyle = v('--text'); x.font = `700 19px ${F}`; x.fillText(c.champion, bx + 84, by + 36);
    x.fillStyle = v('--muted'); x.font = `500 13px ${F}`; x.fillText(`${c.games} games · ${c.wr}% · ${c.kda} KDA`, bx + 84, by + 60, 150); }
  x.fillStyle = v('--dim') || '#5f6880'; x.font = `500 13px ${F}`; x.fillText('Made with LoLStat · ' + new Date().toLocaleDateString() + ' · Not endorsed by Riot Games', 40, H - 28);
}
async function openShare(){
  const p = viewing || myProf; if (!p) return;
  q('#copyCode').style.display = ''; q('#shareHint').textContent = 'Paste the image anywhere (Discord, messages). Friends with LoLStat can paste the share code on their Profile page to compare.';
  q('#shareModal').classList.add('on'); await ensureChampIcons(); await drawCard(p);
  q('#copyCode').onclick = async () => { const c = encodeShare(p); try { await navigator.clipboard.writeText(c); toastMsg('Share code copied. Send it to a friend.'); } catch(e){ prompt('Copy this share code', c); } };
  q('#copyImg').onclick = () => q('#card').toBlob(async b => { try { await navigator.clipboard.write([new ClipboardItem({'image/png': b})]); toastMsg('Stats card copied. Paste it anywhere.'); } catch(e){ toastMsg('Copying images isn’t allowed here. Use Save image instead.'); } });
  q('#saveImg').onclick = async () => { let png; try { png = q('#card').toDataURL('image/png'); } catch(e){ toastMsg('Couldn’t make the image. Try again.'); return; } try { await api('/api/save_card', {png, name: p.name}); } catch(e){} };
}

// ---------------- friends leaderboard (fills in by itself)
let frSort = 'rank';
const FR_SORTS = [['rank','Rank'],['wr','Win rate'],['kda','KDA'],['dpm','Damage'],['games','Games'],['streak','Streak']];
q('#frSort').innerHTML = FR_SORTS.map(([k,l])=>`<button data-k="${k}" class="${k===frSort?'on':''}">${l}</button>`).join('');
q('#frSort').onclick = e => { const b = e.target.closest('button'); if (!b) return; frSort = b.dataset.k; document.querySelectorAll('#frSort button').forEach(x=>x.classList.toggle('on', x===b)); loadBoard(); };
function presence(f){
  if (f.me) return {cls:'on', txt:'You'};
  if (f.playing === 'inGame') return {cls:'ingame', txt: 'In game' + (f.champ ? ' as ' + f.champ : '') + (f.queue ? ' · ' + f.queue.replace(/_/g,' ').toLowerCase() : '')};
  if (f.playing === 'championSelect') return {cls:'ingame', txt:'In champ select'};
  if (f.playing === 'inQueue') return {cls:'ingame', txt:'In queue'};
  if (f.status === 'offline') return {cls:'', txt:'Offline'};
  if (f.status === 'away') return {cls:'away', txt:'Away'};
  return {cls:'on', txt:'Online'};
}
function sortVal(f){ const s = f.summary || {};
  return {rank: f.rank_score ?? -1, wr: s.games ? s.wr : -1, kda: s.games ? s.kda : -1, dpm: s.games ? s.dpm : -1, games: s.games || 0, streak: f.streak || 0}[frSort]; }
async function loadBoard(){
  if (page !== 'friends') return;
  await ensureChampIcons();
  try {
    const r = await api('/api/friends_board');
    q('#frStatus').textContent = r.status;
    const rows = r.friends.slice().sort((a,b)=> (sortVal(b) - sortVal(a)) || (presence(a).cls==='' ) - (presence(b).cls==='') || a.name.localeCompare(b.name));
    const has = rows.filter(f=>f.summary && f.summary.games >= 5 && !f.me);
    const pick = (k, lab, fmtv) => { const best = has.slice().sort((a,b)=>(b.summary[k]||0)-(a.summary[k]||0))[0]; if (!best) return '';
      return `<div class="box">${img((champIcons[best.top]||{}).icon,'',46)}<div><div class="muted" style="font-size:12px">${lab}</div><b>${esc(best.name)}</b><div class="muted" style="font-size:12px">${fmtv(best.summary[k])}</div></div></div>`; };
    const streaker = has.slice().sort((a,b)=>(b.streak||0)-(a.streak||0))[0];
    q('#frHi').innerHTML = has.length ? [pick('wr','Best win rate', v=>v+'% recent'), pick('kda','Best KDA', v=>v+' KDA'), pick('dpm','Most damage', v=>fmt(v)+' per minute'),
      streaker && streaker.streak > 1 ? `<div class="box">${img((champIcons[streaker.top]||{}).icon,'',46)}<div><div class="muted" style="font-size:12px">Hottest streak</div><b>${esc(streaker.name)}</b><div class="muted" style="font-size:12px">${streaker.streak} wins in a row</div></div></div>` : ''].join('') : '';
    let pos = 0;
    q('#frRows').innerHTML = `<div class="frow head"><span></span><span>Player</span><span>Solo/Duo</span><span>Win rate</span><span class="x">KDA</span><span class="x">Damage/min</span><span class="x">Streak</span><span>Main</span></div>` + rows.map(f=>{
      const s = f.summary || {}, pr = presence(f), solo = f.solo;
      pos++;
      return `<div class="frow ${f.me?'me':''}" data-n="${esc(f.name)}" data-p="${esc(f.puuid||'')}" onclick="openFriend(this.dataset.n, this.dataset.p, ${f.me?'true':'false'})">
        <span class="pos">${pos}</span>
        <div style="min-width:0"><div class="n"><span class="dot ${pr.cls}"></span>${esc(f.name)}</div><div class="p ${pr.cls==='ingame'?'ig':''}">${esc(pr.txt)}</div></div>
        <div>${f.loading ? '<span class="muted">Loading…</span>' : f.error ? '<span class="muted">Profile hidden</span>' : solo && solo.label !== 'Unranked' ? `<b>${esc(solo.label)}</b> <span class="muted">${solo.lp} LP</span>` : '<span class="muted">Unranked</span>'}</div>
        <div>${s.games ? `<b class="${s.wr>=50?'win':'loss'}">${s.wr}%</b> <span class="muted" style="font-size:11.5px">${s.games}g</span>` : '<span class="muted">–</span>'}</div>
        <div class="x">${s.games ? s.kda : '–'}</div><div class="x">${s.games ? fmt(s.dpm) : '–'}</div>
        <div class="x ${f.streak>0?'win':f.streak<0?'loss':''}">${f.streak ? (f.streak>0 ? 'W' + f.streak : 'L' + (-f.streak)) : '–'}</div>
        <div>${f.top ? img((champIcons[f.top]||{}).icon,'',40) : ''}</div></div>`; }).join('');
  } catch(e){ console.error('friends', e); }
}
function openFriend(name, puuid, me){
  go('profile');
  if (me){ viewing = null; cmpWith = null; q('#cmpOut').innerHTML = ''; loadProfile(true); return; }
  lookUp(name, puuid).then(()=>{ if (viewing && myProf) compareWithMe(); });
}
setInterval(loadBoard, 15000);

// ---------------- champion themes
let ctReady = false, ctSkins = [], ctTheme = null;
async function initCT(){
  if (ctReady) return; ctReady = true;
  await ensureChampIcons();
  const names = Object.keys(champIcons).sort();
  q('#ctChamp').innerHTML = names.map(n=>`<option>${esc(n)}</option>`).join('');
  const cur = S && S.settings.champ_theme;
  q('#ctChamp').value = cur ? cur.champion : (S && S.mayhem.champion ? S.mayhem.champion.name : names[0]);
  q('#ctChamp').onchange = () => loadSkins();
  q('#ctSkin').onchange = () => previewCT();
  q('#ctOwned').onchange = () => fillSkins();
  q('#ctUse').onclick = () => { const o = q('#ctSkin').selectedOptions[0]; if (!o) return; themeSig = '';
    act('set_value', {name:'champ_theme', value:{champion:q('#ctChamp').value, num:+o.value, skin:o.dataset.n}}); toastMsg('Theme set: ' + (o.dataset.n === 'Default' ? q('#ctChamp').value : o.dataset.n)); };
  await loadSkins(cur ? cur.num : null);
}
async function loadSkins(select){
  q('#ctSkin').innerHTML = '<option>Loading skins…</option>';
  try { const r = await api('/api/skins?champ=' + encodeURIComponent(q('#ctChamp').value)); ctSkins = r.skins; q('#ctOwned').disabled = !r.owned_known;
    q('#ctOwned').closest('label').title = r.owned_known ? '' : 'Open League to see which skins you own';
    fillSkins(select); } catch(e){}
}
function fillSkins(select){
  const only = q('#ctOwned').checked && !q('#ctOwned').disabled;
  const list = ctSkins.filter(x => !only || x.owned).sort((a,b)=> (b.owned - a.owned) || a.num - b.num);
  q('#ctSkin').innerHTML = list.map(x=>`<option value="${x.num}" data-n="${esc(x.name)}">${esc(x.name)}${x.owned && x.num ? '  ✓ owned' : ''}</option>`).join('') || '<option disabled>No owned skins for this champion</option>';
  if (select != null && list.some(x=>x.num === select)) q('#ctSkin').value = select;
  previewCT();
}
async function previewCT(){
  const o = q('#ctSkin').selectedOptions[0]; if (!o || o.disabled) return;
  const champ = q('#ctChamp').value, num = +o.value;
  const el = q('#ctPrev'); el.innerHTML = '<b>Making theme…</b>';
  try {
    const t = await api('/api/champ_theme?champ=' + encodeURIComponent(champ) + '&num=' + num + '&skin=' + encodeURIComponent(o.dataset.n));
    ctTheme = t;
    el.style.backgroundImage = t.art ? `url('/api/art?alias=${encodeURIComponent(t.alias)}&num=${t.num}&key=${encodeURIComponent(KEY)}')` : '';
    el.innerHTML = `<b>${esc(t.name)}</b><div class="sw">${[t.bg,t.panel,t.raised,t.accent,t.accent2,t.text].map(c=>`<i style="background:${c}"></i>`).join('')}</div>`;
  } catch(e){ el.innerHTML = '<b>Couldn’t load that skin</b>'; }
}
// ---------------- themes
const THEMES = {
  dark:{name:'Dark',bg:'#0c1220',panel:'#131b2e',raised:'#1a2440',line:'#26314d',text:'#ece6d6',muted:'#8e96ab',accent:'#d9b871',accent2:'#19c8b4',rail:'#0a0f1b'},
  light:{name:'Light',bg:'#eef1f6',panel:'#ffffff',raised:'#f2f4f8',line:'#d6dce7',text:'#141a26',muted:'#5b6578',accent:'#a8792a',accent2:'#0f9e8e',rail:'#e2e7ef'},
  league:{name:'League',bg:'#010a13',panel:'#091428',raised:'#0f1d33',line:'#1e2d42',text:'#f0e6d2',muted:'#a09b8c',accent:'#c8aa6e',accent2:'#0ac8b9',rail:'#010a13'},
  midnight:{name:'Midnight',bg:'#0d0b1a',panel:'#16132b',raised:'#1f1b3b',line:'#2e2855',text:'#ebe7ff',muted:'#9a93c2',accent:'#a78bfa',accent2:'#5eead4',rail:'#0a0815'},
  noxus:{name:'Noxus',bg:'#120a0a',panel:'#1d1010',raised:'#2a1616',line:'#3d2020',text:'#f3e3e0',muted:'#b08f8a',accent:'#e5484d',accent2:'#f2b33d',rail:'#0e0707'},
  ionia:{name:'Ionia',bg:'#14101a',panel:'#1e1726',raised:'#2a2034',line:'#3b2d49',text:'#f8eaf2',muted:'#b79fb1',accent:'#f28cb1',accent2:'#7ee0a6',rail:'#100c15'},
  shurima:{name:'Shurima',bg:'#17130b',panel:'#221c10',raised:'#2e2616',line:'#43381f',text:'#f5ecd7',muted:'#b7a782',accent:'#e9b949',accent2:'#3fb8c9',rail:'#120f08'},
  freljord:{name:'Freljord',bg:'#0b1419',panel:'#122029',raised:'#182b37',line:'#24404f',text:'#e8f4fa',muted:'#8fb0c2',accent:'#8fd3ff',accent2:'#c4f1ff',rail:'#081015'},
  shadow:{name:'Shadow Isles',bg:'#07120f',panel:'#0d1c18',raised:'#132722',line:'#1d3a32',text:'#dff5ec',muted:'#82ab9d',accent:'#3ee0b0',accent2:'#9be564',rail:'#050e0b'},
  bilgewater:{name:'Bilgewater',bg:'#0a1418',panel:'#102026',raised:'#162b33',line:'#21404b',text:'#eef3ef',muted:'#93aaa6',accent:'#ff8a3d',accent2:'#4cc9f0',rail:'#071013'},
  piltover:{name:'Piltover',bg:'#16110d',panel:'#211913',raised:'#2c221a',line:'#423226',text:'#f6ede2',muted:'#b9a48f',accent:'#d99a5b',accent2:'#5fb3f9',rail:'#110d0a'},
  zaun:{name:'Zaun',bg:'#0b120b',panel:'#111c11',raised:'#182618',line:'#253a23',text:'#e8f5e0',muted:'#94ad8a',accent:'#9cff3a',accent2:'#ff4fa3',rail:'#080e08'},
  targon:{name:'Targon',bg:'#0b0d1c',panel:'#12152b',raised:'#191d3a',line:'#272d55',text:'#eef0ff',muted:'#9aa1cf',accent:'#ffd36e',accent2:'#7aa2ff',rail:'#080a16'},
  void:{name:'Void',bg:'#100717',panel:'#1a0c25',raised:'#241133',line:'#3a1b50',text:'#f4e9ff',muted:'#ad8fc7',accent:'#d14bff',accent2:'#ff5c8a',rail:'#0c0512'},
  arcade:{name:'Arcade',bg:'#0a0a1f',panel:'#121236',raised:'#1a1a4a',line:'#2a2a6e',text:'#fbf5ff',muted:'#a7a3d9',accent:'#ff3fa4',accent2:'#29e7ff',rail:'#07071a'},
  mono:{name:'Monochrome',bg:'#0e0e0f',panel:'#18181a',raised:'#222225',line:'#323236',text:'#f2f2f2',muted:'#9a9aa0',accent:'#f2f2f2',accent2:'#9a9aa0',rail:'#0a0a0b'},
};
const FIELDS = [['bg','Background'],['panel','Panels'],['raised','Cards'],['line','Borders'],['text','Text'],['muted','Soft text'],['accent','Accent'],['accent2','Second accent'],['rail','Sidebar']];
const hexRgb = h => { h = h.replace('#',''); if (h.length===3) h = h.split('').map(c=>c+c).join(''); const n = parseInt(h,16); return [n>>16&255, n>>8&255, n&255]; };
const mix = (a,b,t) => { const x = hexRgb(a), y = hexRgb(b); return '#' + x.map((v,i)=>Math.round(v+(y[i]-v)*t).toString(16).padStart(2,'0')).join(''); };
const rgba = (h,a) => { const [r,g,b] = hexRgb(h); return `rgba(${r},${g},${b},${a})`; };
let themeSig = '', draft = null;
function themeOf(set){ if (set.theme === 'custom' && set.custom_theme) return set.custom_theme;
  if (set.theme === 'champ' && set.champ_theme) return set.champ_theme;
  return Object.assign({alpha:1, radius:14, overlay:0.9}, THEMES[set.theme] || THEMES.dark); }
function paint(t){
  const r = document.documentElement.style, a = t.alpha ?? 1;
  r.setProperty('--ink', t.bg); r.setProperty('--panel', rgba(t.panel, a)); r.setProperty('--raised', rgba(t.raised, Math.min(1, a + .06)));
  r.setProperty('--line', t.line); r.setProperty('--line2', mix(t.line, t.text, .12)); r.setProperty('--text', t.text); r.setProperty('--muted', t.muted);
  r.setProperty('--dim', mix(t.muted, t.bg, .35)); r.setProperty('--gold', t.accent); r.setProperty('--gold2', mix(t.accent, '#ffffff', .25));
  r.setProperty('--teal', t.accent2); r.setProperty('--rail', t.rail || t.bg); r.setProperty('--hi', mix(t.panel, t.accent2, .14)); r.setProperty('--r', (t.radius ?? 14) + 'px');
  document.body.style.background = t.bg;
  const art = q('#bgart');
  if (t.alias && t.art){ const u = `/api/art?alias=${encodeURIComponent(t.alias)}&num=${t.num||0}&key=${encodeURIComponent(KEY)}`;
    if (art.dataset.u !== u){ art.dataset.u = u; art.style.backgroundImage = `url('${u}')`; } art.classList.add('on'); }
  else art.classList.remove('on');
  const [R,G,B] = hexRgb(t.bg), light = (0.299*R + 0.587*G + 0.114*B) / 255 > 0.6;
  r.setProperty('--gS1', light ? '#c08a12' : '#f6d27a');                    // S+ gold readable on light themes
  r.setProperty('--iconbg', light ? '#2a3350' : mix(t.raised, '#000000', .25));
}
function overlayTheme(t){ return {glass: t.panel, edge: t.line, text: t.text, muted: t.muted, accent: t.accent, accent2: t.accent2, alpha: t.overlay ?? 0.9}; }
function applyThemeFrom(set){
  if (q('#ctFollow')) q('#ctFollow').checked = !!set.theme_follow;
  const sig = JSON.stringify([set.theme, set.custom_theme, set.champ_theme]);
  if (sig === themeSig || draft) return;
  themeSig = sig; const t = themeOf(set); paint(t); drawThemeGrid(set); fillCreator(t);
}
function chooseTheme(name){
  draft = null; const t = name === 'custom' ? S.settings.custom_theme : name === 'champ' ? S.settings.champ_theme : Object.assign({alpha:1, radius:14, overlay:0.9}, THEMES[name]);
  if (S.settings.theme_follow && name !== 'champ') act('setting', {name:'theme_follow'});
  if (!t) return;
  act('set_value', {name:'theme', value:name}); act('set_value', {name:'overlay_theme', value:overlayTheme(t)});
}
function drawThemeGrid(set){
  const all = Object.entries(THEMES); if (set.custom_theme) all.push(['custom', Object.assign({name:'My theme'}, set.custom_theme)]);
  if (set.champ_theme) all.unshift(['champ', set.champ_theme]);
  q('#themeGrid').innerHTML = all.map(([k,t])=>`<button class="th ${set.theme===k?'on':''}" style="background:${t.panel};color:${t.text}" onclick="chooseTheme('${k}')"><b style="font-size:13px">${esc(t.name||k)}</b><div class="sw">${[t.bg,t.raised,t.accent,t.accent2,t.text].map(c=>`<i style="background:${c}"></i>`).join('')}</div></button>`).join('');
}
function fillCreator(t){
  q('#creator').innerHTML = FIELDS.map(([k,l])=>`<label>${l}<input type="color" data-k="${k}" value="${t[k] || t.bg}"></label>`).join('');
  q('#cAlpha').value = t.alpha ?? 1; q('#cRadius').value = t.radius ?? 14; q('#cOverlay').value = t.overlay ?? 0.9;
}
function readCreator(){
  const t = {name:'My theme'}; document.querySelectorAll('#creator input').forEach(i=>t[i.dataset.k]=i.value);
  t.alpha = +q('#cAlpha').value; t.radius = +q('#cRadius').value; t.overlay = +q('#cOverlay').value; return t;
}
q('#creator').addEventListener('input', () => { draft = readCreator(); paint(draft); });
['cAlpha','cRadius','cOverlay'].forEach(id => q('#'+id).addEventListener('input', () => { draft = readCreator(); paint(draft); }));
q('#cFrom').onclick = () => { draft = null; fillCreator(themeOf(S.settings)); };
q('#cSave').onclick = () => { const t = readCreator(); draft = null; themeSig = '';
  act('set_value', {name:'custom_theme', value:t}).then(()=>{ act('set_value', {name:'theme', value:'custom'}); act('set_value', {name:'overlay_theme', value:overlayTheme(t)}); });
  q('#cSave').textContent = 'Saved'; setTimeout(()=>q('#cSave').textContent='Save custom theme', 1500); };

function champCard(c, cls, size, onclick, tag){
  const w = size, h = Math.round(size * 1.818);
  return `<button class="ccard ${cls}" style="width:${w}px;height:${h}px" data-name="${esc(c.name)}" ${onclick ? `onclick="${onclick}"` : 'tabindex="-1"'} title="${esc(c.name)}">
    <img src="${esc(c.art)}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${esc(c.icon)}'">
    ${tag ? `<span class="flag">${tag}</span>` : ''}
    ${S && S.mayhem.mode && S.mayhem.mode !== 'mayhem' ? '' : `<span class="cg">${grade(c.tier)}</span>`}
    <span class="nm"><b>${esc(c.name)}</b>${c.pick != null ? `<i>${pct(c.pick)} pick rate</i>` : ''}</span></button>`;
}
function drawChampSelect(cs){
  const el = q('#cs');
  if (!cs){ el.style.display = 'none'; return; }
  el.style.display = 'block';
  const order = g => ({'S+':0,S:1,A:2,B:3,C:4,D:5}[g] ?? 9);
  let h = '';
  if (cs.cards && cs.cards.length){
    const best = cs.cards.reduce((bi, c, i, arr) => order(c.tier) < order(arr[bi].tier) ? i : bi, 0);
    h += `<div class="cs-head"><div><div class="muted" style="font-size:12.5px">Champ select, live from your client</div><div class="cs-title">Pick your champion</div></div><div class="muted" style="font-size:12.5px">Click a card to lock it in. The other goes to your team's bench.</div></div>`;
    h += `<div class="ccards">${cs.cards.map((c,i)=>champCard(c, 'pick', 210, "act('pick',{name:this.dataset.name})", i===best ? 'Best pick' : '')).join('')}</div>`;
  } else {
    const me = cs.champion;
    h += `<div class="cs-head"><div><div class="muted" style="font-size:12.5px">Champ select, live from your client</div><div class="cs-title">${me ? 'You have ' + esc(me.name) : 'Waiting for your champion'}</div></div>`
      + (cs.bench_enabled && cs.rerolls ? `<button class="btn gold" onclick="act('reroll')">Reroll (${cs.rerolls} left)</button>` : '') + `</div>`;
    h += `<div class="cs-grid"><div>${me ? champCard(me, 'mine', 190, '', '') : '<div class="ccard empty" style="width:190px;height:345px"></div>'}</div><div style="min-width:0">`;
    if (cs.bench_enabled){
      h += `<div class="cs-sub">Bench: click a card to swap</div>` + (cs.bench.length
        ? `<div class="ccards">${cs.bench.map(b=>champCard(b, 'swap', 118, "act('swap',{name:this.dataset.name})", '')).join('')}</div>`
        : `<div class="muted" style="font-size:12.5px">The bench is empty right now.</div>`);
    }
    if (cs.team && cs.team.length) h += `<div class="cs-sub" style="margin-top:14px">Your team</div><div class="ccards">${cs.team.map(t=>champCard(t, 'mate', 86, '', '')).join('')}</div>`;
    if (cs.ban_action) h += `<div class="lock"><input id="banName" list="champNames" placeholder="Champion to ban"><button class="btn" onclick="act('ban',{name:q('#banName').value})">Ban</button></div>`;
    if (cs.pick_action) h += `<div class="lock"><input id="lockName" list="champNames" placeholder="Champion to lock in"><button class="btn gold" onclick="act('pick',{name:q('#lockName').value})">Lock in</button></div>`;
    if (cs.enemies && cs.enemies.length) h += `<div class="cs-sub" style="margin-top:14px">Enemy picks</div><div class="ccards">${cs.enemies.map(t=>champCard(t, 'mate', 86, '', '')).join('')}</div>`;
    h += `</div></div>`;
  }
  if ((cs.pick_action || cs.ban_action) && !champsLoaded){ champsLoaded = true; api('/api/champions').then(r=>{ q('#champNames').innerHTML = r.map(c=>`<option value="${esc(c.name)}">`).join(''); }); }
  if (S){ h += `<div class="auto" style="margin-top:16px">${autoHtml(S).replace(/<label class="chk">(?=[^]*?Auto-accept)/,'<label class="chk" style="display:none">')}</div><div class="spells">${spellHtml(S)}</div>`; }
  h += `<div class="muted" style="font-size:12px;margin-top:12px">${S && S.mayhem.mode === 'mayhem' ? `Grades come from daily ARAM Mayhem stats${S.mayhem.champ_date ? ' (' + esc(S.mayhem.champ_date) + ')' : ''}. ` : ''}Builds, runes and spells below update the moment your champion changes.</div>`;
  if (el.dataset.h !== h){ el.dataset.h = h; el.innerHTML = h; }
}

function card(c, best, choose){
  const tag = choose ? 'button' : 'div';
  return `<${tag} class="card tier-${esc(c.tier)} ${best?'best':''}" ${choose?`onclick="act('add_aug',{id:'${c.id}'})"`:''}>
    ${best?'<span class="flag">Best pick</span>':''}
    <span class="big ${gcls(c.grade)}">${esc(c.grade||'–')}</span>
    ${img(c.icon,'cimg',58)}
    <div class="cn">${esc(c.name)}</div>
    ${c.combo ? `<div style="margin:-2px 0 4px"><span class="tag good">Combo with ${esc(c.combo)}</span></div>` : ''}
    <div class="ct">${esc(c.text)}</div>
    <div class="picks"><span class="muted"><b>${pct(c.gpick)||'–'}</b>picked overall</span>${c.cpick!=null?`<span class="muted"><b>${pct(c.cpick)}</b>picked on ${esc(S.mayhem.champion?S.mayhem.champion.name:'')}</span>`:''}</div>
  </${tag}>`;
}

function drawPlan(m){
  if (q('#plan').dataset.ready) { return; }
  q('#plan').dataset.ready = '1';
  const slots = m.enemy_slots || ['','','','',''];
  q('#plan').innerHTML = `<div><label for="pc">Your champion</label><input id="pc" list="champNames" value="${esc(m.champion?m.champion.name:'')}" placeholder="Type a champion"></div>`
    + slots.map((s,i)=>`<div><label for="pe${i}">Enemy ${i+1}</label><input id="pe${i}" list="champNames" value="${esc(s)}" placeholder="Optional"></div>`).join('');
  q('#pc').onchange = e => act('set_champion', {name:e.target.value});
  slots.forEach((_,i)=> q('#pe'+i).onchange = e => act('set_enemy', {i, name:e.target.value}));
  if (!champsLoaded){ champsLoaded = true; api('/api/champions').then(r=>{ q('#champNames').innerHTML = r.map(c=>`<option value="${esc(c.name)}">`).join(''); }); }
}

function drawAugs(){
  document.querySelectorAll('#tierSeg button').forEach(b=>b.classList.toggle('on', b.dataset.t===tierF));
  const s = q('#augSearch').value.trim().toLowerCase();
  const rows = augs.filter(a => (!tierF || a.tier===tierF) && (!s || a.name.toLowerCase().includes(s) || a.text.toLowerCase().includes(s))).slice(0, 160);
  const champ = S && S.mayhem.champion ? S.mayhem.champion.name : '';
  q('#augList').innerHTML = rows.map(a=>`<button class="aug tier-${esc(a.tier)}" onclick="act('add_aug',{id:'${a.id}'})" title="${esc(a.text)}">${img(a.icon,'',36)}<div><div class="an">${esc(a.name)}</div><div class="at">${esc(a.tier)}</div></div><div class="ap">${a.gpick!=null?pct(a.gpick)+' picked':''}${a.cpick!=null&&champ?'<br>'+pct(a.cpick)+' on '+esc(champ):''}</div>${grade(a.grade)}</button>`).join('')
    || `<div class="muted" style="padding:10px">No augments match “${esc(s)}”.</div>`;
}

let lastTick = 0;
let stH = '';
async function loop(){ lastTick = Date.now(); let ok = false; try { const st = await api('/api/state?h=' + stH); ok = true; if (st._h !== stH){ stH = st._h; render(st); } } catch(e){ console.error(e); } finally { setTimeout(loop, ok ? 0 : 1000); } }
setInterval(() => { if (Date.now() - lastTick > 8000) loop(); }, 4000);   // watchdog: restart the refresh if it ever stops
loop();
</script>
</body></html>
"""

import ui_more  # noqa: E402  (extra screens added onto the app page)
from lolstat_assets import APP_VERSION as _V  # noqa: E402
APP_HTML = ui_more.extend8(ui_more.extend7(ui_more.extend6(ui_more.extend5(ui_more.extend4(ui_more.extend3(ui_more.extend2(ui_more.extend(APP_HTML))), _V)))))
MINI_HTML = ui_more.mini_html(BASE_CSS, COMMON_JS)

OVERLAY_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>LoLStat Overlay</title>
<style>
""" + BASE_CSS + r"""
html,body{background:transparent;overflow:hidden}
.panel{margin:0;height:100vh;background:rgba(12,18,32,.94);border:1px solid var(--line2);border-radius:14px;display:flex;flex-direction:column}
.head{display:flex;align-items:center;gap:9px;padding:10px 12px;border-bottom:1px solid var(--line);cursor:move}
.head b{font-size:13.5px}
.head .sp{flex:1}
.head .lv{font-size:11.5px;color:var(--muted)}
.body{padding:12px;flex:1;overflow:hidden}
.ttl{font-size:12px;color:var(--muted);margin:0 0 8px}
.oc{display:grid;grid-template-columns:38px 1fr auto;gap:10px;align-items:center;padding:8px;border-radius:10px;background:var(--raised);border:1px solid var(--line);margin-bottom:8px;position:relative}
.oc::before{content:"";position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:3px;background:var(--tier,var(--line2))}
.oc.best{border-color:var(--gold)}
.oc img{width:38px;height:38px;border-radius:9px}
.oc .n{font-weight:700;font-size:13px;line-height:1.2}
.oc .p{font-size:11.5px;color:var(--muted)}
.oc .grade{min-width:40px;height:32px;font-size:16px}
.side{font-size:10.5px;color:var(--dim);margin-right:2px}
.its{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.its img{width:40px;height:40px;border-radius:9px;border:1px solid var(--line2)}
.its .own{border-color:var(--teal);opacity:.55}
.ch{display:flex;flex-wrap:wrap;gap:6px}
.ch>span{display:flex;align-items:center;gap:6px;background:var(--raised);border:1px solid var(--line);border-radius:8px;padding:3px 7px 3px 3px;font-size:11.5px}
.ch img{width:22px;height:22px;border-radius:6px}
.ch .grade{min-width:24px;height:20px;font-size:11px}
.foot{padding:7px 12px;border-top:1px solid var(--line);font-size:11px;color:var(--dim);display:flex;gap:6px;align-items:center}
.foot i{width:7px;height:7px;border-radius:50%;background:var(--dim)} .foot.on i{background:var(--teal)}
@keyframes pop{from{transform:scale(.97);opacity:0}to{transform:none;opacity:1}}
.fresh .oc{animation:pop .25s ease-out both}
</style></head>
<body><div class="panel">
  <div class="head pywebview-drag-region"><img src="/logo.png" width="22" height="22" alt=""><b id="h">LoLStat</b><span class="sp"></span><span class="lv" id="lv"></span></div>
  <div class="body" id="b"></div>
  <div class="foot" id="f"><i></i><span id="fs"></span></div>
</div>
<script>
""" + COMMON_JS + r"""
const SIDE = ['Left','Middle','Right']; let last = '';
function render(st){
  const m = st.mayhem;
  q('#h').textContent = m.champion ? m.champion.name : 'LoLStat';
  q('#lv').textContent = m.live && m.level ? 'Level ' + m.level : '';
  const b = q('#b');
  if (m.offer){
    const key = m.offer.cards.map(c=>c.id).join();
    b.innerHTML = `<p class="ttl">Augment cards</p><div class="${key!==last?'fresh':''}">` + m.offer.cards.map((c,i)=>`<div class="oc tier-${esc(c.tier)} ${i===m.offer.best?'best':''}">${img(c.icon,'',38)}<div><div class="n"><span class="side">${m.offer.cards.length===3?SIDE[i]:''}</span> ${esc(c.name)}</div><div class="p">${c.gpick!=null?pct(c.gpick)+' picked':''}${c.cpick!=null?', '+pct(c.cpick)+' on '+esc(m.champion?m.champion.name:''):''}</div></div>${grade(c.grade)}</div>`).join('') + '</div>';
    last = key;
  } else {
    last = '';
    const bd = m.builds[0];
    const items = bd ? (bd.boots ? [bd.boots] : []).concat(bd.items) : [];
    b.innerHTML = (items.length ? `<p class="ttl">Max damage build</p><div class="its">${items.map(it=>`<img class="${it.owned?'own':''}" src="${esc(it.icon)}" title="${esc(it.name)}: ${esc(it.why)}" alt="${esc(it.name)}" onerror="this.style.visibility='hidden'">`).join('')}</div>` : `<p class="ttl">Builds show once your champion is known.</p>`)
      + `<p class="ttl">Your augments</p><div class="ch">${m.chosen.map(c=>`<span>${img(c.icon,'',22)}${grade(c.grade)}${esc(c.name)}</span>`).join('') || '<span style="padding:3px 7px">Picked cards appear here</span>'}</div>`;
  }
  const on = /Watching/.test(m.scanner);
  q('#f').className = 'foot' + (on ? ' on' : '');
  q('#fs').textContent = m.scanner;
}
let stH = '';
async function loop(){ let ok = false; try { const st = await api('/api/state?h=' + stH); ok = true; if (st._h !== stH){ stH = st._h; render(st); } } catch(e){} finally { setTimeout(loop, ok ? 0 : 800); } }
loop();
</script></body></html>
"""
