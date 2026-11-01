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
        const isBye=!hasTable && (id===null || id===undefined || Number(id)<0) && Number(points)===3;
        return {round:i+1,opponent:other?.n || (isBye?'Bye':Number(id)<0?'Awaiting opponent':''),opponentCountry:other?.c||'',table:hasTable?table:null,result:isBye?'Bye':points===-1?'Pending':points===3?'Win':points===1?'Tie':points===0?'Loss':'Pending'};
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
  function moveWatch(key, offset) {
    const keys=[...watched()]; const index=keys.indexOf(key); const target=index+offset;
    if(index<0 || target<0 || target>=keys.length)return;
    [keys[index],keys[target]]=[keys[target],keys[index]];
    updateWatch(keys);
  }
  function renderSuggestions() {
    const box=$('suggestions'); box.replaceChildren(); const q=norm($('search').value); if(q.length<2)return;
    const tracked=new Set(watched()); const list=state.people.filter(p=>norm(nameOf(p)).includes(q) && !tracked.has(watchKey(p))).slice(0,12);
    if(!list.length){add(box,'div','tiny',state.snapshot?'No matching players in the published snapshot.':'No snapshot loaded yet.');return;}
    for(const p of list){const row=add(box,'div','suggestion');const label=add(row,'span','',nameOf(p));const c=country(p);if(c)label.append(document.createTextNode(' '+flag(c)+' '+c));row.append(btn('+ Follow',()=>{updateWatch([...watched(),watchKey(p)]);$('search').value='';renderSuggestions();},'primary'));}
  }
  function stat(box,label,value){const x=add(box,'div','stat');add(x,'small','',label);add(x,'strong','',value);}
  function render(){
    renderSuggestions(); renderBracket(); const root=$('players');root.replaceChildren();const keys=watched();$('count').textContent=keys.length;
    if(!keys.length){add(root,'div','empty','Search for a player above and choose “+ Follow”. Your watchlist stays in this browser.');return;}
    for(const [position,key] of keys.entries()){const p=state.people.find(x=>watchKey(x)===key);const panel=add(root,'article','player');const head=add(panel,'div','player-head');const top=add(head,'div','between');const left=add(top,'div');const nameRow=add(left,'div','player-name-row');add(nameRow,'h3','',p?nameOf(p):key);if(p){const c=country(p);if(c)add(left,'div','muted',`${flag(c)} ${c}`);}else add(left,'div','muted','Not present in latest snapshot');
      const controls=add(top,'div','watch-controls');
      const up=btn('↑',()=>moveWatch(key,-1),'move-player');up.title='Move player up';up.setAttribute('aria-label',`Move ${p?nameOf(p):key} up`);up.disabled=position===0;controls.append(up);
      const down=btn('↓',()=>moveWatch(key,1),'move-player');down.title='Move player down';down.setAttribute('aria-label',`Move ${p?nameOf(p):key} down`);down.disabled=position===keys.length-1;controls.append(down);
      controls.append(btn('Remove',()=>updateWatch(watched().filter(x=>x!==key))));
      const grid=add(head,'div','stats');stat(grid,'MATCH RECORD',p?record(p):'—');stat(grid,'POINTS',p?str(val(p,['p','points','matchPoints','match_points','score'])??'—'):'—');stat(grid,'RANK',p?rankOf(p):'—');
      const history=add(panel,'div','history');const rounds=p?matches(p):[];const latest=rounds[rounds.length-1];const dropRound=p?.d;const dropped=dropRound!==null && dropRound!==undefined && dropRound!=='' && dropRound!==false;if(dropped){const label=Number.isInteger(Number(dropRound)) && Number(dropRound)>0?`Dropped · Round ${dropRound}`:'Dropped';add(nameRow,'div','dropped-badge',label);}else if(latest && result(latest)==='Pending'){const live=add(nameRow,'div','still-playing');add(live,'span','live-dot');add(live,'span','','Still playing');}const toggle=btn(`Round history (${rounds.length}) ▾`,()=>{history.hidden=!history.hidden;toggle.textContent=`Round history (${rounds.length}) ${history.hidden?'▾':'▴'}`;});head.append(toggle);history.hidden=false;toggle.textContent=`Round history (${rounds.length}) ▴`;
      if(!rounds.length)add(history,'div','muted','Round-by-round opponents are not available in this snapshot.');
      for(let i=0;i<rounds.length;i++){const m=rounds[i];if(!m||typeof m!=='object')continue;const row=add(history,'div','match');add(row,'div','muted',`R${val(m,['round','roundNumber','round_number'])??i+1}`);const center=add(row,'div');const opp=opponent(m);const oc=val(m,['opponentCountry']);add(center,'div','',opp?(opp+(oc?' '+flag(oc):'')):'Opponent unavailable');const table=val(m,['table','tableNumber','table_number']);add(center,'div','tiny',table!==undefined && table!==null && table!==''?`Table ${table}`:'No table');const r=result(m);if(r==='Pending'){const badge=add(row,'div','result still-playing');add(badge,'span','live-dot');add(badge,'span','','Still playing');}else add(row,'div','result '+(/win|bye/i.test(r)?'win':/loss|lose/i.test(r)?'loss':/tie|draw/i.test(r)?'tie':''),r);}
    }
  }
  function renderBracket(){
    const root=$('bracket'); if(!root)return; root.replaceChildren();
    const raw=state.snapshot?.raw;
    const players=raw?.standings?.players;
    if(!Array.isArray(players))return;
    const seeded=players.filter(p=>Number.isInteger(p.top_cut_seed)&&p.top_cut_seed>0&&Number.isInteger(p.bracket_size)&&p.bracket_size>1);
    const sizes=[...new Set(seeded.map(p=>p.bracket_size))];
    const size=sizes.length===1?sizes[0]:NaN;
    const swiss=Number(raw.tournament?.day1)+Number(raw.tournament?.day2);
    if(!Number.isInteger(size)||size<2||(size&(size-1))!==0||!Number.isInteger(swiss)||swiss<1){
      add(root,'div','muted','Waiting for valid top-cut and Swiss-round metadata.');return;
    }
    const byId=new Map(players.map(p=>[Number(p.i),p]));
    const entrants=new Map(seeded.filter(p=>p.bracket_size===size&&p.top_cut_seed<=size).map(p=>[p.top_cut_seed,p]));
    const valid=p=>p&&entrants.get(p.top_cut_seed)===p;
    const stages=Math.log2(size);
    const pairKey=(a,b)=>[a.top_cut_seed,b.top_cut_seed].sort((x,y)=>x-y).join(':');
    const observed=Array.from({length:stages},()=>new Map());
    for(let stage=0;stage<stages;stage++){
      const index=swiss+stage;
      for(const p of entrants.values()){
        const entry=p.r?.[index]; if(!Array.isArray(entry))continue;
        const other=byId.get(Number(entry[0])); if(!valid(other)||other===p)continue;
        const key=pairKey(p,other);if(observed[stage].has(key))continue;
        const reverse=other.r?.[index];
        const reciprocal=Array.isArray(reverse)&&Number(reverse[0])===Number(p.i);
        const score=Number(entry[1]),otherScore=reciprocal?Number(reverse[1]):NaN;
        const decided=reciprocal&&((score===3&&otherScore===0)||(score===0&&otherScore===3));
        observed[stage].set(key,{p,other,winner:decided?(score===3?p:other):null,decided});
      }
    }
    // Lay out the recorded first-round games according to which winners meet next.
    // This avoids assuming the tournament follows a conventional 1-v-N seed bracket.
    const first=[...observed[0].values()];
    const used=new Set(first.flatMap(g=>[g.p.top_cut_seed,g.other.top_cut_seed]));
    const remaining=[...entrants.values()].filter(p=>!used.has(p.top_cut_seed)).sort((a,b)=>a.top_cut_seed-b.top_cut_seed);
    while(remaining.length>=2){first.push({p:remaining.shift(),other:remaining.shift(),winner:null,decided:false});}
    if(remaining.length)first.push({p:remaining.shift(),other:null,winner:null,decided:false});
    // An unmatched seed is kept visible, but never given an invented opponent or result.
    while(first.length<size/2)first.push(null);
    const groups=first.map((game,i)=>({games:[game],seeds:new Set(game?[game.p?.top_cut_seed,game.other?.top_cut_seed].filter(Boolean):[]),order:i}));
    let level=groups;
    const rounds=[[]];
    for(let stage=1;stage<stages;stage++){
      const next=[];const available=[...level];
      const links=[...observed[stage].values()];
      // Prefer links recorded for this stage; an unconfirmed pairing is still a valid link.
      for(const link of links){
        const a=available.find(g=>g.seeds.has(link.p.top_cut_seed));
        const b=available.find(g=>g.seeds.has(link.other.top_cut_seed));
        if(!a||!b||a===b)continue;
        available.splice(available.indexOf(a),1);available.splice(available.indexOf(b),1);
        next.push({children:[a,b],seeds:new Set([...a.seeds,...b.seeds]),order:Math.min(a.order,b.order)});
      }
      available.sort((a,b)=>a.order-b.order);
      while(available.length>=2){const a=available.shift(),b=available.shift();next.push({children:[a,b],seeds:new Set([...a.seeds,...b.seeds]),order:Math.min(a.order,b.order)});}
      if(available.length)next.push({children:[available.shift(),null],seeds:new Set(),order:Infinity});
      level=next;
    }
    // Traverse the resulting tree to obtain contiguous positions for every round.
    const ordered=Array.from({length:stages},()=>[]);
    function walk(node,stage){
      if(stage===0){ordered[0].push(node?.games?.[0]??null);return;}
      if(!node){for(let i=0;i<2**stage;i++)ordered[0].push(null);return;}
      walk(node.children?.[0],stage-1);walk(node.children?.[1],stage-1);
      ordered[stage].push(node);
    }
    // Rebuild all round columns by collecting nodes at each depth.
    const tree=level;
    const collect=(node,stage)=>{
      ordered[stage].push(node);
      if(stage>0){collect(node?.children?.[0]??null,stage-1);collect(node?.children?.[1]??null,stage-1);}
    };
    for(const row of ordered)row.length=0;
    for(const node of tree)collect(node,stages-1);
    const board=add(root,'div','bracket-board');
    for(let stage=0;stage<stages;stage++){
      const participants=size/(2**stage);
      const label=participants===2?'Final':participants===4?'Semifinals':participants===8?'Quarterfinals (Top 8)':`Top ${participants}`;
      const column=add(board,'section','bracket-column');add(column,'h3','bracket-heading',label);
      const slots=add(column,'div','bracket-slots');slots.style.setProperty('--round-depth',String(stage));
      for(const node of ordered[stage]){
        let game=null;
        if(stage===0)game=node?.games?.[0]??null;
        else if(node){
          const children=node.children||[];
          const candidate=children.map(child=>{
            if(!child)return null;
            if(stage===1)return child.games?.[0]?.winner??null;
            const prior=ordered[stage-1].includes(child)?null:null;
            return null;
          });
          const actual=[...observed[stage].values()].find(g=>node.seeds.has(g.p.top_cut_seed)&&node.seeds.has(g.other.top_cut_seed));
          if(actual)game=actual;
          else if(candidate[0]&&candidate[1])game={p:candidate[0],other:candidate[1],winner:null,decided:false};
        }
        if(!game){add(slots,'div','bracket-card muted','Awaiting bracket pairing');continue;}
        const card=add(slots,'div','bracket-card'+(game.decided?' complete':''));
        for(const player of [game.p,game.other].filter(Boolean)){
          const won=game.decided&&game.winner===player;
          const line=add(card,'div','bracket-player'+(won?' bracket-winner':game.decided?' bracket-loser':''));
          add(line,'span','bracket-player-name',`#${player.top_cut_seed} ${nameOf(player)}`);
          if(won)add(line,'span','bracket-check','✓');
        }
        add(card,'div','bracket-result',game.decided?`Winner: ${nameOf(game.winner)}`:'Awaiting confirmed result');
      }
    }
  }
  async function load(){
    $('status').textContent='Loading snapshot…';state.people=[];state.snapshot=null;render();
    try {const response=await fetch(`./data/${encodeURIComponent(state.event)}.json?t=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw new Error('Snapshot not available yet');const snap=await response.json();if(!snap || !(snap.raw||snap.standings?.players))throw new Error('Invalid snapshot');state.snapshot=snap.raw?snap:{...snap,raw:snap};state.people=playersFrom(state.snapshot.raw);const eventTitle=snap.raw?.tournament?.title || snap.event_name || state.events.find(e=>e.id===state.event)?.name || 'Tournament';$('event-title').textContent=eventTitle;const option=$('event').selectedOptions[0];if(option)option.textContent=eventTitle;const when=snap.fetched_at?new Date(snap.fetched_at).toLocaleString():'unknown';$('status').textContent=`${state.people.length} players · Updated ${when}`;if(!state.people.length)$('status').textContent='Snapshot fetched, but player fields could not be recognized — check JSON schema';}
    catch(e){$('status').textContent=`No published snapshot: ${e.message}`;}
    render();
  }
  async function init(){
    try{const response=await fetch('./events.json',{cache:'no-store'});if(!response.ok)throw new Error('Cannot load event list');const config=await response.json();state.events=(config.events||[]).filter(e=>e.enabled!==false);const selector=$('event');for(const e of state.events){const opt=make('option','',e.name);opt.value=e.id;selector.append(opt);}if(!state.events.length)throw new Error('No events configured');state.event=state.events[0].id;selector.addEventListener('change',()=>{state.event=selector.value;$('search').value='';load();});$('search').addEventListener('input',renderSuggestions);$('reload').addEventListener('click',load);await load();setInterval(load,5*60*1000);}
    catch(e){$('status').textContent=e.message;}
  }
  init();
})();
