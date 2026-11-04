'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const endpoint = String(window.PAIRINGS_API_URL || '').trim();
  let current = null;
  let fingerprint = '';
  let fetching = false;
  let selectedDivision = 'All';
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
    const divisions = Array.isArray(data.divisions) ? data.divisions.map(clean) : [division];
    if (!divisions.length || divisions.some(d => !d || d.length > 80) || new Set(divisions).size !== divisions.length) throw Error('Invalid divisions');
    const round = Number(data.round);
    if (!tournament || !division || !Number.isSafeInteger(round) || round < 1 || !Array.isArray(data.matches) || data.matches.length > 2000) throw Error('Incomplete pairings data');
    const seen = new Set();
    const matches = data.matches.map(m => {
      const matchDivision = clean(m.division) || division;
      if (!divisions.includes(matchDivision)) throw Error('Unknown match division');
      const bye = m.bye === true;
      const table = bye ? null : Number(m.table);
      const player1 = clean(m.player1), player2 = clean(m.player2);
      if (!player1 || player1.length > 200 || player2.length > 200) throw Error('Invalid player name');
      if (bye) {
        if (player2 || m.table !== null) throw Error('Invalid BYE data');
      } else {
        if (!Number.isSafeInteger(table) || table < 1 || !player2 || seen.has(`${matchDivision}:${table}`)) throw Error('Invalid match data');
        seen.add(`${matchDivision}:${table}`);
      }
      const record1 = clean(m.record1), record2 = clean(m.record2);
      const validRecord = value => /^\d+-\d+-\d+$/.test(value);
      if (record1 && !validRecord(record1)) throw Error('Invalid player record');
      if (record2 && !validRecord(record2)) throw Error('Invalid opponent record');
      return { division: matchDivision, table, player1, player2, record1, record2, static1: m.static1 === true, static2: m.static2 === true, bye };
    }).sort((a, b) => (a.bye ? 1 : 0) - (b.bye ? 1 : 0) || (a.table ?? 0) - (b.table ?? 0));
    return { status: 'published', tournament, division, divisions, round, matches, updated_at: clean(data.updated_at) };
  }
  function renderMatches() {
    const container = $('matches');
    container.replaceChildren();
    if (!current || current.status !== 'published') return;
    const query = normalized($('search').value);
    const matches = current.matches.filter(m => (selectedDivision === 'All' || m.division === selectedDivision || Boolean(query)) && (normalized(`${m.player1} ${m.player2}`).includes(query) || (!m.bye && String(m.table).includes(query))));
    for (const match of matches) {
      const card = document.createElement('article'); card.className = 'match';
      if (query && (normalized(match.player1).includes(query) || normalized(match.player2).includes(query))) card.classList.add('highlight');
      const table = document.createElement('div'); table.className = 'table-num';
      const caption = document.createElement('span'); caption.textContent = match.bye ? 'STATUS' : 'TABLE';
      const number = document.createElement('strong'); number.textContent = match.bye ? 'BYE' : match.table;
      table.append(caption, number);
      if (current.divisions.length > 1 && (selectedDivision === 'All' || query)) { const tag = document.createElement('span'); tag.className = 'division-label'; tag.textContent = match.division; table.append(tag); }
      const players = document.createElement('div'); players.className = 'players';
      for (const [index, name] of (match.bye ? [match.player1] : [match.player1, match.player2]).entries()) {
        if (index) { const vs = document.createElement('span'); vs.className = 'vs'; vs.textContent = 'VS'; players.append(vs); }
        const player = document.createElement('div'); player.className = 'player';
        const playerName = document.createElement('span'); playerName.className = 'player-name'; playerName.textContent = name;
        player.append(playerName);
        if (index === 0 ? match.static1 : match.static2) { const badge = document.createElement('span'); badge.className = 'static-seat-badge'; badge.textContent = '★ Static Seat'; player.append(badge); }
        const record = index === 0 ? match.record1 : match.record2;
        if (record) { const recordText = document.createElement('span'); recordText.className = 'player-record'; recordText.textContent = record.replaceAll("-", "/"); player.append(recordText); }
        players.append(player);
      }
      if (match.bye) { const note = document.createElement('span'); note.className = 'vs'; note.textContent = 'No opponent this round'; players.append(note); }
      card.append(table, players); container.append(card);
    }
    const visibleTotal = selectedDivision === 'All' ? current.matches.length : current.matches.filter(m => m.division === selectedDivision).length;
    text('result-count', `${matches.length} of ${query ? current.matches.length : visibleTotal} pairings`);
    show('no-results', matches.length === 0);
    show('clear', Boolean(query));
  }
  function renderDivisions() {
    const tabs = $('division-tabs');
    tabs.replaceChildren();
    if (!current || current.status !== 'published' || current.divisions.length < 2) { tabs.hidden = true; return; }
    tabs.hidden = false;
    if (selectedDivision !== 'All' && !current.divisions.includes(selectedDivision)) selectedDivision = 'All';
    for (const division of ['All', ...current.divisions]) {
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'division-tab' + (division === selectedDivision ? ' active' : '');
      button.textContent = division;
      button.setAttribute('aria-pressed', String(division === selectedDivision));
      button.addEventListener('click', () => { selectedDivision = division; $('search').value = ''; renderDivisions(); renderMatches(); });
      tabs.append(button);
    }
  }
  function render() {
    const published = current?.status === 'published';
    text('tournament', clean(current?.tournament) || 'Waiting for pairings');
    text('division', published ? (current.divisions.length > 1 ? current.divisions.join(' · ') : `${current.division} Division`) : 'Pairings will appear here when published.');
    text('round', published ? `Round ${current.round}` : '');
    show('round', published);
    text('count', published ? `${current.matches.filter(m => !m.bye).length} tables · ${current.matches.filter(m => m.bye).length} BYEs · ${current.matches.reduce((n, m) => n + (m.bye ? 1 : 2), 0)} players` : 'No active round');
    let updated = '';
    if (published && current.updated_at) {
      const date = new Date(current.updated_at);
      if (!Number.isNaN(date.getTime())) updated = `Published ${date.toLocaleString()}`;
    }
    text('updated', updated);
    show('results-section', published);
    show('empty-state', !published);
    text('empty-title', endpoint ? 'Waiting for the next round' : 'Awaiting setup');
    text('empty-description', endpoint ? 'This page will update automatically when the organizer publishes pairings.' : 'The organizer will connect the pairings endpoint before the event.');
    renderDivisions();
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
  else text('status', 'Awaiting setup');
})();
