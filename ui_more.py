"""Extra LoLStat screens, added onto the main app page: My stats (round 1)."""

NAV = r'''  <button class="nav" data-page="stats" aria-label="My stats"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-5 4 4 8-8"/><path d="M14 8h6v6"/></svg><span class="tip">My stats</span></button>
'''

SECTION = r'''
  <!-- MY STATS -->
  <section class="page" id="p-stats">
    <div class="box"><div class="cs-head" style="margin:0"><div><h2 style="margin:0">My stats</h2><div class="muted" style="font-size:12.5px" id="stStatus"></div></div><div class="seg" id="stTabs"></div></div></div>
    <div id="stOut"></div>
  </section>
'''

CSS = r'''
/* my stats */
.st-grid{display:grid;grid-template-columns:1.3fr 1fr;gap:16px;margin-top:16px;align-items:start}
.tip-row{display:flex;gap:10px;align-items:flex-start;padding:7px 0;font-size:13.5px}
.tip-row i{flex:none;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-style:normal;font-size:12px;font-weight:800;color:#0c1220;margin-top:1px}
.tip-row i.g{background:var(--gA)}.tip-row i.b{background:var(--gD)}
.moods{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
.moods button{padding:6px 12px;border-radius:999px;border:1px solid var(--line2);background:var(--raised);font-size:12.5px}
.moods button.on{border-color:var(--gold);color:var(--gold)}
.rec{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.rec div{padding:12px;border-radius:12px;background:var(--raised);border:1px solid var(--line)}
.rec b{display:block;font-size:17px}.rec span{font-size:12px;color:var(--muted)}
.badges{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.badge{padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--raised);text-align:center}
.badge .ic{width:44px;height:44px;border-radius:50%;margin:0 auto 8px;display:grid;place-items:center;font-weight:800;font-size:18px;
  background:radial-gradient(circle at 35% 30%,var(--gold2),var(--gold));color:#1a1405;box-shadow:0 0 18px color-mix(in srgb,var(--gold) 40%,transparent)}
.badge.off{opacity:.45}.badge.off .ic{background:var(--line2);color:var(--muted);box-shadow:none}
.badge b{display:block;font-size:13px}.badge span{font-size:11.5px;color:var(--muted)}
.bars{display:flex;flex-direction:column;gap:8px}
.bar{display:grid;grid-template-columns:110px 1fr 90px;gap:10px;align-items:center;font-size:13px}
.bar .tr{height:10px;border-radius:10px;background:var(--line);overflow:hidden}
.bar .tr i{display:block;height:100%;border-radius:10px;background:var(--gA)}
.bar .tr i.low{background:var(--gD)}.bar .tr i.mid{background:var(--gold)}
.bar span{color:var(--muted);text-align:right;font-size:12px}
.lpchart svg{width:100%;height:220px;display:block}
.chips2{display:flex;gap:6px;flex-wrap:wrap}
.chips2 .tag{font-size:11.5px}
.wrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin-top:14px}
.wrap div{padding:14px;border-radius:12px;background:var(--raised);border:1px solid var(--line)}
.wrap b{display:block;font-size:24px;color:var(--gold)}.wrap span{font-size:12px;color:var(--muted)}
'''

JS = r'''
// ---------------- my stats
let stTab = 'overview', INS = null, stChamp = null;
const ST_TABS = [['overview','Overview'],['champions','Champions'],['people','Duos and rivals'],['habits','Habits'],['highlights','Highlights'],['season','Season']];
q('#stTabs').innerHTML = ST_TABS.map(([k,l])=>`<button data-k="${k}" class="${k===stTab?'on':''}">${l}</button>`).join('');
q('#stTabs').onclick = e => { const b = e.target.closest('button'); if (!b) return; stTab = b.dataset.k; document.querySelectorAll('#stTabs button').forEach(x=>x.classList.toggle('on', x===b)); drawStats(); };
async function loadStats(){
  if (page !== 'stats') return;
  await ensureChampIcons();
  try { INS = await api('/api/insights'); drawStats(); } catch(e){ console.error('stats', e); }
}
setInterval(loadStats, 20000);
const ago = t => { const d = (Date.now() - t) / 86400000; return d < 1 ? 'today' : d < 2 ? 'yesterday' : Math.round(d) + ' days ago'; };
function wrBar(b){ const cls = b.wr == null ? '' : b.wr >= 55 ? '' : b.wr >= 45 ? 'mid' : 'low';
  return `<div class="bar"><b>${esc(b.label)}</b><div class="tr"><i class="${cls}" style="width:${b.wr ?? 0}%"></i></div><span>${b.wr != null ? b.wr + '% · ' + b.games + 'g' : 'no games'}</span></div>`; }
function lpChart(lp){
  const qs = [['RANKED_SOLO_5x5','Solo/Duo','var(--gold)'],['RANKED_FLEX_SR','Flex','var(--teal)']];
  const pts = lp.filter(x=>qs.some(q=>q[0]===x.q));
  if (pts.length < 2) return `<div class="muted">Your LP graph builds up as you play ranked games.</div>`;
  const W = 900, H = 220, min = Math.min(...pts.map(p=>p.score)) - 30, max = Math.max(...pts.map(p=>p.score)) + 30;
  const t0 = pts[0].t, t1 = pts[pts.length-1].t || t0 + 1;
  const X = t => 40 + (t - t0) / Math.max(1, t1 - t0) * (W - 60), Y = v => H - 20 - (v - min) / Math.max(1, max - min) * (H - 40);
  const T = ['Iron','Bronze','Silver','Gold','Platinum','Emerald','Diamond','Master','Grandmaster','Challenger'];
  let g = '';
  for (let s = Math.ceil(min / 400) * 400; s <= max; s += 400) g += `<line x1="40" x2="${W-20}" y1="${Y(s)}" y2="${Y(s)}" stroke="var(--line)" stroke-dasharray="4 4"/><text x="0" y="${Y(s)+4}" fill="var(--muted)" font-size="11">${T[s/400] || ''}</text>`;
  for (const [qid, name, col] of qs){ const p = pts.filter(x=>x.q===qid); if (p.length < 1) continue;
    g += `<polyline fill="none" stroke="${col}" stroke-width="2.5" points="${p.map(x=>X(x.t)+','+Y(x.score)).join(' ')}"/>` + p.map(x=>`<circle cx="${X(x.t)}" cy="${Y(x.score)}" r="3.5" fill="${col}"><title>${name}: ${x.label} ${x.lp} LP, ${new Date(x.t).toLocaleDateString()}</title></circle>`).join(''); }
  return `<div class="lpchart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="LP over time">${g}</svg></div><div class="muted" style="font-size:12px"><span style="color:var(--gold)">●</span> Solo/Duo &nbsp; <span style="color:var(--teal)">●</span> Flex</div>`;
}
function coachHtml(c, notes){
  if (!c) return `<div class="muted">Play a game and your recap appears here.</div>`;
  const n = (notes||{})[c.id] || {};
  return `<div style="font-size:16px;font-weight:700">${esc(c.headline)}</div><div class="muted" style="font-size:12.5px;margin:4px 0 8px">${esc(c.queue)}, ${c.minutes} min · ${c.k}/${c.d}/${c.a} · ${fmt(c.dmg)} damage</div>`
    + (c.tips.length ? c.tips.map(t=>`<div class="tip-row"><i class="${t.good?'g':'b'}">${t.good?'+':'!'}</i><span>${esc(t.text)}</span></div>`).join('') : '<div class="muted">Pretty average game for you. Nothing stood out.</div>')
    + `<div class="moods"><span class="muted" style="font-size:12.5px">How did it feel?</span>${[['good','Felt good'],['okay','Okay'],['tilted','Tilted']].map(([k,l])=>`<button class="${n.mood===k?'on':''}" onclick="act('journal',{id:${c.id},mood:'${k}'}).then(()=>setTimeout(loadStats,300))">${l}</button>`).join('')}
       <input id="noteIn" value="${esc(n.text||'')}" placeholder="Add a note (optional)" style="flex:1;min-width:160px;background:var(--raised);border:1px solid var(--line2);border-radius:9px;padding:6px 10px" onchange="act('journal',{id:${c.id},text:this.value})"></div>`;
}
function drawStats(){
  const I = INS, el = q('#stOut');
  if (!I) return;
  q('#stStatus').textContent = I.count ? `${I.count} games saved on this PC${I.syncing ? ' · adding new games…' : ''}` : (I.connected ? 'Collecting your games from League. This takes a minute the first time.' : 'Open League to start collecting your games.');
  if (!I.count){ el.innerHTML = `<div class="box muted" style="margin-top:16px">Your stats appear here once LoLStat has saved some games.</div>`; return; }
  const ci = n => (champIcons[n]||{}).icon, o = I.overview;
  let h = '';
  if (stTab === 'overview'){
    h = `<div class="sum" style="margin-top:16px">${[[o.games,'games saved'],[o.wr+'%','win rate'],[o.kda,'KDA'],[fmt(o.dpm),'damage per minute'],[I.streak>0?'W'+I.streak:I.streak<0?'L'+(-I.streak):'–','current streak'],[o.hours+'h','played']].slice(0,4).map(([v,l])=>`<div class="box"><div class="stat">${v}</div><div class="muted" style="font-size:12.5px">${l}</div></div>`).join('')}</div>`
      + `<div class="st-grid"><div class="box"><h2>Last game recap</h2>${coachHtml(I.coach, I.notes)}</div><div class="box"><h2>LP over time</h2>${lpChart(I.lp)}</div></div>`
      + `<div class="box" style="margin-top:16px"><h2>Personal records</h2><div class="rec">${I.records.map(r=>`<div><span>${esc(r.label)}</span><b>${esc(r.value)}</b><span>${esc(r.champ)} · ${esc(r.queue)} · ${ago(r.when)}</span></div>`).join('')}</div></div>`
      + `<div class="box" style="margin-top:16px"><h2>Badges <span class="muted" style="font-size:13px;font-weight:500">${I.badges.filter(b=>b.got).length} of ${I.badges.length}</span></h2><div class="badges">${I.badges.slice().sort((a,b)=>b.got-a.got).map(b=>`<div class="badge ${b.got?'':'off'}"><div class="ic">${b.got?'★':'?'}</div><b>${esc(b.name)}</b><span>${esc(b.how)}</span></div>`).join('')}</div></div>`;
  } else if (stTab === 'champions'){
    stChamp = stChamp || (I.champions[0]||{}).champion;
    h = `<div class="st-grid"><div class="box"><h2>Your champions</h2>${I.champions.map(c=>`<div class="ctab" style="cursor:pointer" onclick="stChamp=this.dataset.c;drawStats()" data-c="${esc(c.champion)}">${img(ci(c.champion),'',36)}<b>${esc(c.champion)}</b><span>${c.games} games</span><span class="${c.wr>=50?'win':'loss'}">${c.wr}%</span><span class="muted">${stChamp===c.champion?'Showing':''}</span></div>`).join('')}</div><div class="box" id="journeyBox"><div class="muted">Loading…</div></div></div>`;
    el.innerHTML = h; loadJourney(stChamp); return;
  } else if (stTab === 'people'){
    const row = (r, kind) => `<div class="ctab" style="grid-template-columns:36px 1fr auto auto auto;cursor:pointer" data-n="${esc(r.name)}" data-p="${esc(r.puuid)}" onclick="openFriend(this.dataset.n,this.dataset.p,false)">${img(ci(r.main),'',36)}<div><b>${esc(r.name)}</b><div class="muted" style="font-size:11.5px">${kind}${r.premade?' · played together often':''} · last ${ago(r.last)}</div></div><span>${r.games} games</span><span class="${r.wr>=50?'win':'loss'}">${r.wr}%</span><span class="muted">${esc(r.main)}</span></div>`;
    h = `<div class="two"><div class="box"><h2>Duo partners</h2><div class="muted" style="font-size:12.5px;margin-bottom:6px">Your win rate when they're on your team.</div>${I.people.duos.map(r=>row(r,'Teammate')).join('') || '<div class="muted">Play with a friend and they show up here.</div>'}</div>`
      + `<div class="box"><h2>Rivals</h2><div class="muted" style="font-size:12.5px;margin-bottom:6px">Players you keep meeting on the enemy team, and your record against them.</div>${I.people.rivals.map(r=>row(r,'Enemy')).join('') || '<div class="muted">No repeat opponents yet.</div>'}</div></div>`;
  } else if (stTab === 'habits'){
    const H = I.habits, notes = I.notes || {}, moods = {};
    (I.recent||[]).forEach(g=>{ const m = (notes[g.id]||{}).mood; if (!m) return; const b = moods[m] = moods[m] || {label: {good:'Felt good',okay:'Okay',tilted:'Tilted'}[m], games:0, wins:0}; b.games++; b.wins += g.win; });
    const moodBars = Object.values(moods).map(b=>Object.assign(b,{wr:Math.round(b.wins/b.games*100)}));
    const best = H.time.filter(b=>b.games>=3).sort((a,b)=>b.wr-a.wr)[0], sess = H.session.filter(b=>b.games>=3);
    const tired = sess.length >= 2 && sess[sess.length-1].wr != null && sess[0].wr != null && sess[sess.length-1].wr < sess[0].wr - 8;
    h = `<div class="box" style="margin-top:16px"><h2>What the numbers say</h2>${best ? `<div class="tip-row"><i class="g">+</i><span>Your best time to play is the <b>${esc(best.label.toLowerCase())}</b> (${best.wr}% win rate).</span></div>` : ''}${tired ? `<div class="tip-row"><i class="b">!</i><span>Your win rate drops the longer you play in one sitting (${sess[0].wr}% in game 1, ${sess[sess.length-1].wr}% by ${esc(sess[sess.length-1].label.toLowerCase())}). Short breaks help.</span></div>` : ''}</div>`
      + `<div class="two"><div class="box"><h2>Time of day</h2><div class="bars">${H.time.map(wrBar).join('')}</div><h2 style="margin-top:18px">Day of the week</h2><div class="bars">${H.day.map(wrBar).join('')}</div></div>`
      + `<div><div class="box"><h2>Games in a row</h2><div class="bars">${H.session.map(wrBar).join('')}</div></div><div class="box" style="margin-top:16px"><h2>Game length</h2><div class="bars">${H.length.map(wrBar).join('')}</div></div>`
      + `<div class="box" style="margin-top:16px"><h2>Modes</h2><div class="bars">${H.queue.slice(0,6).map(wrBar).join('')}</div></div>`
      + `<div class="box" style="margin-top:16px"><h2>Mood</h2>${moodBars.length ? `<div class="bars">${moodBars.map(wrBar).join('')}</div>` : '<div class="muted">Tap how a game felt on the Overview recap and it shows up here.</div>'}</div></div></div>`;
  } else if (stTab === 'highlights'){
    h = `<div class="box" style="margin-top:16px"><h2>Highlights</h2><div class="muted" style="font-size:12.5px;margin-bottom:6px">Your standout games. Replays work for games on the current patch.</div>` + (I.highlights.map(x=>`<div class="mrow ${x.win?'w':'l'}" style="grid-template-columns:44px 1fr 1fr 2fr auto">${img(ci(x.champ),'c',44)}<div><b>${esc(x.champ)}</b><div class="muted" style="font-size:12px">${esc(x.queue)}, ${ago(x.when)}</div></div><div><b>${x.k}/${x.d}/${x.a}</b><div class="muted" style="font-size:12px">${fmt(x.dmg)} damage</div></div><div class="chips2">${x.tags.map(t=>`<span class="tag good">${esc(t)}</span>`).join('')}</div><button class="btn" onclick="act('replay',{id:${x.id}})">Replay</button></div>`).join('') || '<div class="muted">Big games show up here.</div>') + `</div>`;
  } else if (stTab === 'season'){
    const s = I.season;
    h = s.games ? `<div class="box" style="margin-top:16px"><div class="cs-head" style="margin:0"><h2 style="margin:0">Your ${s.year} so far</h2><button class="btn gold" onclick="openSeasonShare()">Share season card</button></div>
      <div class="wrap">${[[s.games,'games'],[s.hours+'h','played'],[s.wr+'%','win rate'],[fmt(s.kills),'kills'],[fmt(s.damage),'damage to champions'],[s.pentas,'pentakills'],[s.best_streak,'longest win streak'],[s.champions,'champions played'],[s.best_month,'busiest month'],[s.fav_mode,'favorite mode']].map(([v,l])=>`<div><b>${esc(v)}</b><span>${l}</span></div>`).join('')}</div>
      <h2 style="margin-top:18px">Top champions</h2>${s.top.map(c=>`<div class="ctab">${img(ci(c.champion),'',36)}<b>${esc(c.champion)}</b><span>${c.games} games</span><span class="${c.wr>=50?'win':'loss'}">${c.wr}%</span><span></span></div>`).join('')}</div>` : `<div class="box muted" style="margin-top:16px">No games saved for this year yet.</div>`;
  }
  el.innerHTML = h;
}
async function loadJourney(champ){
  if (!champ) return;
  try { const j = await api('/api/journey?champ=' + encodeURIComponent(champ)); const el = q('#journeyBox'); if (!el) return;
    if (!j.games){ el.innerHTML = '<div class="muted">No games on this champion.</div>'; return; }
    const W = 520, H = 140, tr = j.trend, X = i => 10 + i / Math.max(1, tr.length - 1) * (W - 20), Y = v => H - 10 - v / 100 * (H - 20);
    const s = j.summary;
    el.innerHTML = `<div class="chero">${img((champIcons[champ]||{}).icon,'',72)}<div><div style="font-size:20px;font-weight:700">${esc(champ)}</div><div class="muted" style="font-size:12.5px">${j.games} games since ${new Date(j.first).toLocaleDateString()} · last played ${ago(j.last)}</div></div></div>
      <div class="livestats">${[[s.wr+'%','win rate'],[s.kda,'KDA'],[fmt(s.dpm),'damage/min'],[s.csm,'CS/min']].map(([v,l])=>`<div><b>${v}</b>${l}</div>`).join('')}</div>
      <h2 style="margin-top:16px">Win rate over time</h2><svg viewBox="0 0 ${W} ${H}" style="width:100%;height:140px"><line x1="10" x2="${W-10}" y1="${Y(50)}" y2="${Y(50)}" stroke="var(--line)" stroke-dasharray="4 4"/><polyline fill="none" stroke="var(--gold)" stroke-width="2.5" points="${tr.map((p,i)=>X(i)+','+Y(p.wr)).join(' ')}"/>${tr.map((p,i)=>`<circle cx="${X(i)}" cy="${Y(p.wr)}" r="3" fill="${p.win?'var(--gA)':'var(--gD)'}"/>`).join('')}</svg>
      <h2 style="margin-top:12px">Best game</h2><div class="mrow ${j.best.win?'w':'l'}" style="grid-template-columns:1fr 1fr auto;padding-left:14px"><div><b>${j.best.k}/${j.best.d}/${j.best.a}</b><div class="muted" style="font-size:12px">${esc(j.best.queue)}, ${ago(j.best.when)}</div></div><div><b>${fmt(j.best.dmg)}</b><div class="muted" style="font-size:12px">damage</div></div><button class="btn" onclick="act('replay',{id:${j.best.id}})">Replay</button></div>`;
  } catch(e){ console.error('journey', e); }
}
async function openSeasonShare(){
  const s = INS && INS.season; if (!s) return;
  q('#shareModal').classList.add('on'); q('#copyCode').style.display = 'none'; q('#shareHint').textContent = 'Paste the image anywhere: Discord, messages, social media.';
  const cv = q('#card'), x = cv.getContext('2d'), css = getComputedStyle(document.documentElement), v = n => css.getPropertyValue(n).trim(), F = "'Sora','Segoe UI',sans-serif";
  const W = cv.width, H = cv.height, g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, v('--ink')); g.addColorStop(1, v('--hi') || v('--panel'));
  x.fillStyle = g; x.fillRect(0, 0, W, H); x.strokeStyle = v('--gold'); x.lineWidth = 3; x.strokeRect(1.5, 1.5, W - 3, H - 3);
  const logo = await loadImg('/logo.png'); if (logo) x.drawImage(logo, 40, 36, 56, 56);
  x.fillStyle = v('--text'); x.font = `800 40px ${F}`; x.fillText(`${INS.name || (myProf||{}).name || 'My season'} · ${s.year} in League`, 112, 76);
  x.fillStyle = v('--muted'); x.font = `500 18px ${F}`; x.fillText('Season so far, made with LoLStat', 114, 104);
  const cells = [[s.games,'games'],[s.hours+'h','played'],[s.wr+'%','win rate'],[fmt(s.kills),'kills'],[fmt(s.damage),'damage'],[s.pentas,'pentakills'],[s.best_streak,'win streak'],[s.champions,'champions']];
  cells.forEach(([val, lab], i)=>{ const bx = 40 + (i % 4) * 262, by = 140 + Math.floor(i / 4) * 120; x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(bx, by, 246, 104);
    x.fillStyle = v('--gold'); x.font = `800 38px ${F}`; x.fillText(String(val), bx + 16, by + 52); x.fillStyle = v('--muted'); x.font = `500 16px ${F}`; x.fillText(lab, bx + 16, by + 84); });
  x.fillStyle = v('--muted'); x.font = `600 16px ${F}`; x.fillText('Top champions', 40, 410);
  for (let i = 0; i < s.top.length; i++){ const c = s.top[i], bx = 40 + i * 350, by = 426; const im = await loadImg((champIcons[c.champion]||{}).icon);
    x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(bx, by, 330, 84); if (im){ try { x.drawImage(im, bx + 12, by + 12, 60, 60); } catch(e){} }
    x.fillStyle = v('--text'); x.font = `700 20px ${F}`; x.fillText(c.champion, bx + 84, by + 36); x.fillStyle = v('--muted'); x.font = `500 14px ${F}`; x.fillText(`${c.games} games · ${c.wr}% win rate`, bx + 84, by + 60); }
  x.fillStyle = v('--dim'); x.font = `500 13px ${F}`; x.fillText(`Favorite mode: ${s.fav_mode} · busiest month: ${s.best_month} · Not endorsed by Riot Games`, 40, H - 28);
  q('#copyImg').onclick = () => q('#card').toBlob(async b => { try { await navigator.clipboard.write([new ClipboardItem({'image/png': b})]); toastMsg('Season card copied. Paste it anywhere.'); } catch(e){ toastMsg('Copying images isn’t allowed here. Use Save image instead.'); } });
  q('#saveImg').onclick = async () => { try { await api('/api/save_card', {png: q('#card').toDataURL('image/png'), name: 'season-' + s.year}); } catch(e){} };
}
'''


