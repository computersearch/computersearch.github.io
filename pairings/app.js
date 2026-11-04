'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const endpoint = String(window.PAIRINGS_API_URL || '').trim();
  let current = null;
  let fingerprint = '';
  let fetching = false;
  const clean = value => String(value ?? '').trim();
  const normalized = value => clean(value).normalize('NFKD').toLocaleLowerCase();
  const show = (id, visible) => { $(id).hidden = !visible; };
  const text = (id, value) => { $(id).textContent = value; };

  // Expected schema is documented in README.md. Never inject API content as HTML.
  function parse(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw Error('Invalid pairings response');
    const state = clean(data.status).toLowerCase();
    if (!['published', 'waiting'].includes(state)) throw Error('Unknown pairings status');
    if (state === 'waiting') return { status: 'waiting', tournament: clean(data.tournament), round: data.round };
    const tournament = clean(data.tournament);
    const division = clean(data.division);
    const round = Number(data.round);
    if (!tournament || !division || !Number.isSafeInteger(round) || round < 1 || !Array.isArray(data.matches) || data.matches.length > 2000) throw Error('Incomplete pairings data');
    const seen = new Set();
    const matches = data.matches.map(m => {
      const table = Number(m.table);
      const player1 = clean(m.player1), player2 = clean(m.player2);
      if (!Number.isSafeInteger(table) || table < 1 || !player1 || !player2 || player1.length > 200 || player2.length > 200 || seen.has(table)) throw Error('Invalid match data');
      seen.add(table);
      return { table, player1, player2 };
    }).sort((a, b) => a.table - b.table);
    return { status: 'published', tournament, division, round, matches, updated_at: clean(data.updated_at) };
  }
  function renderMatches() {
    const container = $('matches');
    container.replaceChildren();
    if (!current || current.status !== 'published') return;
    const query = normalized($('search').value);
    const matches = current.matches.filter(m => normalized(`${m.player1} ${m.player2}`).includes(query) || String(m.table).includes(query));
    for (const match of matches) {
      const card = document.createElement('article'); card.className = 'match';
      if (query && (normalized(match.player1).includes(query) || normalized(match.player2).includes(query))) card.classList.add('highlight');
      const table = document.createElement('div'); table.className = 'table-num';
      const caption = document.createElement('span'); caption.textContent = 'TABLE';
      const number = document.createElement('strong'); number.textContent = match.table;
      table.append(caption, number);
      const players = document.createElement('div'); players.className = 'players';
      for (const [index, name] of [match.player1, match.player2].entries()) {
        if (index) { const vs = document.createElement('span'); vs.className = 'vs'; vs.textContent = 'VS'; players.append(vs); }
        const player = document.createElement('div'); player.className = 'player'; player.textContent = name; players.append(player);
      }
      card.append(table, players); container.append(card);
    }
    text('result-count', `${matches.length} of ${current.matches.length} tables`);
    show('no-results', matches.length === 0);
    show('clear', Boolean(query));
  }
  function render() {
    const published = current?.status === 'published';
    text('tournament', clean(current?.tournament) || 'Waiting for pairings');
    text('division', published ? `${current.division} Division` : 'Pairings will appear here when published.');
    text('round', published ? `Round ${current.round}` : '');
    show('round', published);
    text('count', published ? `${current.matches.length} tables · ${current.matches.length * 2} players` : 'No active round');
    let updated = '';
    if (published && current.updated_at) {
      const date = new Date(current.updated_at);
      if (!Number.isNaN(date.getTime())) updated = `Published ${date.toLocaleString()}`;
    }
    text('updated', updated);
    show('results-section', published);
    show('empty-state', !published);
    text('empty-title', endpoint ? 'Waiting for the next round' : 'Pairings are not connected yet');
    text('empty-description', endpoint ? 'This page will update automatically when the organizer publishes pairings.' : 'The organizer will connect the Hostinger pairings endpoint before the first event.');
    if (published) renderMatches();
  }
  async function refresh() {
    if (!endpoint || fetching || document.hidden) return;
    fetching = true;
    try {
      const url = new URL(endpoint);
      if (url.protocol !== 'https:') throw Error('API must use HTTPS');
      url.searchParams.set('_', Date.now().toString());
      const response = await fetch(url, { cache: 'no-store', mode: 'cors', credentials: 'omit' });
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      const raw = await response.text();
      if (raw.length > 400000) throw Error('Response too large');
      const next = parse(JSON.parse(raw));
      const nextFingerprint = JSON.stringify(next);
      if (nextFingerprint !== fingerprint) { current = next; fingerprint = nextFingerprint; render(); }
      text('status', 'Up to date');
    } catch (error) {
      text('status', current?.status === 'published' ? 'Connection interrupted · showing last received round' : 'Unable to load pairings');
      console.warn('Pairings refresh:', error);
    } finally { fetching = false; }
  }
  $('search').addEventListener('input', renderMatches);
  $('clear').addEventListener('click', () => { $('search').value = ''; renderMatches(); $('search').focus(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  render();
  if (endpoint) { refresh(); setInterval(refresh, 15000); }
  else text('status', 'Awaiting Hostinger setup');
})();
