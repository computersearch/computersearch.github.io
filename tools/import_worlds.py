#!/usr/bin/env python3
"""Dedicated 2026 Worlds Masters importer (Limitless tournament 515).
The standings table on this specific Phase 2 results page is the Day 2 roster.
All rows on that source are marked day2=True based on source provenance,
not based on a finishing-rank cutoff. Published decklists are optional.
"""
import argparse, json, re, time, unicodedata
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
BASE="https://limitlesstcg.com"
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"tournaments"
TID="515"
session=requests.Session()
session.headers.update({"User-Agent":"ComputerSearch/1.0 (noncommercial tournament archive; respectful rate limiting)"})


def get(path):
    r=session.get(urljoin(BASE,path),timeout=45)
    r.raise_for_status()
    return BeautifulSoup(r.text,"html.parser")


def find_decks(soup):
    links={}
    for a in soup.select('a[href]'):
        href=a.get("href","")
        m=re.search(r"/decks/list/(\d+)(?:[/?#]|$)",href)
        if m:links[m[1]]=urljoin(BASE,href)
    return list(links.values())


def parse_deck(soup,tid,url):
    # Card links on Limitless use /cards/SET/COLLECTOR_NUMBER.
    cards=[]
    for a in soup.select('a[href]'):
        m=re.search(r"/cards/([A-Za-z0-9-]+)/([A-Za-z0-9-]+)(?:[/?#]|$)",a.get("href",""))
        if not m:continue
        label=a.get_text(" ",strip=True)
        match=re.match(r"^(\d+)\s+(.+)$",label)
        if not match:continue
        qty=int(match[1])
        if not 1<=qty<=60:continue
        cards.append(dict(quantity=qty,name=match[2],set=m[1],number=m[2]))
    if sum(x["quantity"] for x in cards)!=60:return None
    text=soup.get_text(" ",strip=True)
    # Deck page explicitly states "26th Place Regional Puebla - Sanjeev Viswan".
    # Locate tournament association and rank from the text near its name.
    tournament_links=[a for a in soup.select('a[href]') if re.search(r"/tournaments/"+re.escape(tid)+r"(?:[/?#]|$)",a.get("href",""))]
    if not tournament_links:return None
    rank=None
    name=None
    for a in tournament_links:
        parent=a.parent
        nearby=parent.get_text(" ",strip=True) if parent else ""
        match=re.search(r"(\d+)(?:st|nd|rd|th)\s+Place",nearby,re.I)
        if match:
            rank=int(match[1])
            # player name is generally the next anchor in the same list item
            links=parent.select('a[href]') if parent else []
            for x in links:
                if x is not a and "/players/" in x.get("href",""):
                    name=x.get_text(" ",strip=True)
                    break
            if name:break
    if not rank or rank<1 or not name:return None
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    archetype=title.split(" by ",1)[0].strip()
    return dict(rank=rank,name=name,deck=archetype,decklist=cards,decklist_url=url)


def standings(soup, limit=None):
    players={}
    for tr in soup.select("tr"):
        cells=tr.find_all("td",recursive=False)
        if len(cells)<2:continue
        raw=cells[0].get_text(" ",strip=True).lstrip("#").strip()
        if not raw.isdigit():continue
        rank=int(raw)
        if rank<1 or (limit is not None and rank>limit):continue
        name=cells[1].get_text(" ",strip=True)
        if name:players[rank]=dict(rank=rank,name=name,deck=None,decklist=None,decklist_url=None)
    return players