def extend(html):
    html = html.replace('''  <button class="nav" data-page="games" aria-label="Games">''', NAV + '''  <button class="nav" data-page="games" aria-label="Games">''', 1)
    html = html.replace('''  <!-- GAMES -->''', SECTION + '''  <!-- GAMES -->''', 1)
    html = html.replace('''/* champ select */''', CSS + '''/* champ select */''', 1)
    html = html.replace('''let lastTick = 0;''', JS + '''let lastTick = 0;''', 1)
    html = html.replace('''if (p==='friends') loadBoard();''', '''if (p==='friends') loadBoard(); if (p==='stats') loadStats();''', 1)
    html = html.replace('''profile:'Profile', friends:'Friends',''', '''profile:'Profile', friends:'Friends', stats:'My stats',''', 1)
    return html


# ====================================================================== round 2: quality of life
HOME_EXTRA = r'''
    <div class="homegrid" style="margin-top:16px">
      <div class="box" id="queueBox"><div class="muted">Queue</div><div class="stat" id="qTime">–</div><div class="muted" style="font-size:12.5px" id="qSub">Not in queue</div></div>
      <div class="box" id="goalBox"></div>
      <div class="box"><div class="muted">Quick actions</div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px"><button class="btn" onclick="act('mini')">Mini mode</button><button class="btn" id="dndBtn" onclick="act('setting',{name:'dnd'})">Do not disturb</button><button class="btn" onclick="openSearch()">Search</button></div><div class="muted" style="font-size:12px;margin-top:8px" id="dndNote"></div></div>
    </div>'''

SETTINGS_EXTRA = r'''
    <div class="box" style="max-width:860px;margin-top:16px" id="setQol">
      <h2>Notifications</h2>
      <div class="auto" id="setNotify"></div>
      <h2 style="margin-top:18px">Window and performance</h2>
      <div class="auto" id="setWindow"></div>
      <h2 style="margin-top:18px">Hotkey</h2>
      <div class="spells"><span class="muted" style="font-size:12.5px">Open and close the in-game panel with</span>
        <select id="hkMods" aria-label="Hotkey modifier keys"><option value="ctrl+shift">Ctrl + Shift</option><option value="ctrl+alt">Ctrl + Alt</option><option value="alt+shift">Alt + Shift</option><option value="ctrl">Ctrl</option><option value="alt">Alt</option></select>
        <span class="muted">+</span><select id="hkKey" aria-label="Hotkey key"></select><span class="muted" style="font-size:12px" id="hkState"></span></div>
      <h2 style="margin-top:18px">Champ select helpers</h2>
      <div class="muted" style="font-size:12.5px">Champions you like to pick and ban. In champ select they show up as one-click buttons when it's your turn. LoLStat never picks or bans by itself.</div>
      <div class="two" style="margin-top:10px"><div><b style="font-size:13px">Pick list</b><div class="chips" id="pickChips" style="margin-top:6px"></div><div class="lock" style="margin-top:6px"><input id="pickAdd" list="champNames" placeholder="Add a champion"><button class="btn" onclick="listAdd('pick_list','#pickAdd')">Add</button></div></div>
        <div><b style="font-size:13px">Ban list</b><div class="chips" id="banChips" style="margin-top:6px"></div><div class="lock" style="margin-top:6px"><input id="banAdd" list="champNames" placeholder="Add a champion"><button class="btn" onclick="listAdd('ban_list','#banAdd')">Add</button></div></div></div>
      <h2 style="margin-top:18px">Favorite champions</h2>
      <div class="muted" style="font-size:12.5px">Star champions on the Champions page. LoLStat can keep its item sets for all of them in your client, ready in any game.</div>
      <div class="chips" id="favChips" style="margin-top:8px"></div>
      <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap"><label class="chk" style="padding:9px 12px"><input type="checkbox" id="favSets" onchange="act('setting',{name:'fav_itemsets'})"><div><b>Keep item sets for all favorites</b></div></label><button class="btn" onclick="act('fav_sets_now')">Save them now</button></div>
      <h2 style="margin-top:18px">Accessibility</h2>
      <div class="slider"><label for="txtScale">Text size</label><input type="range" id="txtScale" min="0.85" max="1.4" step="0.05"><span class="muted" id="txtScaleV" style="width:44px;text-align:right"></span></div>
      <div class="auto" id="setA11y"></div>
      <h2 style="margin-top:18px">Backup and restore</h2>
      <div class="muted" style="font-size:12.5px">Saves your settings, themes, game archive, records and journal to one file in Documents\LoLStat Backups.</div>
      <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap"><button class="btn gold" onclick="act('backup')">Back up now</button><label class="btn" style="cursor:pointer">Restore from a file<input type="file" id="restoreIn" accept=".zip" style="display:none"></label></div>
    </div>'''

SEARCH_MODAL = r'''
  <div class="modal" id="searchModal" role="dialog" aria-modal="true" aria-label="Search"><div class="sheet" style="max-width:640px;align-self:start;margin-top:8vh">
    <input id="sq" placeholder="Search champions, augments, friends, pages, settings…" aria-label="Search" style="width:100%;font-size:16px;padding:12px 14px;background:var(--raised);border:1px solid var(--line2);border-radius:12px">
    <div id="sres" style="margin-top:10px;max-height:55vh;overflow:auto"></div>
    <div class="muted" style="font-size:11.5px;margin-top:8px">Enter opens the first result · Esc closes</div>
  </div></div>'''

CSS2 = r'''
/* round 2 */
.sres{display:grid;grid-template-columns:34px 1fr auto;gap:10px;align-items:center;padding:8px;border-radius:10px;cursor:pointer;width:100%;text-align:left}
.sres:hover,.sres.sel{background:var(--raised)}
.sres img,.sres .ph{width:34px;height:34px;border-radius:8px;background:var(--raised)}
.sres small{color:var(--muted);font-size:11.5px}
.searchbtn{display:inline-flex;gap:8px;align-items:center;padding:6px 12px;border-radius:999px;background:var(--panel);border:1px solid var(--line);color:var(--muted);font-size:12.5px}
.searchbtn kbd{font:inherit;font-size:11px;border:1px solid var(--line2);border-radius:5px;padding:0 5px}
.progress{height:10px;border-radius:10px;background:var(--line);overflow:hidden;margin-top:8px}.progress i{display:block;height:100%;background:var(--teal);border-radius:10px}
.star{font-size:20px;line-height:1;color:var(--dim);padding:4px 8px;border-radius:8px}.star.on{color:var(--gold)}
.suggest{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
.suggest button{display:flex;align-items:center;gap:6px;padding:4px 10px 4px 4px;border-radius:999px;background:var(--raised);border:1px solid var(--line2);font-size:12.5px}
.suggest button:hover{border-color:var(--gold)}.suggest img{width:26px;height:26px;border-radius:50%}
.pin{font-size:11.5px;padding:3px 8px;border-radius:7px;border:1px solid var(--line2);margin-left:8px;color:var(--muted)}.pin.on{color:#1a1405;background:var(--gold);border-color:var(--gold)}
html.cb{--gA:#3b8fe8;--gD:#f08a24;--gB:#a78bfa}
html.rm *{animation:none!important;transition:none!important}
'''

