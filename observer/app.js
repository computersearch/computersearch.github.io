(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { events: [], event: '', snapshot: null, people: [], watched: readWatched() };
  function readWatched() { try { return JSON.parse(localStorage.getItem('cs-observer-watch-v1') || '{}'); } catch { return {}; } }
  function save() { try { localStorage.setItem('cs-observer-watch-v1', JSON.stringify(state.watched)); } catch {} }
  function val(o, keys) { if (!o || typeof o !== 'object') return undefined; for (const k of keys) if (o[k] !== undefined && o[k] !== null && o[k] !== '') return o[k]; }
  const str = x => x === undefined || x === null ? '' : String(x);
  const norm = s => str(s).normalize('NFKD').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  function nameOf(p) {
    const direct = val(p,['n','name','playerName','player_name','fullName','full_name','player']);
    if (typeof direct === 'string') return direct;
    if (direct && typeof direct === 'object') return nameOf(direct);
    return [val(p,['firstName','first_name','firstname']),val(p,['lastName','last_name','lastname'])].filter(Boolean).join(' ');
  }
  function arrayCandidates(raw) {
    const found=[]; const seen=new Set();
    function visit(v,depth) { if (!v || typeof v !== 'object' || depth > 5 || seen.has(v)) return; seen.add(v);
      if (Array.isArray(v)) { if (v.length && v.some(x=>x && typeof x==='object' && nameOf(x))) found.push(v); for (const x of v.slice(0,4)) visit(x,depth+1); }
      else for (const [key,x] of Object.entries(v)) if (!['matches','rounds','opponents','pairings','games'].includes(key.toLowerCase())) visit(x,depth+1);
    } visit(raw,0); return found;
  }
  function playersFrom(raw) {
    const arrays=arrayCandidates(raw).sort((a,b)=>b.filter(x=>x && typeof x==='object' && nameOf(x)).length-a.filter(x=>x && typeof x==='object' && nameOf(x)).length);
    const rows=(arrays[0]||[]).filter(x=>x && typeof x==='object' && nameOf(x));
    const unique=new Map(); for (const p of rows) { const n=norm(nameOf(p)); if (n && !unique.has(n)) unique.set(n,p); }
    return [...unique.values()]; // Pokédata standings are already sorted by rank.
  }
  function rankOf(p) {
    const rows=state.snapshot?.raw?.standings?.players;
    if(Array.isArray(rows)){const index=rows.indexOf(p);if(index>=0)return `#${index+1}`;}
    const rank=val(p,['rank','placement','place','position']);
    return rank===undefined?'—':`#${rank}`;
  }
  function country(p) { const c=val(p,['c','countryCode','country_code','country','nationality']); if (c && typeof c==='object') return str(val(c,['code','name'])); return str(c); }
  function flag(c) { c=str(c).trim().toUpperCase(); if(c==='UK')c='GB'; return /^[A-Z]{2}$/.test(c) ? String.fromCodePoint(...[...c].map(x=>127397+x.charCodeAt(0))) : ''; }
  function record(p) {
    if(Array.isArray(p.s) && p.s.length===3) return p.s.join('–');
    const rec=val(p,['record','matchRecord','match_record','standing']);
    if (typeof rec==='string') { const m=rec.match(/(\d+)\s*[-–]\s*(\d+)\s*[-–]\s*(\d+)/); if (m) return m.slice(1).join('–'); }
    const src=rec && typeof rec==='object' ? rec : p;
    const w=val(src,['wins','win','w']),l=val(src,['losses','loss','l']),t=val(src,['ties','draws','tie','draw','t']);
    return [w,l,t].every(x=>x!==undefined && Number.isFinite(Number(x))) ? `${w}–${l}–${t}` : '—';
  }
  function matches(p) {
    if(Array.isArray(p.r) && state.snapshot?.raw?.standings?.players){
      const byId=new Map(state.snapshot.raw.standings.players.map(x=>[Number(x.i),x]));
      return p.r.map((entry,i)=>{
        if(!Array.isArray(entry))return null;
        const [id,points,table]=entry;const other=byId.get(Number(id));
        const hasTable=Number.isFinite(Number(table)) && Number(table)>0;
        const isBye=!hasTable && (id===null || id===undefined || Number(id)<0);
        return {round:i+1,opponent:other?.n || (isBye?'Bye':''),opponentCountry:other?.c||'',table:hasTable?table:null,result:isBye?'Bye':points===-1?'Pending':points===3?'Win':points===1?'Tie':points===0?'Loss':'Pending'};
      }).filter(Boolean);
    }
    const a=val(p,['matches','rounds','matchHistory','match_history','pairings','games','opponents']);
    return Array.isArray(a) ? a : [];
  }
  function result(m) { const r=val(m,['result','outcome','status','matchResult','match_result']); return r===undefined ? 'Unknown' : str(r); }
  function opponent(m) { const o=val(m,['opponent','opponentName','opponent_name','opponentPlayer','opponent_player']); return typeof o==='string' ? o : o && typeof o==='object' ? nameOf(o) : ''; }
  function make(tag,cls,content) { const e=document.createElement(tag); if(cls)e.className=cls; if(content!==undefined)e.textContent=str(content); return e; }
  function add(parent,tag,cls,text) { const e=make(tag,cls,text); parent.append(e); return e; }
  function btn(text,fn,cls='') { const b=make('button',cls,text); b.type='button'; b.addEventListener('click',fn); return b; }
  function watchKey(p) { return norm(nameOf(p)); }
  function watched() { return state.watched[state.event] || []; }
  function updateWatch(keys) { state.watched[state.event]=keys; save(); render(); }
  // Floating preview + FLIP transitions: the original card keeps its layout slot,
  // while neighbouring cards glide into place instead of jumping.
  function installDrag(handle, panel, key) {
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !event.isPrimary) return;
      event.preventDefault();
      const root = $('players');
      const pointerId = event.pointerId;
      const startY = event.clientY;
      const startX = event.clientX;
      const originOrder = [...root.querySelectorAll('.player')];
      let active = false, preview = null, frame = 0, lastY = startY;
      handle.setPointerCapture(pointerId);

      const animateReflow = action => {
        const cards = [...root.querySelectorAll('.player')];
        const before = new Map(cards.map(card => [card, card.getBoundingClientRect().top]));
        action();
        for (const card of cards) {
          if (card === panel) continue;
          const delta = before.get(card) - card.getBoundingClientRect().top;
          if (Math.abs(delta) < 1) continue;
          card.getAnimations().forEach(animation => animation.cancel());
          card.animate([{transform:`translateY(${delta}px)`},{transform:'translateY(0)'}],
            {duration:210,easing:'cubic-bezier(.2,.8,.2,1)'});
        }
      };
      const draw = () => {
        frame = 0;
        if (preview) preview.style.transform = `translate3d(0,${lastY-startY}px,0)`;
      };
      const move = e => {
        if (e.pointerId !== pointerId) return;
        lastY = e.clientY;
        if (!active && Math.hypot(e.clientX-startX,e.clientY-startY) < 7) return;
        if (!active) {
          active = true;
          const rect = panel.getBoundingClientRect();
          preview = panel.cloneNode(true);
          preview.classList.add('drag-preview');
          preview.style.cssText = `position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;pointer-events:none;z-index:1000;margin:0;`;
          preview.setAttribute('aria-hidden','true');
          document.body.append(preview);
          panel.classList.add('drag-placeholder');
          document.body.classList.add('sorting-players');
        }
        if (!frame) frame = requestAnimationFrame(draw);
        const others = [...root.querySelectorAll('.player')].filter(card => card !== panel);
        const target = others.find(card => e.clientY < card.getBoundingClientRect().top + card.offsetHeight/2) || null;
        if (target !== panel.nextElementSibling) animateReflow(() => root.insertBefore(panel,target));
        // Gently scroll when dragging close to the viewport edge.
        if (e.clientY < 65) window.scrollBy(0,-12);
        else if (e.clientY > innerHeight-65) window.scrollBy(0,12);
      };
      const cleanup = () => {
        handle.removeEventListener('pointermove',move);
        handle.removeEventListener('pointerup',finish);
        handle.removeEventListener('pointercancel',cancel);
        if (frame) cancelAnimationFrame(frame);
        preview?.remove();
        panel.classList.remove('drag-placeholder');
        document.body.classList.remove('sorting-players');
      };
      const finish = e => {
        if (e.pointerId !== pointerId) return;
        cleanup();
        if (!active) return;
        const order = [...root.querySelectorAll('.player')].map(card => card.dataset.watchKey);
        if (order.length === watched().length && order.every(k => watched().includes(k))) {
          state.watched[state.event] = order;
          save();

        }
      };
      const cancel = e => {
        if (e.pointerId !== pointerId) return;
        cleanup();
        animateReflow(() => originOrder.forEach(card => root.append(card)));
      };
      handle.addEventListener('pointermove',move);
      handle.addEventListener('pointerup',finish);
      handle.addEventListener('pointercancel',cancel);
    });
  }
  function renderSuggestions() {
    const box=$('suggestions'); box.replaceChildren(); const q=norm($('search').value); if(q.length<2)return;
    const tracked=new Set(watched()); const list=state.people.filter(p=>norm(nameOf(p)).includes(q) && !tracked.has(watchKey(p))).slice(0,12);
    if(!list.length){add(box,'div','tiny',state.snapshot?'No matching players in the published snapshot.':'No snapshot loaded yet.');return;}
    for(const p of list){const row=add(box,'div','suggestion');const label=add(row,'span','',nameOf(p));const c=country(p);if(c)label.append(document.createTextNode(' '+flag(c)+' '+c));row.append(btn('+ Follow',()=>{updateWatch([...watched(),watchKey(p)]);$('search').value='';renderSuggestions();},'primary'));}
  }
  function stat(box,label,value){const x=add(box,'div','stat');add(x,'small','',label);add(x,'strong','',value);}
  function render(){
    renderSuggestions(); const root=$('players');root.replaceChildren();const keys=watched();$('count').textContent=keys.length;
    if(!keys.length){add(root,'div','empty','Search for a player above and choose “+ Follow”. Your watchlist stays in this browser.');return;}
    for(const [position,key] of keys.entries()){const p=state.people.find(x=>watchKey(x)===key);const panel=add(root,'article','player');panel.dataset.watchKey=key;const head=add(panel,'div','player-head');const top=add(head,'div','between');const left=add(top,'div');const nameRow=add(left,'div','player-name-row');add(nameRow,'h3','',p?nameOf(p):key);if(p){const c=country(p);if(c)add(left,'div','muted',`${flag(c)} ${c}`);}else add(left,'div','muted','Not present in latest snapshot');
      const controls=add(top,'div','watch-controls');
      const handle=btn('⠿',()=>{},'drag-handle');handle.title='Drag to reorder player';handle.setAttribute('aria-label',`Drag ${p?nameOf(p):key} to reorder`);controls.append(handle);installDrag(handle,panel,key);
      controls.append(btn('Remove',()=>updateWatch(watched().filter(x=>x!==key))));
      const grid=add(head,'div','stats');stat(grid,'MATCH RECORD',p?record(p):'—');stat(grid,'POINTS',p?str(val(p,['p','points','matchPoints','match_points','score'])??'—'):'—');stat(grid,'RANK',p?rankOf(p):'—');
      const history=add(panel,'div','history');const rounds=p?matches(p):[];const latest=rounds[rounds.length-1];if(latest && result(latest)==='Pending'){const live=add(nameRow,'div','still-playing');add(live,'span','live-dot');add(live,'span','','Still playing');}const toggle=btn(`Round history (${rounds.length}) ▾`,()=>{history.hidden=!history.hidden;toggle.textContent=`Round history (${rounds.length}) ${history.hidden?'▾':'▴'}`;});head.append(toggle);history.hidden=true;
      if(!rounds.length)add(history,'div','muted','Round-by-round opponents are not available in this snapshot.');
      for(let i=0;i<rounds.length;i++){const m=rounds[i];if(!m||typeof m!=='object')continue;const row=add(history,'div','match');add(row,'div','muted',`R${val(m,['round','roundNumber','round_number'])??i+1}`);const center=add(row,'div');const opp=opponent(m);const oc=val(m,['opponentCountry']);add(center,'div','',opp?(opp+(oc?' '+flag(oc):'')):'Opponent unavailable');const table=val(m,['table','tableNumber','table_number']);add(center,'div','tiny',table!==undefined && table!==null && table!==''?`Table ${table}`:'No table');const r=result(m);if(r==='Pending'){const badge=add(row,'div','result still-playing');add(badge,'span','live-dot');add(badge,'span','','Still playing');}else add(row,'div','result '+(/win|bye/i.test(r)?'win':/loss|lose/i.test(r)?'loss':/tie|draw/i.test(r)?'tie':''),r);}
    }
  }
  async function load(){
    $('status').textContent='Loading snapshot…';state.people=[];state.snapshot=null;render();
    try {const response=await fetch(`./data/${encodeURIComponent(state.event)}.json?t=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw new Error('Snapshot not available yet');const snap=await response.json();if(!snap || !snap.raw)throw new Error('Invalid snapshot');state.snapshot=snap;state.people=playersFrom(snap.raw);const eventTitle=snap.raw?.tournament?.title || snap.event_name || state.events.find(e=>e.id===state.event)?.name || 'Tournament';$('event-title').textContent=eventTitle;const option=$('event').selectedOptions[0];if(option)option.textContent=eventTitle;const when=snap.fetched_at?new Date(snap.fetched_at).toLocaleString():'unknown';$('status').textContent=`${state.people.length} players · Updated ${when}`;if(!state.people.length)$('status').textContent='Snapshot fetched, but player fields could not be recognized — check JSON schema';}
    catch(e){$('status').textContent=`No published snapshot: ${e.message}`;}
    render();
  }
  async function init(){
    try{const response=await fetch('./events.json',{cache:'no-store'});if(!response.ok)throw new Error('Cannot load event list');const config=await response.json();state.events=(config.events||[]).filter(e=>e.enabled!==false);const selector=$('event');for(const e of state.events){const opt=make('option','',e.name);opt.value=e.id;selector.append(opt);}if(!state.events.length)throw new Error('No events configured');state.event=state.events[0].id;selector.addEventListener('change',()=>{state.event=selector.value;$('search').value='';load();});$('search').addEventListener('input',renderSuggestions);$('reload').addEventListener('click',load);await load();setInterval(load,5*60*1000);}
    catch(e){$('status').textContent=e.message;}
  }
  init();
})();