def worlds_decklists(soup, players, tid="515"):
    """Read inline Worlds lists. Quantities can be siblings of card anchors."""
    from bs4 import NavigableString, Tag
    from unicodedata import normalize

    def clean(x):
        return re.sub(r"\s+", " ", str(x or "")).strip()

    def norm(x):
        return re.sub(r"[^a-z0-9]", "", normalize("NFKD", str(x)).casefold().encode("ascii", "ignore").decode())

    # Build an ordered stream of visible text nodes. Unlike heading-only
    # searches, this also handles <span>1st</span><span>Andrew Hedrick</span>.
    strings=[n for n in soup.descendants if isinstance(n,NavigableString) and clean(n)
             and n.parent and n.parent.name not in ("script", "style", "noscript")]
    expected={rank:norm(p["name"]) for rank,p in players.items()}
    ordinal=re.compile(r"^(\d{1,3})(?:st|nd|rd|th)\s*(.*)$",re.I)
    headings=[]
    for i,n in enumerate(strings):
        value=clean(n)
        m=ordinal.fullmatch(value)
        if not m:continue
        rank=int(m[1])
        if rank not in expected:continue
        suffix=m[2]
        if norm(suffix)==expected[rank]:
            headings.append((i,rank))
        elif not suffix and i+1<len(strings) and norm(clean(strings[i+1]))==expected[rank]:
            headings.append((i,rank))
    headings=sorted(set(headings))
    print(f"Worlds: {len(headings)} player headings recognized",flush=True)

    card_re=re.compile(r"/cards/([A-Za-z0-9-]+)/([A-Za-z0-9-]+)(?:[/?#]|$)")
    # Associate each card anchor with the nearest text-node position.
    # A card's quantity is often a sibling text node, NOT part of the anchor.
    positions={id(n):i for i,n in enumerate(strings)}
    all_cards=[]
    for a in soup.select('a[href]'):
        m=card_re.search(a.get('href',''))
        if not m:continue
        own=[n for n in a.descendants if isinstance(n,NavigableString) and clean(n)]
        if not own:continue
        pos=positions.get(id(own[0]))
        if pos is None:continue
        all_cards.append((pos,a,m))
    print(f"Worlds: {len(all_cards)} card anchors found",flush=True)

    results=[]
    for h,(start,rank) in enumerate(headings):
        end=headings[h+1][0] if h+1<len(headings) else len(strings)
        section=[clean(n) for n in strings[start+1:end]]
        # The first meaningful text after player heading is the archetype;
        # skip split-name fragments and prices.
        archetype=""
        for value in section[:18]:
            if norm(value)==expected[rank] or re.fullmatch(r"\d+(?:st|nd|rd|th)",value,re.I):continue
            if re.fullmatch(r"(?:USD|EUR|[€$]?[\d,.]+[€$]?)",value,re.I):continue
            if re.fullmatch(r"Pok[eé]mon\s*\(\d+\)",value,re.I):break
            if value.lower() in ("copy to clipboard", "open all", "close all"):continue
            archetype=value
            break
        cards=[]
        for pos,a,m in all_cards:
            if not start<pos<end:continue
            label=clean(a.get_text(' ',strip=True))
            quantity=None
            name=label
            match=re.match(r"^(\d{1,2})\s+(.+)$",label)
            if match:
                quantity=int(match[1]);name=match[2]
            else:
                # e.g. <div class=card><span>4</span><a href=/cards/...>Dreepy</a></div>
                for node in (a.parent, a.parent.parent if a.parent else None):
                    if node is None:continue
                    value=clean(node.get_text(' ',strip=True))
                    match=re.match(r"^(\d{1,2})\s+"+re.escape(label)+r"(?:\s|$)",value,re.I)
                    if match:
                        quantity=int(match[1]);break
                if quantity is None and pos>0:
                    prev=clean(strings[pos-1])
                    match=re.fullmatch(r"(\d{1,2})",prev)
                    if match:quantity=int(match[1])
            if quantity is None or not 1<=quantity<=60:continue
            cards.append(dict(quantity=quantity,name=name,set=m[1],number=m[2]))
        total=sum(x['quantity'] for x in cards)
        if total==60 and archetype:
            results.append(dict(rank=rank,name=players[rank]['name'],deck=archetype,
                decklist=cards,decklist_url=f"{BASE}/tournaments/{tid}/decklists"))
        else:
            print(f"Worlds #{rank}: {len(cards)} card rows / {total} copies, archetype={archetype!r}",flush=True)
    return results



def normalize_name(name):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD",name).casefold().encode("ascii","ignore").decode())