JS2 = r'''
// ---------------- round 2: home extras, search, settings, favorites, helpers
function fmtSec(s){ s = Math.max(0, Math.round(s)); return Math.floor(s/60) + ':' + String(s%60).padStart(2,'0'); }
function drawQol(st){
  const qi = st.accept.queue, ph = st.accept.phase;
  if (qi && qi.penalty > 0){ q('#qTime').textContent = fmtSec(qi.penalty); q('#qSub').textContent = 'Queue penalty: you can queue again after this timer'; }
  else if (qi && qi.in_queue){ q('#qTime').textContent = fmtSec(qi.time); q('#qSub').textContent = qi.estimate ? 'Estimated ' + fmtSec(qi.estimate) : 'In queue'; }
  else { q('#qTime').textContent = ph === 'ChampSelect' ? 'Champ select' : ph === 'InProgress' ? 'In game' : '–'; q('#qSub').textContent = 'Not in queue'; }
  const g = st.goal, gb = q('#goalBox'), sig = JSON.stringify(g) + (st.settings.goal_type||'');
  if (gb.dataset.sig !== sig){ gb.dataset.sig = sig;
    const label = {wins:'wins', games:'games', lp:'LP gained'};
    gb.innerHTML = g ? `<div class="muted">Today's goal</div><div class="stat">${g.now} / ${g.target}</div><div class="muted" style="font-size:12.5px">${g.done ? 'Goal reached. Nice work.' : label[g.type] + ' today'}</div><div class="progress"><i style="width:${Math.min(100, Math.max(0, g.now / g.target * 100))}%"></i></div><button class="btn" style="margin-top:10px" onclick="act('goal',{type:'',target:0})">Clear goal</button>`
      : `<div class="muted">Today's goal</div><div class="spells" style="margin-top:8px"><select id="gType"><option value="wins">Wins</option><option value="games">Games</option><option value="lp">LP gained</option></select><input id="gTarget" type="number" min="1" max="999" value="3" style="width:70px;background:var(--raised);border:1px solid var(--line2);border-radius:9px;padding:7px"><button class="btn gold" onclick="act('goal',{type:q('#gType').value,target:+q('#gTarget').value})">Set goal</button></div><div class="muted" style="font-size:12px;margin-top:6px">Tracks today's games from the League client.</div>`; }
  q('#dndBtn').classList.toggle('gold', !!st.settings.dnd);
  q('#dndNote').textContent = st.dnd_active ? 'Notifications are paused' + (st.settings.dnd ? '.' : ' during ranked.') : '';
  // accessibility
  const H = document.documentElement;
  H.classList.toggle('cb', !!st.settings.colorblind); H.classList.toggle('rm', !!st.settings.reduce_motion);
  const sc = +(st.settings.text_scale || 1); if (document.body.style.zoom != sc) document.body.style.zoom = sc;
  if (page === 'settings') drawSetQol(st);
}
const toggleRow = (st, rows) => rows.map(([k,t,d])=>`<label class="chk"><input type="checkbox" ${st.settings[k]?'checked':''} onchange="act('setting',{name:'${k}'})"><div><b>${t}</b><span>${d}</span></div></label>`).join('');
function drawSetQol(st){
  const sig = JSON.stringify([st.settings, st.mayhem.hotkeys]);
  if (q('#setQol').dataset.sig === sig) return; q('#setQol').dataset.sig = sig;
  q('#setNotify').innerHTML = toggleRow(st, [['notify','Windows notifications','Match found, post-game recap, friends online'],['notify_friends','Friends coming online','A pop-up when a friend logs in'],['dnd','Do not disturb','Pause all pop-ups'],['dnd_ranked','Quiet during ranked','Pause pop-ups in ranked games automatically']]);
  q('#setWindow').innerHTML = toggleRow(st, [['close_to_tray','Keep running in the tray when closed','Off: closing the window quits LoLStat completely. On: it keeps working in the tray'],['start_hidden','Start in the tray','Open hidden when Windows starts'],['show_on_league','Show when League opens','Bring LoLStat up when the client starts'],['perf_mode','Performance mode','Do less in the background while you play']]);
  q('#setA11y').innerHTML = toggleRow(st, [['colorblind','Colorblind-friendly colors','Blue and orange instead of green and red'],['reduce_motion','Reduce motion','Turn off animations']]);
  q('#hkMods').value = st.settings.hotkey_mods || 'ctrl+shift';
  if (!q('#hkKey').options.length) q('#hkKey').innerHTML = 'ABCDEFGHIJKLMNOPQRTUVWXYZ'.split('').map(c=>`<option>${c}</option>`).join('');
  q('#hkKey').value = (st.settings.hotkey_key || 'L').toUpperCase();
  q('#hkState').textContent = st.mayhem.hotkeys || '';
  const chips = (lst, name) => (st.settings[lst]||[]).map(n=>`<span class="chip">${img((champIcons[n]||{}).icon,'',26)}<span>${esc(n)}</span><button class="x" aria-label="Remove ${esc(n)}" data-n="${esc(n)}" onclick="act('list_edit',{list:'${lst}',name:this.dataset.n,remove:true})">✕</button></span>`).join('') || `<span class="muted" style="font-size:12.5px">None yet</span>`;
  q('#pickChips').innerHTML = chips('pick_list'); q('#banChips').innerHTML = chips('ban_list');
  q('#favChips').innerHTML = (st.settings.favorites||[]).map(n=>`<span class="chip">${img((champIcons[n]||{}).icon,'',26)}<span>${esc(n)}</span><button class="x" data-n="${esc(n)}" aria-label="Unfavorite ${esc(n)}" onclick="act('favorite',{name:this.dataset.n})">✕</button></span>`).join('') || `<span class="muted" style="font-size:12.5px">No favorites yet</span>`;
  q('#favSets').checked = !!st.settings.fav_itemsets;
  if (document.activeElement !== q('#txtScale')) q('#txtScale').value = st.settings.text_scale || 1;
  q('#txtScaleV').textContent = Math.round((st.settings.text_scale||1)*100) + '%';
}
function listAdd(list, sel){ const v = q(sel).value.trim(); if (!v) return; act('list_edit',{list, name:v}); q(sel).value = ''; }
q('#hkMods').onchange = () => act('set_value',{name:'hotkey_mods', value:q('#hkMods').value});
q('#hkKey').onchange = () => act('set_value',{name:'hotkey_key', value:q('#hkKey').value});
q('#txtScale').oninput = e => { document.body.style.zoom = e.target.value; q('#txtScaleV').textContent = Math.round(e.target.value*100) + '%'; };
q('#txtScale').onchange = e => act('set_value',{name:'text_scale', value:+e.target.value});
q('#restoreIn').onchange = e => { const f = e.target.files[0]; if (!f) return; const r = new FileReader();
  r.onload = async () => { try { const res = await api('/api/restore', {data: r.result}); toastMsg(res.ok ? `Backup restored (${res.files} files)` : 'Couldn’t restore: ' + res.error); themeSig = ''; } catch(err){ toastMsg('Couldn’t restore that file.'); } };
  r.readAsDataURL(f); e.target.value = ''; };
// ---------------- search palette (Ctrl+K)
let sRows = [], sSel = 0, sAugs = null, sFriends = [];
const SEARCH_PAGES = [['home','Home'],['mayhem','Champ select and builds'],['live','Live game scouting'],['champs','Champions'],['profile','Profile'],['friends','Friends'],['stats','My stats'],['games','Games and damage'],['settings','Settings']];
const SEARCH_SETTINGS = [['Themes and champion themes','#themeGrid'],['Notifications','#setNotify'],['Hotkey','#hkMods'],['Champ select helpers','#pickChips'],['Favorite champions','#favChips'],['Accessibility','#txtScale'],['Backup and restore','#restoreIn'],['Automation (auto-accept, item sets, runes, spells)','#autoBox'],['Troubleshooting','#trouble']];
async function openSearch(){
  q('#searchModal').classList.add('on'); q('#sq').value = ''; q('#sq').focus(); await ensureChampIcons();
  if (!sAugs) try { sAugs = await api('/api/augments'); } catch(e){ sAugs = []; }
  try { sFriends = (await api('/api/friends_board')).friends; } catch(e){}
  runSearch();
}
function closeSearch(){ q('#searchModal').classList.remove('on'); }
function runSearch(){
  const t = q('#sq').value.trim().toLowerCase(), hit = s => !t || s.toLowerCase().includes(t);
  sRows = [];
  SEARCH_PAGES.filter(([k,l])=>hit(l)).forEach(([k,l])=>sRows.push({kind:'Page', name:l, go:()=>go(k)}));
  Object.values(champIcons).filter(c=>hit(c.name)).slice(0, t ? 8 : 4).forEach(c=>sRows.push({kind:'Champion', name:c.name, icon:c.icon, go:()=>{ go('champs'); initChamps(); q('#champQ').value = c.name; loadChamp(); }}));
  (sAugs||[]).filter(a=>t && hit(a.name)).slice(0,6).forEach(a=>sRows.push({kind:'Augment · ' + (a.grade || 'no grade'), name:a.name, icon:a.icon, go:()=>{ go('mayhem'); q('#augSearch').value = a.name; drawAugs(); }}));
  (sFriends||[]).filter(f=>t && hit(f.name)).slice(0,5).forEach(f=>sRows.push({kind:'Friend', name:f.name, go:()=>openFriend(f.name, f.puuid, !!f.me)}));
  SEARCH_SETTINGS.filter(([l])=>t && hit(l)).forEach(([l,sel])=>sRows.push({kind:'Setting', name:l, go:()=>{ go('settings'); initCT(); setTimeout(()=>{ const el = q(sel); if (el){ if (sel==='#trouble') el.open = true; el.scrollIntoView({block:'center'}); } }, 150); }}));
  sSel = 0; drawSearch();
}
function drawSearch(){ q('#sres').innerHTML = sRows.slice(0, 30).map((r,i)=>`<button class="sres ${i===sSel?'sel':''}" onclick="pickSearch(${i})">${r.icon ? `<img src="${esc(r.icon)}" alt="">` : '<span class="ph"></span>'}<div><b>${esc(r.name)}</b></div><small>${esc(r.kind)}</small></button>`).join('') || '<div class="muted" style="padding:10px">Nothing matches that.</div>'; }
function pickSearch(i){ const r = sRows[i]; closeSearch(); if (r) r.go(); }
q('#sq').addEventListener('input', runSearch);
q('#sq').addEventListener('keydown', e => { if (e.key === 'ArrowDown'){ sSel = Math.min(sRows.length - 1, sSel + 1); drawSearch(); e.preventDefault(); } else if (e.key === 'ArrowUp'){ sSel = Math.max(0, sSel - 1); drawSearch(); e.preventDefault(); } else if (e.key === 'Enter') pickSearch(sSel); });
document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k'){ e.preventDefault(); openSearch(); } if (e.key === 'Escape'){ closeSearch(); q('#shareModal').classList.remove('on'); } });
q('#searchModal').addEventListener('click', e => { if (e.target.id === 'searchModal') closeSearch(); });
// ---------------- champ select suggestions from your pick/ban lists and favorites
function suggestHtml(cs){
  if (!S) return '';
  const taken = new Set([...(cs.team||[]), ...(cs.enemies||[])].map(c=>c.name).concat(cs.champion ? [cs.champion.name] : []));
  const btn = (n, action, label) => `<button data-name="${esc(n)}" onclick="act('${action}',{name:this.dataset.name})" title="${label} ${esc(n)}">${img((champIcons[n]||{}).icon,'',26)}${label} ${esc(n)}</button>`;
  let h = '';
  if (cs.ban_action){ const b = (S.settings.ban_list||[]).filter(n=>!taken.has(n)).slice(0,5); if (b.length) h += `<div class="suggest"><span class="muted" style="font-size:12.5px">Your bans:</span>${b.map(n=>btn(n,'ban','Ban')).join('')}</div>`; }
  if (cs.pick_action){ const p = (S.settings.pick_list||[]).concat(S.settings.favorites||[]).filter((n,i,a)=>!taken.has(n) && a.indexOf(n)===i).slice(0,6); if (p.length) h += `<div class="suggest"><span class="muted" style="font-size:12.5px">Your picks:</span>${p.map(n=>btn(n,'pick','Lock in')).join('')}</div>`; }
  if (cs.bench_enabled && cs.bench){ const fav = cs.bench.filter(b=>(S.settings.favorites||[]).includes(b.name) || (S.settings.pick_list||[]).includes(b.name)); if (fav.length) h += `<div class="suggest"><span class="muted" style="font-size:12.5px">Your favorites on the bench:</span>${fav.map(b=>btn(b.name,'swap','Swap to')).join('')}</div>`; }
  return h;
}
'''

