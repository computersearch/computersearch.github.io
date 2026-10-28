// Deck model and central registry. All deck files register themselves here.
class Deck {
  constructor(data) {
    this.slug = data.slug;
    this.name = data.name;
    this.rank = data.rank ?? 999;
    this.points = data.points ?? 0;
    this.share = data.share ?? '—';
    this.card = data.featuredCard ?? data.groups?.[0]?.cards?.[0];
    this.description = data.description ?? '';
    this.url = data.url ?? 'https://limitlesstcg.com/decks';
    this.groups = data.groups;
    this.validate();
  }
  validate() {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(this.slug)) throw Error('Invalid deck slug: '+this.slug);
    if (!Array.isArray(this.groups) || this.groups.length !== 3) throw Error('Deck must have three groups: '+this.slug);
    const total = this.groups.reduce((sum,g) => sum + g.cards.reduce((s,c) => s + Number(c[0]),0),0);
    if (total !== 60) throw Error(`${this.name} has ${total} cards, expected 60`);
    for (const g of this.groups) {
      const actual=g.cards.reduce((s,c)=>s+Number(c[0]),0);
      if (actual !== g.count) throw Error(`${this.name}: ${g.name} count mismatch`);
      for (const c of g.cards) if (c.length !== 4 || !c[1] || !c[2] || !c[3]) throw Error(`${this.name}: invalid card row`);
    }
  }
  exportText() { return this.groups.map(g=>`${g.name}: ${g.count}\n${g.cards.map(([q,n,s,no])=>`${q} ${n} ${s} ${no}`).join('\n')}`).join('\n\n'); }
}
class DeckRegistry {
  constructor() { this.bySlug=new Map(); }
  register(data) { const deck=new Deck(data); if(this.bySlug.has(deck.slug))throw Error('Duplicate deck: '+deck.slug); this.bySlug.set(deck.slug,deck); return deck; }
  get(slug) { return this.bySlug.get(slug); }
  all() { return [...this.bySlug.values()]; }
}
window.DeckforgeDecks = new DeckRegistry();