def import_worlds(delay):
    path=f"/tournaments/{TID}"
    print(f"Worlds Phase 2 source: {BASE}{path}",flush=True)
    soup=get(path)
    players=standings(soup)
    print(f"Phase 2 standings: {len(players)} players; highest placement {max(players,default=0)}",flush=True)
    if not players:
        raise RuntimeError("No Phase 2 standings parsed; existing archive preserved")
    # This specific source is the Masters Phase 2 standings, not general
    # tournament standings. Membership in its rows is the Day 2 evidence.
    # Never infer qualification from a rank threshold or from a decklist link.
    for p in players.values():
        p['day2']=True
        p['day2_source']=f"{BASE}{path}"
    if len(players)!=143:
        print(f"WARNING: Expected 143 Phase 2 players, found {len(players)}. "
              "All retrieved roster entries are marked Day 2; review source completeness.",flush=True)
    pages=[(path,soup)]
    for extra in (f"{path}/decklists",):
        try:pages.append((extra,get(extra)))
        except requests.RequestException as exc:
            print(f"Optional page unavailable {extra}: {exc}",flush=True)
    links=[];seen=set()
    for url,page in pages:
        found=find_decks(page)
        print(f"Discovery {url}: {len(found)} decklist links",flush=True)
        for link in found:
            if link not in seen:seen.add(link);links.append(link)
    print(f"Discovered {len(links)} unique decklist URLs; processing ALL",flush=True)
    verified=0
    for link in links:
        try:
            item=parse_deck(get(link),TID,link)
            if item is None:
                print(f"SKIP unverified 60-card decklist: {link}",flush=True)
            elif item['rank'] not in players:
                print(f"SKIP decklist not on Phase 2 roster: {link}",flush=True)
            elif normalize_name(item['name'])!=normalize_name(players[item['rank']]['name']):
                print(f"SKIP name mismatch #{item['rank']}: {item['name']!r} vs {players[item['rank']]['name']!r}",flush=True)
            elif players[item['rank']]['decklist'] is None:
                players[item['rank']].update(item);verified+=1
        except (requests.RequestException,ValueError) as exc:
            print(f"SKIP {link}: {exc}",flush=True)
        time.sleep(delay)
    if not links and len(pages)>1:
        embedded=worlds_decklists(pages[-1][1],players,TID)
        for item in embedded:
            if item['rank'] in players and players[item['rank']]['decklist'] is None:
                players[item['rank']].update(item);verified+=1
    # Preserve standings even when no decklists are published/recognized.
    OUT.mkdir(parents=True,exist_ok=True)
    result=dict(id='limitless-515',name='2026 World Championships',date='2026-08-28',
        source=f'{BASE}{path}',provider='LimitlessTCG',event_type='World Championships',
        day2_total=143,day2_verified_count=len(players),
        standings=[players[i] for i in sorted(players)],
        note='Day 2 status comes from the Worlds Phase 2 standings roster. Only validated 60-card decklists are attached.')
    filename='limitless-515.json'
    (OUT/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    indexfile=OUT/'index.json'
    index=json.loads(indexfile.read_text()) if indexfile.exists() else []
    entry=dict(id=result['id'],name=result['name'],date=result['date'],file=filename,
        source=result['source'],verified_decks=verified,event_type=result['event_type'],
        day2_total=143,day2_verified_count=len(players))
    index=[e for e in index if e.get('id')!=entry['id']]+[entry]
    index.sort(key=lambda e:e.get('date',''),reverse=True)
    indexfile.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    print(f"SUCCESS: Worlds Phase 2: {len(players)} Day 2 roster players, "
          f"{len(links)} decklist URLs checked, {verified} verified 60-card decks",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tournament-id',default='515',help='Must be 515 (Worlds Phase 2 source)')
    p.add_argument('--delay',type=float,default=1.2)
    p.add_argument('--max-decks',type=int,default=None,help='Ignored; all discovered URLs processed')
    args=p.parse_args()
    if str(args.tournament_id)!='515':p.error('This parser only supports Worlds tournament 515')
    if args.max_decks is not None:print('INFO: --max-decks ignored; all URLs processed',flush=True)
    import_worlds(max(args.delay,1.0))

if __name__=='__main__':main()