MINI_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>LoLStat Mini</title><style>
''' + "%%BASE_CSS%%" + r'''
body{padding:12px;display:flex;flex-direction:column;gap:10px;font-size:13px}
.m{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.m b.big{display:block;font-size:20px}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.switch{width:44px;height:26px;border-radius:26px;background:var(--line2);position:relative;border:0;cursor:pointer}
.switch::after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:transform .15s}
.switch.on{background:var(--teal)}.switch.on::after{transform:translateX(18px)}
.its{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}.its img{width:34px;height:34px;border-radius:7px;border:1px solid var(--line2)}.its img.own{opacity:.4;border-color:var(--teal)}
</style></head><body>
<div class="m"><div class="muted" id="ph">League client</div><b class="big" id="st">Open League</b><div class="muted" id="sub"></div></div>
<div class="m row"><div><b>Auto-accept</b><div class="muted" style="font-size:12px">Accept matches by itself</div></div><button class="switch" id="acc" aria-label="Auto-accept"></button></div>
<div class="m" id="build" style="display:none"><div class="muted" id="bt"></div><div class="its" id="bi"></div></div>
<div class="m" id="goal" style="display:none"></div>
<script>
''' + "%%COMMON_JS%%" + r'''
const PH = {None:'In the client',Lobby:'In a lobby',Matchmaking:'In queue',ReadyCheck:'Match found',ChampSelect:'Champ select',GameStart:'Loading in',InProgress:'In game',WaitingForStats:'Post game',PreEndOfGame:'Post game',EndOfGame:'Post game'};
const fs = s => { s = Math.max(0, Math.round(s)); return Math.floor(s/60) + ':' + String(s%60).padStart(2,'0'); };
let themeSigM = '';
function render(st){
  const a = st.accept, m = st.mayhem || {};
  const t = st.settings.overlay_theme; const sg = JSON.stringify(t||{});
  if (t && sg !== themeSigM){ themeSigM = sg; const r = document.documentElement.style;
    r.setProperty('--panel', t.glass); r.setProperty('--line', t.edge); r.setProperty('--line2', t.edge); r.setProperty('--text', t.text);
    r.setProperty('--muted', t.muted); r.setProperty('--gold', t.accent); r.setProperty('--teal', t.accent2); r.setProperty('--ink', '#000000'); document.body.style.background = '#05070c'; }
  q('#st').textContent = a.connected ? (PH[a.phase] || a.phase) : 'Open League';
  const qi = a.queue;
  q('#sub').textContent = qi && qi.penalty ? 'Queue penalty ' + fs(qi.penalty) : qi && qi.in_queue ? fs(qi.time) + (qi.estimate ? ' / ~' + fs(qi.estimate) : '') : m.stats ? `${m.stats.k}/${m.stats.d}/${m.stats.a} · ${m.stats.cs} CS` : '';
  q('#ph').textContent = m.champion ? m.champion.name : 'League client';
  q('#acc').classList.toggle('on', a.enabled);
  const b = (m.builds||[])[0];
  q('#build').style.display = b ? '' : 'none';
  if (b){ q('#bt').textContent = b.style.charAt(0) + b.style.slice(1).toLowerCase() + ' build'; const its = (b.boots ? [b.boots] : []).concat(b.items);
    q('#bi').innerHTML = its.map(i=>`<img class="${i.owned?'own':''}" src="${esc(i.icon)}" title="${esc(i.name)}" alt="${esc(i.name)}">`).join(''); }
  const g = st.goal; q('#goal').style.display = g ? '' : 'none';
  if (g) q('#goal').innerHTML = `<div class="muted">Today's goal</div><b>${g.now} / ${g.target}</b>`;
}
q('#acc').onclick = () => act('toggle_accept');
let stH = '';
async function loop(){ let ok = false; try { const st = await api('/api/state?h=' + stH); ok = true; if (st._h !== stH){ stH = st._h; render(st); } } catch(e){} finally { setTimeout(loop, ok ? 0 : 1000); } }
loop();
</script></body></html>'''


def extend2(html):
    html = html.replace('''    <div class="box" style="margin-top:16px"><h2>Automation</h2>''', HOME_EXTRA.strip("\n") + '''
    <div class="box" style="margin-top:16px"><h2>Automation</h2>''', 1)
    html = html.replace('''    <p class="fine" style="margin-top:18px" id="about"></p>''', SETTINGS_EXTRA + '''
    <p class="fine" style="margin-top:18px" id="about"></p>''', 1)
    html = html.replace('''  <div class="modal" id="shareModal"''', SEARCH_MODAL + '''
  <div class="modal" id="shareModal"''', 1)
    html = html.replace('''/* champ select */''', CSS2 + '''/* champ select */''', 1)
    html = html.replace('''let lastTick = 0;''', JS2 + '''let lastTick = 0;''', 1)
    html = html.replace('''    <span class="grow"></span>''', '''    <span class="grow"></span>
    <button class="searchbtn" onclick="openSearch()" aria-label="Search">Search <kbd>Ctrl K</kbd></button>''', 1)
    html = html.replace('''  drawAuto(st); drawLastGame(m);''', '''  drawQol(st);
  drawAuto(st); drawLastGame(m);''', 1)
    # champ select: suggestions
    html = html.replace('''  if (S){ h += `<div class="auto" style="margin-top:16px">''', '''  h += suggestHtml(cs);
  if (S){ h += `<div class="auto" style="margin-top:16px">''', 1)
    return html


def mini_html(base_css, common_js):
    return MINI_HTML.replace("%%BASE_CSS%%", base_css).replace("%%COMMON_JS%%", common_js)


# ====================================================================== round 3: fun
NAV3 = r'''  <button class="nav" data-page="fun" aria-label="Challenges"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg><span class="tip">Challenges</span></button>
'''

SECTION3 = r'''
  <!-- CHALLENGES -->
  <section class="page" id="p-fun">
    <div class="box"><div class="cs-head" style="margin:0"><div><h2 style="margin:0">Challenges</h2><div class="muted" style="font-size:12.5px">Missions, this week's Chaos build, your augment collection and the build lab.</div></div><div class="seg" id="funTabs"></div></div></div>
    <div id="funOut"></div>
    <datalist id="itemNames"></datalist>
  </section>
'''

TILT_BANNER = r'''
    <div class="box" id="tiltBox" style="display:none;margin-bottom:16px;border-color:var(--gold)"></div>'''

SETTINGS3 = r'''
      <h2 style="margin-top:18px">Wellbeing</h2>
      <div class="auto" id="setTilt"></div>
      <div class="spells"><span class="muted" style="font-size:12.5px">After</span><select id="tiltN"><option>2</option><option>3</option><option>4</option><option>5</option></select><span class="muted" style="font-size:12.5px">losses in a row, suggest a</span><select id="tiltM"><option>5</option><option>10</option><option>15</option><option>30</option></select><span class="muted" style="font-size:12.5px">minute break.</span></div>'''

CSS3 = r'''
/* round 3 */
.mis{display:grid;grid-template-columns:28px 1fr 140px;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}
.mis:last-child{border:0}
.mis .ck{width:24px;height:24px;border-radius:50%;border:2px solid var(--line2);display:grid;place-items:center;font-size:13px;font-weight:800;color:#06121a}
.mis.done .ck{background:var(--teal);border-color:var(--teal)}
.mis.done b{color:var(--muted);text-decoration:line-through}
.coll{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.cg{position:relative}
.coll .a{padding:10px;border-radius:12px;background:var(--raised);border:1px solid var(--line);text-align:center;font-size:12px}
.coll .a img{width:46px;height:46px;border-radius:10px;margin:0 auto 6px;background:var(--iconbg,#1a2440)}
.coll .a.no img{filter:grayscale(1) brightness(.45)}.coll .a.no{opacity:.6}
.coll .a b{display:block;font-size:12.5px;line-height:1.25}
.labgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}
.labgrid input,.labin{width:100%;background:var(--raised);border:1px solid var(--line2);border-radius:9px;padding:8px 10px}
.vsbars .bar{grid-template-columns:90px 1fr 70px}
.mine{position:absolute;right:8px;top:40px;font-size:11px;font-weight:700;padding:2px 7px;border-radius:7px;background:rgba(5,8,15,.8);color:#fff}
@keyframes killflash{0%{box-shadow:inset 0 0 0 0 var(--gold)}30%{box-shadow:inset 0 0 0 4px var(--gold)}100%{box-shadow:inset 0 0 0 0 transparent}}
body.kill main{animation:killflash .9s ease-out}
body.dead main{filter:grayscale(.85) brightness(.8);transition:filter .4s}
#confetti{position:fixed;inset:0;pointer-events:none;z-index:40}
'''

JS3 = r'''
// ---------------- challenges
let funTab = 'missions', FUN = null, labItems = null, labChamp = null;
const FUN_TABS = [['missions','Missions'],['chaos','Chaos mode'],['collection','Augment collection'],['lab','Build lab']];
q('#funTabs').innerHTML = FUN_TABS.map(([k,l])=>`<button data-k="${k}" class="${k===funTab?'on':''}">${l}</button>`).join('');
q('#funTabs').onclick = e => { const b = e.target.closest('button'); if (!b) return; funTab = b.dataset.k; document.querySelectorAll('#funTabs button').forEach(x=>x.classList.toggle('on', x===b)); drawFun(); };
async function loadFun(){ if (page !== 'fun') return; await ensureChampIcons(); try { FUN = await api('/api/challenges' + (labChamp ? '?champ=' + encodeURIComponent(labChamp) : '')); drawFun(); } catch(e){ console.error('fun', e); } }
setInterval(()=>{ if (funTab !== 'lab') loadFun(); }, 30000);
function misRow(m){ const pctv = Math.min(100, m.now / m.goal * 100);
  return `<div class="mis ${m.done?'done':''}"><span class="ck">${m.done?'✓':''}</span><b>${esc(m.text)}</b><div><div class="muted" style="font-size:12px;text-align:right">${m.goal >= 1000 ? fmt(m.now) + ' / ' + fmt(m.goal) : m.now + ' / ' + m.goal}</div><div class="progress"><i style="width:${pctv}%"></i></div></div></div>`; }
function drawFun(){
  const F = FUN, el = q('#funOut'); if (!F && funTab !== 'lab') return;
  const ci = n => (champIcons[n]||{}).icon;
  if (funTab === 'missions'){
    const M = F.missions;
    el.innerHTML = `<div class="sum" style="margin-top:16px;grid-template-columns:repeat(3,1fr)">${[[M.daily.filter(m=>m.done).length + ' / 3','daily missions done'],[M.weekly.filter(m=>m.done).length + ' / 3','weekly missions done'],[M.streak + (M.streak === 1 ? ' day' : ' days'),'daily streak']].map(([v,l])=>`<div class="box"><div class="stat">${v}</div><div class="muted" style="font-size:12.5px">${l}</div></div>`).join('')}</div>
      <div class="two"><div class="box"><h2>Today</h2><div class="muted" style="font-size:12.5px">New missions in ${M.resets_in_h} hours. Finish all three to keep your streak.</div>${M.daily.map(misRow).join('')}</div><div class="box"><h2>This week</h2><div class="muted" style="font-size:12.5px">Resets every Monday.</div>${M.weekly.map(misRow).join('')}</div></div>`;
  } else if (funTab === 'chaos'){
    const b = F.build, rows = b ? (b.boots ? [Object.assign({n:'B'}, b.boots)] : []).concat(b.items.map((it,i)=>Object.assign({n:i+1}, it))) : [];
    el.innerHTML = `<div class="box" style="margin-top:16px"><div class="muted" style="font-size:12.5px">This week's challenge · ${esc(F.challenge.week)}</div><div class="cs-title" style="margin:2px 0 4px">${esc(F.challenge.name)}</div><div>${esc(F.challenge.desc)}</div>
      <div class="muted" style="font-size:12.5px;margin-top:8px">Play any game following the rule (3 or more finished items that fit). Your best games this week are scored by damage per minute.</div></div>
      <div class="two"><div class="box"><div class="cs-head" style="margin:0 0 8px"><h2 style="margin:0">Chaos build for ${esc(F.champion || 'your champion')}</h2><input class="labin" list="champNames" placeholder="Other champion" style="width:180px" onchange="labChamp=this.value;loadFun()"></div>
        <div class="items">${rows.map(it=>`<div class="item"><span class="n">${it.n}</span>${img(it.icon,'',48)}<div><b>${esc(it.name)}</b><div class="why">${esc(it.why)}</div></div></div>`).join('') || '<div class="muted">Pick a champion.</div>'}</div></div>
        <div class="box"><h2>Your challenge games</h2>${F.chaos_games.map((g,i)=>`<div class="ctab" style="grid-template-columns:24px 36px 1fr auto auto"><b>${i+1}</b>${img(ci(g.champ),'',36)}<div><b>${esc(g.champ)}</b><div class="muted" style="font-size:11.5px">${g.k}/${g.d}/${g.a} · ${g.win?'Victory':'Defeat'}</div></div><b>${fmt(g.dpm)}</b><span class="muted">dmg/min</span></div>`).join('') || '<div class="muted">No challenge games yet this week. Build it and show off.</div>'}</div></div>`;
    if (!champsLoaded){ champsLoaded = true; api('/api/champions').then(r=>{ q('#champNames').innerHTML = r.map(c=>`<option value="${esc(c.name)}">`).join(''); }); }
  } else if (funTab === 'collection'){
    const C = F.collection;
    el.innerHTML = `<div class="box" style="margin-top:16px"><div class="cs-head" style="margin:0"><div><h2 style="margin:0">Augment collection</h2><div class="muted" style="font-size:12.5px">Every ARAM Mayhem augment you've taken while LoLStat was running.</div></div><div class="stat">${C.tried} / ${C.total}</div></div><div class="progress" style="margin-top:10px"><i style="width:${C.tried / Math.max(1,C.total) * 100}%"></i></div></div>
      <div class="box" style="margin-top:16px"><div class="coll">${C.augments.map(a=>`<div class="a tier-${esc(a.tier)} ${a.games?'':'no'}" title="${esc(a.name)}">${img(a.icon,'',46)}<b>${esc(a.name)}</b><span class="muted">${a.games ? `${a.games}× · ${a.wr}% wins` : 'Not tried yet'}</span><div style="margin-top:4px">${grade(a.grade)}</div></div>`).join('')}</div></div>`;
  } else if (funTab === 'lab'){ drawLab(); }
}
async function drawLab(){
  const el = q('#funOut');
  if (!labItems){ try { labItems = await api('/api/items'); q('#itemNames').innerHTML = labItems.map(i=>`<option value="${esc(i.name)}">`).join(''); } catch(e){ labItems = []; } }
  if (!champsLoaded){ champsLoaded = true; api('/api/champions').then(r=>{ q('#champNames').innerHTML = r.map(c=>`<option value="${esc(c.name)}">`).join(''); }); }
  if (el.dataset.lab) return; el.dataset.lab = '1';
  el.innerHTML = `<div class="two"><div class="box"><h2>Build lab</h2><div class="muted" style="font-size:12.5px">Try any build on any champion and see how hard it hits before you buy it.</div>
      <div class="labgrid" style="grid-template-columns:1fr"><input id="labC" list="champNames" placeholder="Champion" value="${esc(S && S.mayhem.champion ? S.mayhem.champion.name : 'Jinx')}"></div>
      <div class="labgrid">${[1,2,3,4,5,6].map(i=>`<input class="labI" list="itemNames" placeholder="Item ${i}">`).join('')}</div>
      <div class="muted" style="font-size:12px;margin-top:10px">Enemy team (optional)</div><div class="labgrid">${[1,2,3,4,5].map(i=>`<input class="labE" list="champNames" placeholder="Enemy ${i}">`).join('')}</div>
      <div style="display:flex;gap:8px;margin-top:10px"><button class="btn gold" onclick="runLab()">Test this build</button><button class="btn" onclick="fillLab()">Load LoLStat's max damage build</button></div></div>
    <div class="box" id="labOut"><div class="muted">Add items and press Test this build.</div></div></div>
    <div class="box" style="margin-top:16px"><h2>Which item is better?</h2><div class="muted" style="font-size:12.5px">Compares two items for the champion and enemy team above.</div>
      <div class="labgrid"><input id="cmpA" list="itemNames" placeholder="First item"><input id="cmpB" list="itemNames" placeholder="Second item"><button class="btn gold" onclick="runCompare()">Compare</button></div><div id="cmpRes" style="margin-top:12px"></div></div>`;
}
const itemId = n => { const it = (labItems||[]).find(i=>i.name.toLowerCase() === (n||'').trim().toLowerCase()); return it ? it.id : null; };
const labEnemies = () => [...document.querySelectorAll('.labE')].map(i=>i.value.trim()).filter(Boolean);
async function fillLab(){ const c = q('#labC').value.trim(); if (!c) return; try { const r = await api('/api/champion?name=' + encodeURIComponent(c) + '&mode=sr'); const b = r.builds && r.builds[0]; if (!b) return;
  const its = (b.boots ? [b.boots] : []).concat(b.items); document.querySelectorAll('.labI').forEach((el,i)=>el.value = its[i] ? its[i].name : ''); runLab(); } catch(e){} }
async function runLab(){
  const ids = [...document.querySelectorAll('.labI')].map(i=>itemId(i.value)).filter(Boolean);
  if (!ids.length){ q('#labOut').innerHTML = '<div class="muted">Add at least one item from the list.</div>'; return; }
  const r = await api('/api/buildlab', {champ: q('#labC').value.trim(), items: ids, enemies: labEnemies()});
  if (r.error){ q('#labOut').innerHTML = `<div class="muted">${esc(r.error)}</div>`; return; }
  const max = Math.max(...Object.values(r.vs), 1), S2 = r.stats, L = {ad:'Attack damage', ap:'Ability power', as:'Attack speed %', crit:'Crit chance %', haste:'Ability haste', hp:'Health', armor:'Armor', mr:'Magic resist', leth:'Lethality', arpen:'Armor pen %', mpen_pct:'Magic pen %', mpen:'Magic pen', ls:'Life steal %', omni:'Omnivamp %', ms:'Move speed'};
  q('#labOut').innerHTML = `<h2>Results</h2><div class="livestats" style="margin-top:0">${r.rating != null ? `<div><b>${r.rating}%</b>of LoLStat's best build</div>` : ''}<div><b>${fmt(r.gold)}</b>gold</div></div>
    <h2 style="margin-top:14px">Damage against</h2><div class="bars vsbars">${Object.entries(r.vs).map(([k,v])=>`<div class="bar"><b>${k}</b><div class="tr"><i style="width:${v/max*100}%"></i></div><span>${fmt(v)}</span></div>`).join('')}</div>
    <h2 style="margin-top:14px">Stats</h2><div class="rec" style="grid-template-columns:repeat(auto-fill,minmax(120px,1fr))">${Object.entries(S2).filter(([k])=>L[k]).map(([k,v])=>`<div><span>${L[k]}</span><b>${v}</b></div>`).join('')}</div>
    ${r.feats.length ? `<div class="muted" style="font-size:12px;margin-top:10px">Passives: ${r.feats.map(f=>({onhit:'on-hit',maxhp:'% max health damage',curhp:'% current health damage',antiheal:'anti-heal',antishield:'shield breaking',spellblade:'Spellblade',burn:'burn',ap_amp:'AP multiplier',execute:'execute'})[f]||f).join(', ')}</div>` : ''}`;
}
async function runCompare(){
  const a = itemId(q('#cmpA').value), b = itemId(q('#cmpB').value);
  if (!a || !b){ q('#cmpRes').innerHTML = '<div class="muted">Pick two items from the list.</div>'; return; }
  const r = await api('/api/compare', {champ: q('#labC').value.trim(), a, b, enemies: labEnemies()});
  if (r.error){ q('#cmpRes').innerHTML = `<div class="muted">${esc(r.error)}</div>`; return; }
  const side = x => `<div class="rk" style="${x.name===r.winner?'border-color:var(--gold)':''}"><span>${x.name===r.winner?'Better pick':'Second'}</span><b>${esc(x.name)}</b><span>${fmt(x.gold)} gold · ${x.why.map(esc).join(', ')}</span></div>`;
  q('#cmpRes').innerHTML = `<div class="ranks" style="margin-top:0">${side(r.a)}${side(r.b)}</div><div style="margin-top:8px"><b>${esc(r.winner)}</b> is the stronger pick here${r.margin != null ? ` by about ${r.margin}%` : ''}.</div>`;
}
// ---------------- reactive themes: flash on kills, grey while dead, confetti on wins
let lastK = null, lastWinId = null;
function reactive(st){
  const m = st.mayhem, on = st.settings.reactive && !st.settings.reduce_motion;
  const s = m.stats;
  document.body.classList.toggle('dead', !!(on && m.live && s && s.dead));
  if (on && m.live && s){ if (lastK != null && s.k > lastK){ document.body.classList.remove('kill'); void document.body.offsetWidth; document.body.classList.add('kill'); } lastK = s.k; } else lastK = null;
  const g = (m.history||[])[0];
  if (g && lastWinId === null) lastWinId = g.id;
  if (g && g.id !== lastWinId){ lastWinId = g.id; if (on && g.win) confetti(); }
}
function confetti(){
  const cv = document.createElement('canvas'); cv.id = 'confetti'; cv.width = innerWidth; cv.height = innerHeight; document.body.appendChild(cv);
  const x = cv.getContext('2d'), css = getComputedStyle(document.documentElement), cols = ['--gold','--teal','--gS','--gA','--text'].map(v=>css.getPropertyValue(v).trim());
  const P = Array.from({length: 160}, () => ({x: Math.random() * cv.width, y: -20 - Math.random() * cv.height * .4, vx: (Math.random() - .5) * 4, vy: 2 + Math.random() * 4, r: 3 + Math.random() * 5, c: cols[Math.floor(Math.random() * cols.length)], a: Math.random() * 6}));
  let t = 0; (function tick(){ x.clearRect(0, 0, cv.width, cv.height); P.forEach(p=>{ p.x += p.vx; p.y += p.vy; p.vy += .05; p.a += .1; x.fillStyle = p.c; x.save(); x.translate(p.x, p.y); x.rotate(p.a); x.fillRect(-p.r, -p.r / 2, p.r * 2, p.r); x.restore(); });
    if (++t < 200) requestAnimationFrame(tick); else cv.remove(); })();
}
// ---------------- tilt guard banner + settings
function drawTilt(st){
  const b = q('#tiltBox'), s = st.tilt_lock;
  if (s > 0){ b.style.display = ''; b.innerHTML = `<div class="cs-head" style="margin:0"><div><b>Break time</b><div class="muted" style="font-size:12.5px">Tilt guard paused queueing after a losing run. Queue opens again in ${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}.</div></div><button class="btn" onclick="act('end_break')">End break now</button></div>`; }
  else b.style.display = 'none';
  if (page === 'settings' && q('#setTilt').dataset.sig !== JSON.stringify(st.settings)){ q('#setTilt').dataset.sig = JSON.stringify(st.settings);
    q('#setTilt').innerHTML = toggleRow(st, [['tilt_guard','Tilt guard','Suggests a break after a losing run'],['tilt_lock','Pause queueing during the break','Stops a queue you start during the break (you can end it any time)'],['reactive','Reactive themes','Flash on kills, grey while dead, confetti on wins']]);
    q('#tiltN').value = String(st.settings.tilt_losses || 3); q('#tiltM').value = String(st.settings.tilt_minutes || 10); }
}
q('#tiltN').onchange = () => act('set_value',{name:'tilt_losses', value:+q('#tiltN').value});
q('#tiltM').onchange = () => act('set_value',{name:'tilt_minutes', value:+q('#tiltM').value});
'''


def extend3(html):
    html = html.replace('''  <button class="nav" data-page="games" aria-label="Games">''', NAV3 + '''  <button class="nav" data-page="games" aria-label="Games">''', 1)
    html = html.replace('''  <!-- GAMES -->''', SECTION3 + '''  <!-- GAMES -->''', 1)
    html = html.replace('''  <section class="page on" id="p-home">''', '''  <section class="page on" id="p-home">''' + TILT_BANNER, 1)
    html = html.replace('''      <h2 style="margin-top:18px">Accessibility</h2>''', SETTINGS3.strip("\n") + '''
      <h2 style="margin-top:18px">Accessibility</h2>''', 1)
    html = html.replace('''/* champ select */''', CSS3 + '''/* champ select */''', 1)
    html = html.replace('''let lastTick = 0;''', JS3 + '''let lastTick = 0;''', 1)
    html = html.replace('''if (p==='stats') loadStats();''', '''if (p==='stats') loadStats(); if (p==='fun') loadFun();''', 1)
    html = html.replace('''friends:'Friends', stats:'My stats',''', '''friends:'Friends', stats:'My stats', fun:'Challenges',''', 1)
    html = html.replace('''  drawQol(st);''', '''  drawQol(st); drawTilt(st); reactive(st);''', 1)
    # your own record on champion cards in champ select
    html = html.replace('''`<span class="cg">${grade(c.tier)}</span>`}''', '''`<span class="cg">${grade(c.tier)}</span>`}
    ${S && S.my_champs && S.my_champs[c.name] ? `<span class="mine" title="Your games on ${esc(c.name)}">You: ${S.my_champs[c.name][1]}% · ${S.my_champs[c.name][0]}g</span>` : ''}''', 1)
    return html


# ====================================================================== round 4: launch prep
NAV4 = r'''  <button class="nav" data-page="help" aria-label="Help"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9.5"/><path d="M9.3 9.2a2.8 2.8 0 0 1 5.4 1c0 1.9-2.7 2.4-2.7 4"/><circle cx="12" cy="17.4" r=".6" fill="currentColor"/></svg><span class="tip">Help</span></button>
'''

import patch_notes  # noqa: E402  (one source for patch notes: app, GitHub releases, CHANGELOG.md)

WHATS_NEW = list(patch_notes.latest()["changes"])

HELP = [
    ("Getting started", "Install LoLStat, open it, then open League. LoLStat connects by itself. Most things are automatic: auto-accept, item sets, rune pages and summoner spells in champ select, builds and augment grades in game. Turn any of them on or off on the Home page under Automation."),
    ("The overlay or grade letters don't show", "Set League's Window Mode to Borderless (Settings, Video in League). Make sure In-game overlay and Read augment cards are on under Automation. Then use Test overlay in Settings, Troubleshooting. If it still doesn't work, copy the report there and send it to support."),
    ("Item sets don't show in the shop", "Item sets are saved during champ select once your champion is known. Make sure Item sets is on under Automation, then check the shop's item set dropdown. If League was open before LoLStat, give it a few seconds after your champion changes."),
    ("Rune page isn't imported", "League only lets you have a limited number of rune pages. If they're all in use, LoLStat tells you; delete or rename one page and LoLStat keeps its own page updated from then on. ARAM Mayhem has no runes."),
    ("A friend shows 'Profile hidden'", "Their League profile is private, or they haven't played recently. LoLStat only shows what the League client shows you."),
    ("How the stats work", "Your profile, match history and friends come from your League client. ARAM Mayhem augment and champion grades come from daily stats. Summoner's Rift and ARAM builds and runes come from LoLStat's own damage engine, built from item stats and champion data."),
    ("Phone remote", "Scan the QR code on the Home page with your phone on the same Wi-Fi. You can toggle auto-accept, accept or decline, and open the full app on your phone."),
    ("How does Party Showdown work?", "Get in a lobby with your friends and play. After each game, LoLStat reads everyone's damage to champions from the end-of-game screen and gives the point to whoever did the most. The first to win most of the series (2 in a best of 3, 3 in a best of 5) wins. Remakes and ties don't count. If someone wasn't in a game, that game doesn't count unless you press Count it anyway. You can change any result by hand, and switch between best of 3 and best of 5 on the Party Showdown tab or in Settings."),
    ("Hotkeys", "The in-game panel opens and closes with the hotkey in Settings (Ctrl+Shift+L by default). Ctrl+K opens search in the app."),
    ("Privacy", "Everything LoLStat saves stays on your PC: settings, your game archive, records and journal. Screen reading for augment cards happens on your PC and screenshots are never saved or sent anywhere."),
    ("Is this allowed?", "LoLStat uses the League client's local interface, like other companion apps. Auto-accept and screen reading aren't named in Riot's rules, but there's some risk with any third-party app, so you can switch every automation off, or use safe mode."),
    ("Something is broken", "Turn on safe mode in Settings to pause all automation, then turn things back on one at a time. Use Copy report in Settings, Troubleshooting and include it when you ask for help."),
    ("Uninstalling", "Use Remove LoLStat from League in Settings first, or just uninstall: the uninstaller removes LoLStat's item sets and rune page while League is open."),
]

SECTION4 = r'''
  <!-- HELP -->
  <section class="page" id="p-help">
    <div class="box"><h2 style="margin:0">Help</h2><div class="muted" style="font-size:12.5px">Answers to common questions. Press Ctrl+K anywhere to search LoLStat.</div></div>
    <div class="box" style="margin-top:16px">%%FAQ%%</div>
    <div class="box" style="margin-top:16px"><h2>Version history</h2>%%HISTORY%%</div>
  </section>
'''

MODALS4 = r'''
  <div class="modal" id="onbModal" role="dialog" aria-modal="true" aria-labelledby="onbTitle"><div class="sheet" style="max-width:760px">
    <div class="muted" style="font-size:12px" id="onbStep"></div>
    <div id="onbBody"></div>
    <div style="display:flex;justify-content:space-between;margin-top:18px"><button class="btn" id="onbBack">Back</button><button class="btn gold" id="onbNext">Next</button></div>
  </div></div>
  <div class="modal" id="newModal" role="dialog" aria-modal="true" aria-labelledby="newTitle"><div class="sheet" style="max-width:720px">
    <h2 id="newTitle" style="margin:0 0 4px">What's new in LoLStat %%VERSION%%</h2>
    <div class="muted" style="font-size:12.5px;margin-bottom:10px">Here's what changed since your last version.</div>
    %%NEWS%%
    <div style="display:flex;justify-content:flex-end;margin-top:14px"><button class="btn gold" onclick="act('seen_whatsnew');q('#newModal').classList.remove('on')">Got it</button></div>
  </div></div>'''

SETTINGS4 = r'''
    <div class="box" style="max-width:860px;margin-top:16px">
      <h2>Safety</h2>
      <div class="set"><div><b>Safe mode</b><p>Pauses every automation (auto-accept, item sets, runes, spells, overlay, card reading). Turning it off brings back exactly what you had.</p></div><button class="switch" id="safeSw" onclick="act('safe_mode')" aria-label="Safe mode"></button></div>
      <div class="set"><div><b>Remove LoLStat from League</b><p>Deletes the item sets and rune page LoLStat added to your League client. Your own sets and pages are never touched.</p></div><button class="btn" onclick="act('cleanup')">Remove now</button></div>
      <div class="set"><div><b>Setup guide</b><p>Run the first-launch setup again.</p></div><button class="btn" onclick="openOnboarding(true)">Open setup</button></div>
    </div>'''

CSS4 = r'''
/* round 4 */
.faq details{border-bottom:1px solid var(--line);padding:12px 0}.faq details:last-child{border:0}
.faq summary{cursor:pointer;font-weight:600;list-style:none;display:flex;justify-content:space-between}
.faq summary::-webkit-details-marker{display:none}.faq summary::after{content:"+";color:var(--muted);font-weight:700}
.faq details[open] summary::after{content:"–"}.faq p{margin:8px 0 0;color:var(--muted);font-size:13.5px;line-height:1.55;max-width:820px}
.news{display:grid;grid-template-columns:150px 1fr;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13.5px}.news:last-child{border:0}
.news b{color:var(--gold)}
.onb-themes{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}
.onb-themes button{border-radius:12px;padding:14px;border:2px solid var(--line2);text-align:left;font-weight:700}
.onb-themes button.on{border-color:var(--gold)}
.onb-dots{display:flex;gap:6px;margin:10px 0 0}.onb-dots i{width:24px;height:4px;border-radius:4px;background:var(--line2)}.onb-dots i.on{background:var(--gold)}
'''

JS4 = r'''
// ---------------- onboarding (first launch) and what's new
let onbStep = 0, onbTheme = null, onbFollow = false, onbOpened = false;
const ONB_AUTO = [['accept','Auto-accept matches',true],['itemsets','Item sets in champ select',true],['runes','Rune pages',true],['spells','Summoner spells',true],['overlay','In-game overlay',true],['scan','Read augment cards (ARAM Mayhem)',true]];
let onbAuto = Object.fromEntries(ONB_AUTO.map(([k,,v])=>[k,v]));
function openOnboarding(again){ onbStep = 0; onbOpened = true; q('#onbModal').classList.add('on'); drawOnb(); }
function drawOnb(){
  const steps = 4;
  q('#onbStep').innerHTML = `Step ${onbStep + 1} of ${steps}<div class="onb-dots">${Array.from({length:steps},(_,i)=>`<i class="${i<=onbStep?'on':''}"></i>`).join('')}</div>`;
  q('#onbBack').style.visibility = onbStep ? 'visible' : 'hidden';
  q('#onbNext').textContent = onbStep === steps - 1 ? 'Start using LoLStat' : 'Next';
  const b = q('#onbBody');
  if (onbStep === 0) b.innerHTML = `<h2 style="font-size:24px;margin:14px 0 6px">Welcome to LoLStat</h2><p class="muted" style="font-size:14px;line-height:1.6">Your League companion. LoLStat accepts matches, sets up runes, spells and item sets in champ select, grades ARAM Mayhem augments right on your screen, scouts every player in your game, and turns your games into stats, records and challenges.</p><p class="muted" style="font-size:14px">This quick setup takes 30 seconds. You can change everything later in Settings.</p>`;
  else if (onbStep === 1){
    const opts = [['dark','Dark'],['league','League'],['light','Light'],['midnight','Midnight']];
    b.innerHTML = `<h2 style="font-size:20px;margin:14px 0 6px">Pick a look</h2><div class="onb-themes">${opts.map(([k,l])=>{ const t = THEMES[k]; return `<button class="${onbTheme===k?'on':''}" style="background:${t.panel};color:${t.text}" onclick="onbTheme='${k}';chooseTheme('${k}');drawOnb()">${l}<div class="sw" style="display:flex;gap:4px;margin-top:8px">${[t.bg,t.accent,t.accent2].map(c=>`<i style="display:block;width:16px;height:16px;border-radius:4px;background:${c}"></i>`).join('')}</div></button>`; }).join('')}</div>
      <label class="chk" style="margin-top:14px"><input type="checkbox" ${onbFollow?'checked':''} onchange="onbFollow=this.checked"><div><b>Match my champion automatically</b><span>The app takes the colors and splash art of the champion and skin you're playing. There's a theme for every champion in Settings too.</span></div></label>`;
  } else if (onbStep === 2){
    b.innerHTML = `<h2 style="font-size:20px;margin:14px 0 6px">What should LoLStat do for you?</h2><p class="muted" style="font-size:13px">All of these are on by default. You can change them any time on the Home page.</p><div class="auto">${ONB_AUTO.map(([k,l])=>`<label class="chk"><input type="checkbox" ${onbAuto[k]?'checked':''} onchange="onbAuto['${k}']=this.checked"><div><b>${l}</b></div></label>`).join('')}</div>`;
  } else b.innerHTML = `<h2 style="font-size:20px;margin:14px 0 6px">You're all set</h2><div class="tip-row"><i class="g">1</i><span>Open League. LoLStat connects by itself and shows your champ select, builds and stats.</span></div><div class="tip-row"><i class="g">2</i><span>For the in-game overlay, set League's Window Mode to <b>Borderless</b>.</span></div><div class="tip-row"><i class="g">3</i><span>Press <b>Ctrl+K</b> to search anything. Closing the window quits LoLStat completely.</span></div><div class="tip-row"><i class="g">4</i><span>Scan the QR code on Home to control LoLStat from your phone.</span></div>`;
}
q('#onbBack').onclick = () => { onbStep = Math.max(0, onbStep - 1); drawOnb(); };
q('#onbNext').onclick = () => { if (onbStep < 3){ onbStep++; drawOnb(); return; }
  if (onbFollow && !(S && S.settings.theme_follow)) act('setting', {name:'theme_follow'});
  act('finish_onboarding', {auto: onbAuto}); q('#onbModal').classList.remove('on'); toastMsg('Welcome to LoLStat. Open League and you’re ready.'); };
function launchModals(st){
  if (!st.onboarded && !onbOpened) openOnboarding();
  if (st.show_whatsnew && !q('#newModal').classList.contains('on') && !window._newShown){ window._newShown = true; q('#newModal').classList.add('on'); }
  if (q('#safeSw')) q('#safeSw').classList.toggle('on', !!st.settings.safe_mode);
}
'''


def extend4(html, version):
    faq = "".join(f'<div class="faq"><details><summary>{q}</summary><p>{a}</p></details></div>' for q, a in HELP)
    news = "".join(f'<div class="news"><b>{t}</b><span>{d}</span></div>' for t, d in WHATS_NEW)
    hist = "".join(f'<div class="news"><b>{n["version"]}</b><span>{n["summary"]}'
                   + (f' <span class="muted">({n["date"]})</span>' if n["date"] else "") + '</span></div>'
                   for n in patch_notes.NOTES)
    html = html.replace('''  <button class="nav" data-page="settings" aria-label="Settings">''', NAV4 + '''  <button class="nav" data-page="settings" aria-label="Settings">''', 1)
    html = html.replace('''  <!-- GAMES -->''', SECTION4.replace("%%FAQ%%", faq).replace("%%HISTORY%%", hist) + '''  <!-- GAMES -->''', 1)
    html = html.replace('''  <div class="modal" id="shareModal"''', MODALS4.replace("%%VERSION%%", version).replace("%%NEWS%%", news) + '''
  <div class="modal" id="shareModal"''', 1)
    html = html.replace('''    <p class="fine" style="margin-top:18px" id="about"></p>''', SETTINGS4 + '''
    <p class="fine" style="margin-top:18px" id="about"></p>''', 1)
    html = html.replace('''/* champ select */''', CSS4 + '''/* champ select */''', 1)
    html = html.replace('''let lastTick = 0;''', JS4 + '''let lastTick = 0;''', 1)
    html = html.replace('''fun:'Challenges',''', '''fun:'Challenges', help:'Help',''', 1)
    html = html.replace('''  drawQol(st); drawTilt(st); reactive(st);''', '''  drawQol(st); drawTilt(st); reactive(st); launchModals(st);''', 1)
    html = html.replace('''['Troubleshooting','#trouble']];''', '''['Troubleshooting','#trouble'],['Safe mode','#safeSw'],['Remove LoLStat from League','#safeSw']];''', 1)
    html = html.replace('''const SEARCH_PAGES = [''', '''const SEARCH_PAGES = [['help','Help'],['fun','Challenges'],''', 1)
    return html


# ====================================================================== Fun tab: Party Showdown
CSS5 = r'''
/* party showdown */
.sd-hero{position:relative;overflow:hidden;margin-top:16px;padding:26px 26px 22px;border-radius:18px;border:1px solid var(--line);
  background:radial-gradient(120% 140% at 0% 0%,color-mix(in srgb,var(--gold) 16%,transparent),transparent 55%),radial-gradient(120% 140% at 100% 100%,color-mix(in srgb,var(--teal) 14%,transparent),transparent 55%),var(--panel)}
.sd-hero h3{margin:0;font-size:26px;letter-spacing:-.01em}
.sd-hero p{margin:6px 0 0;color:var(--muted);max-width:620px;line-height:1.55}
.sd-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}
.sd-steps div{padding:14px;border-radius:12px;background:color-mix(in srgb,var(--raised) 80%,transparent);border:1px solid var(--line);font-size:13px;line-height:1.5}
.sd-steps b{display:block;color:var(--gold);font-size:12px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px}
.sd-party{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.sd-chip{display:inline-flex;align-items:center;gap:8px;padding:6px 12px 6px 6px;border-radius:99px;background:var(--raised);border:1px solid var(--line2);font-weight:600;font-size:13px}
.sd-av{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:12px;color:#0c1220;background:var(--av,var(--gold));flex:none;overflow:hidden}
.sd-av img{width:100%;height:100%;object-fit:cover}
.sd-board{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-top:16px}
.sd-p{position:relative;padding:18px;border-radius:16px;background:var(--panel);border:1px solid var(--line);transition:transform .25s,border-color .25s}
.sd-p.lead{border-color:color-mix(in srgb,var(--gold) 70%,transparent);box-shadow:0 0 0 1px color-mix(in srgb,var(--gold) 30%,transparent),0 10px 30px -14px color-mix(in srgb,var(--gold) 60%,transparent)}
.sd-p.champ{border-color:var(--gold);transform:translateY(-2px)}
.sd-p .sd-top{display:flex;align-items:center;gap:12px}
.sd-p .sd-av{width:46px;height:46px;font-size:17px;border-radius:14px}
.sd-p .nm{font-weight:700;font-size:16px;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sd-p .sub{color:var(--muted);font-size:12px;margin-top:2px}
.sd-p .wins{margin-left:auto;font-size:34px;font-weight:800;line-height:1}
.sd-p .crown{position:absolute;top:-11px;left:18px;font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;padding:3px 9px;border-radius:99px;background:var(--gold);color:#0c1220}
.sd-p .crown.mp{background:var(--teal)}
.sd-pips{display:flex;gap:8px;margin:16px 0 14px}
.sd-pip{width:30px;height:30px;border-radius:9px;border:2px solid var(--line2);display:grid;place-items:center;color:#0c1220;font-weight:900;font-size:15px;transition:background .3s,border-color .3s}
.sd-pip.on{background:var(--gold);border-color:var(--gold);animation:sdpop .45s cubic-bezier(.2,1.6,.4,1)}
@keyframes sdpop{0%{transform:scale(.4)}100%{transform:scale(1)}}
.sd-p .nums{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;color:var(--muted)}
.sd-p .nums b{display:block;color:var(--text);font-size:14px}
.sd-p .rm{position:absolute;bottom:10px;right:10px;width:24px;height:24px;border-radius:7px;color:var(--muted);opacity:0;transition:opacity .2s}
.sd-p:hover .rm{opacity:1}.sd-p .rm:hover{background:var(--raised);color:var(--text)}
.sd-diff{margin-top:12px;font-size:12.5px;font-weight:700;color:var(--muted)}.sd-diff.up{color:var(--teal)}.sd-diff.down{color:#ff8a8a}
.sd-margin{font-size:12.5px;color:var(--muted);margin-top:8px}.sd-margin b{color:var(--gold)}
.sd-status{display:flex;align-items:center;gap:10px;margin-top:16px;padding:12px 16px;border-radius:12px;background:var(--raised);border:1px solid var(--line);font-size:13.5px}
.sd-status .dot{width:9px;height:9px;border-radius:50%;background:var(--teal);box-shadow:0 0 0 4px color-mix(in srgb,var(--teal) 25%,transparent);animation:sdpulse 2s infinite}
@keyframes sdpulse{50%{box-shadow:0 0 0 7px transparent}}
.sd-status .sp{margin-left:auto;display:flex;gap:8px}
.sd-round{padding:14px 0;border-bottom:1px solid var(--line)}.sd-round:last-child{border:0}
.sd-round .hd{display:flex;align-items:center;gap:10px;margin-bottom:10px;font-size:13px}
.sd-round .hd b{font-size:14px}.sd-round .hd .muted{font-size:12px}
.sd-round .hd .tag{margin-left:auto;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:99px;background:color-mix(in srgb,var(--gold) 18%,transparent);color:var(--gold)}
.sd-round.off .hd .tag{background:var(--raised);color:var(--muted)}
.sd-row{display:grid;grid-template-columns:34px 130px 1fr 92px 26px;gap:10px;align-items:center;padding:4px 0;font-size:13px}
.sd-row img,.sd-row .ph{width:34px;height:34px;border-radius:9px}
.sd-row .ph{background:var(--raised)}
.sd-row .who{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sd-row .who small{display:block;color:var(--muted);font-size:11.5px}
.sd-bar{height:10px;border-radius:6px;background:var(--raised);overflow:hidden}
.sd-bar i{display:block;height:100%;border-radius:6px;background:var(--line2);transition:width .6s}
.sd-row.w .sd-bar i{background:linear-gradient(90deg,var(--gold),var(--gold2))}
.sd-row .dmg{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.sd-row .ok{width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font-weight:900;font-size:12px;color:#0c1220;background:var(--gold)}
.sd-round.off .sd-row{opacity:.55}
.sd-note{font-size:12.5px;color:var(--muted);margin-top:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sd-edit{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.sd-edit button{padding:6px 10px;border-radius:8px;border:1px solid var(--line2);font-size:12px;font-weight:600}
.sd-edit button.on{background:var(--gold);color:#0c1220;border-color:var(--gold)}
.sd-win{position:relative;overflow:hidden;margin-top:16px;border-radius:18px;border:1px solid var(--gold);min-height:220px;display:flex;align-items:flex-end;background:#0a0f1c}
.sd-win .art{position:absolute;inset:0;background-size:cover;background-position:center 20%;opacity:.55;transform:scale(1.04)}
.sd-win::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(6,9,18,.94) 0%,rgba(6,9,18,.7) 45%,rgba(6,9,18,.15) 100%)}
.sd-win .in{position:relative;z-index:1;padding:28px}
.sd-win .k{font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--gold)}
.sd-win h3{margin:6px 0 4px;font-size:34px;color:#fff;letter-spacing:-.02em}
.sd-win .s{color:#c9d3e6;font-size:14px}
.sd-win .acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
.sd-trophy{width:40px;height:40px;color:var(--gold);margin-bottom:6px}
.sd-hof{display:grid;grid-template-columns:28px 1fr 70px 70px 70px 110px;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}
.sd-hof:last-child{border:0}.sd-hof.h{color:var(--muted);font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.sd-hof span:nth-child(n+3){text-align:right;font-variant-numeric:tabular-nums}
.sd-past{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}.sd-past:last-child{border:0}
.sd-past .sc{margin-left:auto;font-weight:800;font-variant-numeric:tabular-nums}
.sd-mini{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.sd-mini .pp{display:flex;align-items:center;gap:7px;font-weight:600;font-size:13px}
.sd-mini .pp i{width:11px;height:11px;border-radius:4px;border:2px solid var(--line2);display:inline-block}
.sd-mini .pp i.on{background:var(--gold);border-color:var(--gold)}
@media (max-width:760px){.sd-steps{grid-template-columns:1fr}.sd-row{grid-template-columns:30px 1fr 70px 24px}.sd-row .sd-bar{display:none}.sd-hof{grid-template-columns:24px 1fr 60px 90px}.sd-hof span:nth-child(4),.sd-hof span:nth-child(5){display:none}}
#funTabs{flex-wrap:wrap}
html.rm .sd-pip.on,html.rm .sd-status .dot{animation:none}
'''

SETTINGS5 = r'''
      <h2 style="margin-top:18px">Party Showdown</h2>
      <div class="set"><div><b>Format</b><p>How many games a showdown lasts. The first player to win most of them takes it.</p></div><select id="sdFormat"><option value="3">Best of 3</option><option value="5">Best of 5</option></select></div>
      <div class="auto" id="setSD"></div>'''

HOME5 = r'''
    <div class="box" id="sdHome" style="display:none;margin-bottom:16px;cursor:pointer" onclick="go('showdown')" title="Open Party Showdown"></div>'''

NAV5 = r'''  <button class="nav" data-page="showdown" aria-label="Party Showdown"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="m13 19 6-6M16 16l4 4M19 21l2-2"/><path d="M9.5 17.5 21 6V3h-3L6.5 14.5"/><path d="m11 19-6-6M8 16l-4 4M5 21l-2-2"/></svg><span class="tip">Party Showdown</span></button>
'''

PAGE5 = r'''
  <!-- PARTY SHOWDOWN -->
  <section class="page" id="p-showdown"><div id="sdOut"></div></section>
'''

JS5 = r'''
// ---------------- Party Showdown
let SD = null, sdEdit = -1, sdSeenWinner = null;
const SD_COLORS = ['#d9b871','#19c8b4','#8ea2ff','#ff8a8a','#c08cff'];
const sdInit = n => esc((n||'?').trim().charAt(0).toUpperCase());
function sdAv(p, i, champ){ const c = champ && champIcons[champ]; return `<span class="sd-av" style="--av:${SD_COLORS[i % SD_COLORS.length]}">${c && c.icon ? `<img src="${esc(c.icon)}" alt="">` : sdInit(p.name)}</span>`; }
function syncFunTabs(){ document.querySelectorAll('#funTabs button').forEach(x=>x.classList.toggle('on', x.dataset.k===funTab)); }
async function loadSD(){ try { SD = await api('/api/showdown'); if (page === 'showdown') drawSD(); } catch(e){ console.error('showdown', e); } }
setInterval(()=>{ if (page === 'showdown' && sdEdit < 0) loadSD(); }, 4000);
async function sdAct(a, body){ await act(a, body || {}); sdEdit = -1; await loadSD(); }
const sdWhen = t => new Date(t * 1000).toLocaleTimeString([], {hour:'numeric', minute:'2-digit'});
const sdDate = t => new Date(t * 1000).toLocaleDateString([], {month:'short', day:'numeric'});
const SD_MODES = {KIWI:'ARAM Mayhem', ARAM:'ARAM', CLASSIC:"Summoner's Rift", CHERRY:'Arena', URF:'URF'};
const TROPHY = '<svg class="sd-trophy" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>';

function drawSD(){
  const el = q('#sdOut'); if (!SD) { el.innerHTML = '<div class="box"><div class="muted">Loading…</div></div>'; return; }
  const s = SD.series, bo = s ? s.best_of : SD.best_of_setting, auto = S && S.settings.showdown_auto;
  const head = `<div class="box"><div class="cs-head" style="margin:0"><div><h2 style="margin:0">Party Showdown</h2><div class="muted" style="font-size:12.5px">Most damage to champions wins each game. First to ${Math.floor(bo/2)+1} wins takes the showdown.</div></div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><div class="seg" role="group" aria-label="Format">${[3,5].map(n=>`<button class="${bo===n?'on':''}" onclick="sdAct('sd_best_of',{n:${n}})">Best of ${n}</button>`).join('')}</div>
    <label class="chk" style="padding:7px 10px;align-items:center"><input type="checkbox" ${auto?'checked':''} onchange="act('setting',{name:'showdown_auto'}).then(loadSD)"><div><b style="font-size:12.5px">Track automatically</b></div></label></div></div></div>`;
  let body = '';
  if (!s) body = sdEmpty(auto);
  else body = (s.winner ? sdWinner(s) : '') + sdBoard(s) + (s.winner ? '' : sdStatus(s)) + sdRounds(s);
  el.innerHTML = head + body + sdHall();
  if (s && s.winner && sdSeenWinner !== s.id){ if (sdSeenWinner !== null && !(S && S.settings.reduce_motion)) confetti(); sdSeenWinner = s.id; }
  else if (s && !s.winner && sdSeenWinner === null) sdSeenWinner = '';
}
function sdEmpty(auto){
  const party = SD.party || [], ok = party.length >= 2;
  return `<div class="sd-hero">${TROPHY}<h3>Who carries the party?</h3><p>Play a best of ${SD.best_of_setting} with the friends in your party. After every game LoLStat reads everyone's damage to champions, checks a box for whoever did the most, and crowns the winner.</p>
    <div class="sd-steps"><div><b>1 · Party up</b>Invite your friends to a lobby in League, any mode.</div><div><b>2 · Play</b>${auto ? 'LoLStat starts the showdown by itself when your first game together ends.' : 'Press Start below, then play your games.'}</div><div><b>3 · Most damage wins</b>Each game's top damage gets the point. First to ${Math.floor(SD.best_of_setting/2)+1} wins it all.</div></div>
    <div class="muted" style="font-size:12px;margin-top:18px;font-weight:700;letter-spacing:.05em;text-transform:uppercase">In your party now</div>
    <div class="sd-party">${party.length ? party.map((p,i)=>`<span class="sd-chip">${sdAv(p,i)}${esc(p.name)}${p.puuid===SD.me?' <span class="muted" style="font-weight:500">(you)</span>':''}</span>`).join('') : '<span class="muted" style="font-size:13px">Nobody yet. Open a lobby in League with your friends and they show up here.</span>'}</div>
    <div style="display:flex;gap:10px;margin-top:18px;align-items:center"><button class="btn gold" ${ok?'':'disabled style="opacity:.5;cursor:not-allowed"'} onclick="sdAct('sd_start')">Start a best of ${SD.best_of_setting}</button>${ok ? '' : '<span class="muted" style="font-size:12.5px">You need at least one friend in your lobby.</span>'}</div></div>`;
}
function sdBoard(s){
  return `<div class="sd-board">${s.players.map((p,i)=>{
    const champ = s.winner === p.puuid, lead = !s.winner && s.leader === p.puuid;
    const badge = champ ? '<span class="crown">Champion</span>' : lead ? '<span class="crown">Leading</span>' : p.match_point ? '<span class="crown mp">Match point</span>' : '';
    return `<div class="sd-p ${champ?'champ':''} ${lead?'lead':''}">${badge}${!s.winner && s.players.length > 2 ? `<button class="rm" title="Remove ${esc(p.name)} from this showdown" aria-label="Remove ${esc(p.name)}" onclick="if(confirm('Remove ${esc(p.name).replace(/'/g,'')} from this showdown?'))sdAct('sd_remove',{puuid:'${esc(p.puuid)}'})">✕</button>` : ''}
      <div class="sd-top">${sdAv(p,i,p.last_champ)}<div style="min-width:0"><div class="nm">${esc(p.name)}</div><div class="sub">${p.me ? 'You' : 'Party'}${p.last_champ ? ' · ' + esc(p.last_champ) : ''}</div></div><div class="wins" aria-label="${p.wins} wins">${p.wins}</div></div>
      <div class="sd-pips" aria-label="${p.wins} of ${s.need} wins">${Array.from({length:s.need},(_,k)=>`<span class="sd-pip ${k < p.wins ? 'on' : ''}">${k < p.wins ? '✓' : ''}</span>`).join('')}</div>
      <div class="nums"><div>Total damage<b>${fmt(p.total)}</b></div><div>Best game<b>${fmt(p.best)}</b></div></div>
      ${s.rounds.length ? `<div class="sd-diff ${p.diff > 0 ? 'up' : p.diff < 0 ? 'down' : ''}">${p.diff > 0 ? '+' + fmt(p.diff) + ' damage ahead in total' : p.diff < 0 ? fmt(-p.diff) + ' damage behind in total' : 'Even on total damage'}</div>` : ''}</div>`; }).join('')}</div>`;
}
function sdStatus(s){
  const n = s.rounds.length + 1, sc = s.players.map(p=>p.wins), mx = Math.max(...sc), lead = s.players.find(p=>p.puuid === s.leader);
  const mp = s.players.filter(p=>p.match_point);
  let t = !s.rounds.length ? 'Waiting for your first game together. Play a game and the result shows up here by itself.'
        : mp.length > 1 ? `It's ${s.score}. Game ${n} decides it.`
        : lead ? `${esc(lead.name)} leads ${s.score}. ${mp.length ? `One more win and ${esc(mp[0].name)} takes it.` : `Game ${n} is next.`}`
        : mx ? `Tied ${s.score}. Game ${n} is next.` : `No points yet. Game ${n} is next.`;
  return `<div class="sd-status"><span class="dot"></span><span>${t}</span><div class="sp">${s.rounds.length ? `<button class="btn" onclick="sdAct('sd_undo')">Undo last game</button>` : ''}<button class="btn" onclick="if(confirm('End this showdown? It goes into your history.'))sdAct('sd_end')">End showdown</button></div></div>`;
}
function sdRounds(s){
  if (!s.rounds.length) return '';
  const names = Object.fromEntries(s.players.map(p=>[p.puuid,p.name]));
  const rows = s.rounds.map((r,i)=>({r,i})).reverse().map(({r,i})=>{
    const st = s.players.map(p=>Object.assign({puuid:p.puuid, name:p.name}, r.stats[p.puuid] || {missing:true})).sort((a,b)=>(b.damage||0)-(a.damage||0));
    const mx = Math.max(1, ...st.map(x=>x.damage||0)), win = r.counted && r.winner;
    const meta = [SD_MODES[r.mode] || r.mode, r.minutes ? Math.round(r.minutes) + ' min' : '', sdWhen(r.when)].filter(Boolean).join(' · ');
    const tag = win ? `${esc(names[r.winner] || '')} wins${r.margin > 0 && r.runner_up ? ' by ' + fmt(r.margin) : ''}${r.manual ? ' (set by hand)' : ''}` : 'Not counted';
    const beat = win && r.margin > 0 && r.runner_up ? `<div class="sd-margin">${esc(names[r.winner])} did <b>${fmt(r.margin)}</b> more damage than ${esc(names[r.runner_up] || '')} this game</div>` : '';
    const missing = !r.counted && !r.manual && (r.note||'').includes("wasn't in");
    return `<div class="sd-round ${win?'':'off'}"><div class="hd"><b>Game ${i+1}</b><span class="muted">${esc(meta)}</span><span class="tag">${tag}</span></div>
      ${st.map(x=>{ const c = champIcons[x.champion] || {}; return `<div class="sd-row ${x.puuid===r.winner && win ? 'w' : ''}">${c.icon ? `<img src="${esc(c.icon)}" alt="">` : '<span class="ph"></span>'}<div class="who">${esc(x.name)}<small>${x.missing ? 'Not in this game' : esc(x.champion || '') + (x.k != null ? ` · ${x.k}/${x.d}/${x.a}` : '')}</small></div><div class="sd-bar"><i style="width:${x.missing ? 0 : (x.damage||0) / mx * 100}%"></i></div><span class="dmg">${x.missing ? '–' : fmt(x.damage||0)}</span>${x.puuid===r.winner && win ? '<span class="ok" aria-label="Winner">✓</span>' : '<span></span>'}</div>`; }).join('')}
      ${beat}<div class="sd-note">${r.note ? `<span>${esc(r.note)}</span>` : ''}${missing ? `<button class="btn" onclick="sdAct('sd_count',{round:${i}})">Count it anyway</button>` : ''}<button class="btn" style="margin-left:auto" onclick="sdEdit=${sdEdit===i?-1:i};drawSD()">${sdEdit===i?'Done':'Change result'}</button></div>
      ${sdEdit===i ? `<div class="sd-edit"><span class="muted" style="font-size:12px;align-self:center">Point goes to:</span>${s.players.map(p=>`<button class="${r.winner===p.puuid && r.counted?'on':''}" onclick="sdAct('sd_give',{round:${i},puuid:'${esc(p.puuid)}'})">${esc(p.name)}</button>`).join('')}<button class="${!r.counted?'on':''}" onclick="sdAct('sd_give',{round:${i},puuid:null})">Nobody (don't count)</button></div>` : ''}</div>`; }).join('');
  return `<div class="box" style="margin-top:16px"><h2>Games</h2>${rows}</div>`;
}
function sdWinner(s){
  const w = s.players.find(p=>p.puuid === s.winner) || {}, c = champIcons[w.last_champ] || {};
  const art = c.alias ? `/api/art?alias=${encodeURIComponent(c.alias)}&num=0&key=${encodeURIComponent(KEY)}` : '';
  const counted = s.rounds.filter(r=>r.counted).length;
  return `<div class="sd-win">${art ? `<div class="art" style="background-image:url('${art}')"></div>` : ''}<div class="in">${TROPHY}<div class="k">Showdown champion</div><h3>${esc(w.name || '')} wins!</h3>
    <div class="s">${s.score} in a best of ${s.best_of} · ${counted} ${counted===1?'game':'games'} · ${fmt(w.total||0)} total damage</div>
    ${s.damage_leader && s.damage_lead ? `<div class="s" style="margin-top:4px">${esc((s.players.find(p=>p.puuid===s.damage_leader)||{}).name||'')} did <b style="color:#fff">${fmt(s.damage_lead)}</b> more damage than anyone else across the showdown</div>` : ''}
    <div class="acts"><button class="btn gold" onclick="sdAct('sd_rematch')">Run it back</button>${s.best_of < 5 ? `<button class="btn" onclick="sdAct('sd_extend')">Keep going: make it a best of 5</button>` : ''}<button class="btn" onclick="sdCopy()">Copy result</button><button class="btn" onclick="sdAct('sd_end')">Close</button></div></div></div>`;
}
function sdResultText(s){
  const w = s.players.find(p=>p.puuid === s.winner) || {};
  const lines = [`${w.name} wins the LoLStat Party Showdown ${s.score} (best of ${s.best_of})`];
  s.rounds.forEach((r,i)=>{ if (!r.counted) return; lines.push(`Game ${i+1}: ` + s.players.filter(p=>r.stats[p.puuid]).map(p=>`${p.name} ${fmt(r.stats[p.puuid].damage||0)}${p.puuid===r.winner?' ✓':''}`).join(' · ') + (r.counted && r.margin > 0 ? ` (by ${fmt(r.margin)})` : '')); });
  if (s.damage_leader && s.damage_lead) lines.push(`Total damage: ${(s.players.find(p=>p.puuid===s.damage_leader)||{}).name} ahead by ${fmt(s.damage_lead)}`);
  return lines.join('\n');
}
async function sdCopy(){ try { await navigator.clipboard.writeText(sdResultText(SD.series)); toastMsg('Result copied. Paste it in Discord or your group chat.'); } catch(e){ toastMsg("Couldn't copy the result."); } }
function sdHall(){
  const L = SD.leaderboard || [], H = (SD.history || []).filter(h=>h.winner || h.games);
  if (!L.length) return '';
  return `<div class="two"><div class="box"><h2>Hall of fame</h2><div class="sd-hof h"><span>#</span><span>Player</span><span>Titles</span><span>Played</span><span>Games won</span><span>Damage</span></div>
      ${L.slice(0,10).map((b,i)=>`<div class="sd-hof"><b>${i+1}</b><span style="font-weight:600">${esc(b.name)}${b.puuid===SD.me?' <span class="muted" style="font-weight:500">(you)</span>':''}</span><span><b>${b.titles}</b></span><span>${b.series}</span><span>${b.rounds}</span><span>${fmt(b.damage)}</span></div>`).join('')}</div>
    <div class="box"><div class="cs-head" style="margin:0 0 6px"><h2 style="margin:0">Past showdowns</h2><button class="btn" style="font-size:11.5px;padding:5px 9px" onclick="if(confirm('Clear your showdown history?'))sdAct('sd_clear_history')">Clear</button></div>
      ${H.slice(0,8).map(h=>{ const w = h.players.find(p=>p.puuid===h.winner); return `<div class="sd-past">${TROPHY.replace('sd-trophy','').replace('<svg','<svg width="18" height="18" style="color:'+(w?'var(--gold)':'var(--muted)')+';flex:none"')}<div><b>${w ? esc(w.name) : 'No winner'}</b><div class="muted" style="font-size:11.5px">${sdDate(h.finished)} · best of ${h.best_of} · ${h.players.map(p=>esc(p.name)).join(', ')}${h.ended_early ? ' · ended early' : ''}</div></div><span class="sc">${h.players.map(p=>p.wins).sort((a,b)=>b-a).join('-')}</span></div>`; }).join('')}</div></div>`;
}
let sdSig = '';
function drawSdHome(st){
  const el = q('#sdHome'), s = st.showdown; if (!el) return;
  const sig = JSON.stringify(s); if (sig !== sdSig){ sdSig = sig; if (page === 'showdown' && sdEdit < 0) loadSD(); }   // a new game result shows at once
  if (!s){ el.style.display = 'none'; return; }
  el.style.display = '';
  const need = s.need;
  el.innerHTML = `<div class="sd-mini"><b style="font-size:13px">Party Showdown <span class="muted" style="font-weight:500">· best of ${s.best_of}${s.winner ? ' · ' + esc(s.winner) + ' wins!' : ' · ' + s.games + (s.games===1?' game':' games')}</span></b>${s.players.map(p=>`<span class="pp">${esc(p.name)} ${Array.from({length:need},(_,k)=>`<i class="${k<p.wins?'on':''}"></i>`).join('')}</span>`).join('')}<span class="muted" style="margin-left:auto;font-size:12px">Open →</span></div>`;
}
'''


def extend5(html):
    html = html.replace('''/* champ select */''', CSS5 + '''/* champ select */''', 1)
    html = html.replace('''<div class="box" id="tiltBox" style="display:none;margin-bottom:16px;border-color:var(--gold)"></div>''',
                        '''<div class="box" id="tiltBox" style="display:none;margin-bottom:16px;border-color:var(--gold)"></div>''' + HOME5, 1)
    html = html.replace('''      <h2 style="margin-top:18px">Wellbeing</h2>''', SETTINGS5.strip("\n") + '''
      <h2 style="margin-top:18px">Wellbeing</h2>''', 1)
    html = html.replace('''let lastTick = 0;''', JS5 + '''let lastTick = 0;''', 1)
    # the Challenges page becomes "Fun", with Party Showdown as its first tool
    html = html.replace('''let funTab = 'missions',''', '''let funTab = (()=>{ try { const t = localStorage.getItem('lolstat.fun'); return t && t !== 'showdown' ? t : 'missions'; } catch(e){ return 'missions'; } })(),''', 1)
    html = html.replace('''  <button class="nav" data-page="fun"''', NAV5 + '''  <button class="nav" data-page="fun"''', 1)
    html = html.replace('''  <!-- GAMES -->''', PAGE5 + '''  <!-- GAMES -->''', 1)
    html = html.replace('''live:'Live game', champs:'Champions',''', '''live:'Live game', showdown:'Party Showdown', champs:'Champions',''', 1)
    html = html.replace('''if (p==='champs') initChamps(); }''', '''if (p==='champs') initChamps(); if (p==='showdown'){ drawSD(); loadSD(); } }''', 1)
    html = html.replace('''funTab = b.dataset.k; document.querySelectorAll('#funTabs button')''', '''funTab = b.dataset.k; try { localStorage.setItem('lolstat.fun', funTab); } catch(e){} document.querySelectorAll('#funTabs button')''', 1)
    html = html.replace('''let lastTick = 0;''', '''setTimeout(()=>{ try { const p = localStorage.getItem('lolstat.page'); if (p && p !== 'home' && q('#p-' + p)) go(p); } catch(e){} }, 0);
let lastTick = 0;''', 1)
    html = html.replace('''<h2 style="margin:0">Challenges</h2><div class="muted" style="font-size:12.5px">Missions, this week's Chaos build, your augment collection and the build lab.</div>''',
                        '''<h2 style="margin:0">Fun</h2><div class="muted" style="font-size:12.5px">Missions, this week's Chaos build, your augment collection and the build lab.</div>''', 1)
    html = html.replace('''<button class="nav" data-page="fun" aria-label="Challenges">''', '''<button class="nav" data-page="fun" aria-label="Fun">''', 1)
    html = html.replace('''<span class="tip">Challenges</span>''', '''<span class="tip">Fun</span>''', 1)
    html = html.replace('''fun:'Challenges',''', '''fun:'Fun',''', 1)
    html = html.replace('''['fun','Challenges'],''', '''['fun','Fun'],['showdown','Party Showdown'],''', 1)
    # load + draw the showdown tab; the build lab redraws properly when you come back to it
    html = html.replace('''function drawFun(){
  const F = FUN, el = q('#funOut'); if (!F && funTab !== 'lab') return;''', '''function drawFun(){
  const el = q('#funOut'); if (funTab !== 'lab') delete el.dataset.lab;
  if (funTab === 'showdown'){ drawSD(); loadSD(); return; }
  const F = FUN; if (!F && funTab !== 'lab') return;''', 1)
    html = html.replace('''FUN = await api('/api/challenges' + (labChamp ? '?champ=' + encodeURIComponent(labChamp) : '')); drawFun();''',
                        '''if (funTab === 'showdown'){ drawFun(); return; } FUN = await api('/api/challenges' + (labChamp ? '?champ=' + encodeURIComponent(labChamp) : '')); drawFun();''', 1)
    html = html.replace('''  drawQol(st); drawTilt(st); reactive(st); launchModals(st);''', '''  drawQol(st); drawTilt(st); reactive(st); launchModals(st); drawSdHome(st); drawSdSettings(st);''', 1)
    html = html.replace('''['Troubleshooting','#trouble'],''', '''['Troubleshooting','#trouble'],['Party Showdown format (best of 3 or 5)','#sdFormat'],''', 1)
    html = html.replace('''let lastTick = 0;''', '''function drawSdSettings(st){
  const f = q('#sdFormat'); if (f && document.activeElement !== f) f.value = String(st.settings.showdown_best_of || 3);
  const b = q('#setSD'); if (b) b.innerHTML = toggleRow(st, [['showdown_auto','Track automatically','Start a showdown after your first game with a party, and score every game after it']]);
}
q('#sdFormat').onchange = () => act('sd_best_of', {n: +q('#sdFormat').value}).then(()=>{ if (page === 'showdown') loadSD(); });
let lastTick = 0;''', 1)
    return html


# ====================================================================== build breakdown (start → first back → core → boots → end game → situational)
CSS6 = r'''
/* build guide */
.guide{display:flex;flex-direction:column;gap:4px}
.gstep{position:relative;padding:12px 0 12px 34px;border-left:2px solid var(--line2);margin-left:11px}
.gstep:last-child{border-left-color:transparent}
.gstep .gn{position:absolute;left:-12px;top:10px;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:800;background:var(--raised);border:2px solid var(--line2);color:var(--muted)}
.gstep.key .gn{background:var(--gold);border-color:var(--gold);color:#0c1220}
.gstep .gh{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.gstep .gh b{font-size:13.5px}.gstep .gh span{font-size:12px;color:var(--muted)}
.gicons{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.gi{display:flex;align-items:center;gap:8px;padding:5px 10px 5px 5px;border-radius:10px;background:var(--raised);border:1px solid var(--line);font-size:12.5px;font-weight:600}
.gi img{width:30px;height:30px;border-radius:7px}
.gi .x2{color:var(--muted);font-weight:700;font-size:11.5px}
.garrow{color:var(--dim);font-weight:700}
.gstep .item{margin-bottom:8px}.gstep .item:last-child{margin-bottom:0}
.rush{display:inline-block;margin-left:8px;font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;padding:2px 7px;border-radius:6px;background:var(--gold);color:#0c1220;vertical-align:2px}
.sit{display:grid;grid-template-columns:40px 1fr;gap:10px;align-items:center;padding:8px 10px;border-radius:12px;border:1px solid var(--line);background:var(--raised);margin-bottom:6px}
.sit img{width:40px;height:40px;border-radius:9px}
.sit b{font-size:13px}.sit .st{font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);margin-left:6px}
.sit .w{font-size:12px;color:var(--muted)}
.sit.now{border-color:var(--gold);background:color-mix(in srgb,var(--gold) 10%,var(--raised))}
.sit.now .st{color:var(--gold)}
'''

JS6 = r'''
// ---------------- build guide: what to buy first, core, boots, end game, situational
function gIcons(items){
  const counted = []; items.forEach(it=>{ const c = counted.find(x=>x.id===it.id); if (c) c.n++; else counted.push(Object.assign({n:1}, it)); });
  return counted.map(it=>`<span class="gi" title="${esc(it.name)}${it.gold?' · '+it.gold+' gold':''}">${img(it.icon,'',30)}${esc(it.name)}${it.n>1?` <span class="x2">×${it.n}</span>`:''}</span>`).join('<span class="garrow">›</span>');
}
function gRow(it, n){ return `<div class="item ${it.owned?'owned':''}"><span class="n">${n}</span>${img(it.icon,'',48)}<div><b>${esc(it.name)}${it.rush?'<span class="rush">Rush</span>':''}${it.owned?'<span class="own">Owned</span>':''}</b><div class="why">${esc(it.why||'')}</div></div></div>`; }
function guideHtml(g){
  let n = 0; const step = (title, note, body, key) => `<div class="gstep ${key?'key':''}"><span class="gn">${++n}</span><div class="gh"><b>${title}</b>${note?`<span>${esc(note)}</span>`:''}</div>${body}</div>`;
  let h = '<div class="guide">';
  if (g.start && g.start.items.length) h += step('Start', g.start.note, `<div class="gicons">${gIcons(g.start.items)}</div>`);
  if (g.first_back && g.first_back.items.length) h += step('First back', g.first_back.note, `<div class="gicons">${gIcons(g.first_back.items)}</div>`);
  h += step('Core', 'Buy in this order. Rush the first one.', g.core.map((it,i)=>gRow(it, i+1)).join(''), true);
  if (g.boots && g.boots.item) h += step('Boots', g.boots.note, gRow(g.boots.item, 'B'));
  if (g.late.length) h += step('End game', 'Finish your build with these.', g.late.map((it,i)=>gRow(it, i+4)).join(''));
  if (g.situational.length) h += step('Situational', 'Swap one of your end game items for these when it fits the game.',
      g.situational.map(x=>`<div class="sit ${x.urgent?'now':''}">${img(x.icon,'',40)}<div><b>${esc(x.name)}</b><span class="st">${x.urgent?'Buy now · ':''}${esc(x.situation)}</span><div class="w">${esc(x.when.replace('Buy it now: ',''))}</div></div></div>`).join(''));
  return h + '</div>';
}
'''


def extend6(html):
    html = html.replace('''/* champ select */''', CSS6 + '''/* champ select */''', 1)
    html = html.replace('''let lastTick = 0;''', JS6 + '''let lastTick = 0;''', 1)
    html = html.replace('''q('#buildBlurb').textContent = b.blurb;''', '''q('#buildBlurb').textContent = m.builds_locked ? 'Locked for this game, the same as your item sets. ' + b.blurb : b.blurb;''', 1)
    a = '''q('#buildItems').innerHTML = rows.map('''
    assert a in html
    html = html.replace(a, '''q('#buildItems').innerHTML = b.guide ? guideHtml(b.guide) : rows.map(''', 1)
    a = '''<div class="items" style="margin-bottom:14px">${rows.map('''
    assert a in html
    html = html.replace(a, '''<div class="items" style="margin-bottom:22px">${b.guide ? guideHtml(b.guide) : rows.map(''', 1)
    return html


# ====================================================================== in-game panel look and size
SETTINGS7 = r'''
      <div class="set"><div><b>In-game panel look</b><p>Match the app's theme, match the champion and skin you're playing, or pick a theme just for the overlay.</p></div><select id="ovLook"></select></div>
      <div class="set"><div><b>In-game panel size</b><p>You can also drag the panel's bottom-right corner, or hold Ctrl and scroll over it.</p></div><div style="display:flex;align-items:center;gap:10px"><input type="range" id="ovSize" min="60" max="150" step="5"><span class="muted" id="ovSizeV" style="width:42px;text-align:right"></span></div></div>
      <div class="set"><div><b>In-game panel see-through</b><p>Lower lets more of the game show through.</p></div><div style="display:flex;align-items:center;gap:10px"><input type="range" id="ovAlpha" min="50" max="100" step="5"><span class="muted" id="ovAlphaV" style="width:42px;text-align:right"></span></div></div>'''

JS7 = r'''
// ---------------- in-game panel look, size and see-through
function ovLookFill(st){
  const sel = q('#ovLook'); if (!sel || document.activeElement === sel) return;
  const opts = [['app','Match the app'],['skin','Match my champion skin']].concat(Object.entries(THEMES).map(([k,t])=>['t:'+k, t.name || k]));
  if (sel.options.length !== opts.length) sel.innerHTML = opts.map(([v,l])=>`<option value="${v}">${esc(l)}</option>`).join('');
  sel.value = st.settings.overlay_look || 'app';
  const sz = q('#ovSize'), al = q('#ovAlpha');
  if (document.activeElement !== sz){ sz.value = Math.round((st.settings.panel_size || 0.85) * 100); }
  if (document.activeElement !== al){ al.value = Math.round((st.settings.overlay_alpha || 0.9) * 100); }
  q('#ovSizeV').textContent = sz.value + '%'; q('#ovAlphaV').textContent = al.value + '%';
}
q('#ovLook').onchange = async () => {
  const v = q('#ovLook').value;
  await act('set_value', {name:'overlay_look', value:v});
  if (v === 'app') act('set_value', {name:'overlay_theme', value:overlayTheme(themeOf(S.settings))});
  else if (v.startsWith('t:')) act('set_value', {name:'overlay_theme', value:overlayTheme(Object.assign({overlay:0.9}, THEMES[v.slice(2)]))});
  toastMsg(v === 'skin' ? 'The in-game panel will match the champion and skin you play.' : 'In-game panel look saved.');
};
q('#ovSize').oninput = () => { q('#ovSizeV').textContent = q('#ovSize').value + '%'; };
q('#ovSize').onchange = () => act('set_value', {name:'panel_size', value:+q('#ovSize').value / 100});
q('#ovAlpha').oninput = () => { q('#ovAlphaV').textContent = q('#ovAlpha').value + '%'; };
q('#ovAlpha').onchange = () => act('set_value', {name:'overlay_alpha', value:+q('#ovAlpha').value / 100});
'''


def extend7(html):
    a = '''<button class="switch" data-set="overlay"></button></div>'''
    assert html.count(a) == 1
    html = html.replace(a, a + SETTINGS7, 1)
    html = html.replace('''let lastTick = 0;''', JS7 + '''let lastTick = 0;''', 1)
    html = html.replace('''drawSdHome(st); drawSdSettings(st);''', '''drawSdHome(st); drawSdSettings(st); ovLookFill(st);''', 1)
    # the app's theme only restyles the overlay when the overlay is set to "Match the app"
    for a, b in [("act('set_value', {name:'theme', value:name}); act('set_value', {name:'overlay_theme', value:overlayTheme(t)});",
                  "act('set_value', {name:'theme', value:name}); if ((S.settings.overlay_look || 'app') === 'app') act('set_value', {name:'overlay_theme', value:overlayTheme(t)});"),
                 ("act('set_value', {name:'theme', value:'custom'}); act('set_value', {name:'overlay_theme', value:overlayTheme(t)}); });",
                  "act('set_value', {name:'theme', value:'custom'}); if ((S.settings.overlay_look || 'app') === 'app') act('set_value', {name:'overlay_theme', value:overlayTheme(t)}); });")]:
        assert html.count(a) == 1, a[:60]
        html = html.replace(a, b, 1)
    html = html.replace('''a small LoLStat button opens a panel with your builds and augments.''', '''a small LoLStat button opens a panel with your builds (locked for the whole game).''', 1)
    html = html.replace('''['Troubleshooting','#trouble'],''', '''['Troubleshooting','#trouble'],['In-game panel look and size','#ovLook'],''', 1)
    return html
