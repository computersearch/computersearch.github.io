#!/usr/bin/env python3
"""Dedicated 2026 Worlds Masters importer (Limitless tournament 515).
All standings rows are Day 2; inspect every player for an event-specific
decklist, and never infer that 128 list links means only 128 players.
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


def parse_deck_cards(soup, url):
    """Validate a 60-card list without relying on fragile page-header metadata."""
    cards=[]
    for a in soup.select('a[href]'):
        m=re.search(r"/cards/([A-Za-z0-9-]+)/([A-Za-z0-9-]+)(?:[/?#]|$)",a.get('href',''))
        if not m:continue
        label=a.get_text(' ',strip=True)
        match=re.match(r"^(\d{1,2})\s+(.+)$",label)
        if not match:continue
        qty=int(match[1])
        if not 1<=qty<=60:continue
        cards.append(dict(quantity=qty,name=match[2],set=m[1],number=m[2]))
    if sum(c['quantity'] for c in cards)!=60:return None
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    archetype=title.split(' by ',1)[0].strip()
    return dict(deck=archetype or None,decklist=cards,decklist_url=url)


def parse_deck_identity(soup):
    for a in soup.select('a[href]'):
        if not re.search(r"/tournaments/515(?:[/?#]|$)",a.get('href','')):continue
        parent=a.parent
        if parent is None:continue
        nearby=parent.get_text(' ',strip=True)
        match=re.search(r"(\d+)(?:st|nd|rd|th)\s+Place",nearby,re.I)
        if not match:continue
        for p in parent.select('a[href*="/players/"]'):
            name=p.get_text(' ',strip=True)
            if name:return int(match[1]),name
    return None


def roster_deck_links(soup,players):
    """Use tournament standings row as the authoritative player-to-list mapping."""
    mapped={}
    for tr in soup.select('tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)<2:continue
        raw=cells[0].get_text(' ',strip=True).lstrip('#').strip()
        if not raw.isdigit():continue
        rank=int(raw)
        if rank not in players:continue
        if normalize_name(cells[1].get_text(' ',strip=True))!=normalize_name(players[rank]['name']):continue
        for a in tr.select('a[href]'):
            m=re.search(r"/decks/list/(\d+)(?:[/?#]|$)",a.get('href',''))
            if m:mapped.setdefault(urljoin(BASE,a['href']),set()).add(rank)
    return mapped


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

def roster_player_profiles(soup, players):
    """Collect the profile URL for EVERY standings row, independently of deck links."""
    profiles={}
    for tr in soup.select('tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)<2:continue
        raw=cells[0].get_text(' ',strip=True).lstrip('#').strip()
        if not raw.isdigit():continue
        rank=int(raw)
        if rank not in players:continue
        if normalize_name(cells[1].get_text(' ',strip=True))!=normalize_name(players[rank]['name']):continue
        a=cells[1].select_one('a[href*="/players/"]') or tr.select_one('a[href*="/players/"]')
        if a:profiles[rank]=urljoin(BASE,a['href'])
    return profiles


def player_worlds_links(profile_soup):
    """Find list URLs in sections explicitly associated with tournament 515."""
    found=set()
    for a in profile_soup.select('a[href]'):
        href=a.get('href','')
        if not re.search(r'/decks/list/\d+(?:[/?#]|$)',href):continue
        for ancestor in list(a.parents)[:5]:
            if ancestor.name in ('body','html'):break
            if ancestor.select_one('a[href*="/tournaments/515"]') or re.search(r'(?:World Championships|Worlds).*2026|2026.*(?:World Championships|Worlds)',ancestor.get_text(' ',strip=True),re.I):
                found.add(urljoin(BASE,href));break
    return found


def import_worlds(delay):
    path=f"/tournaments/{TID}"
    print(f"Worlds Phase 2 source: {BASE}{path}",flush=True)
    soup=get(path)
    players=standings(soup)
    print(f"Phase 2 standings: {len(players)} players; highest placement {max(players,default=0)}",flush=True)
    if len(players) != 143:
        raise RuntimeError(f"Expected all 143 Worlds standings players; got {len(players)}. Refusing incomplete snapshot.")
    # This specific source is the Masters Phase 2 standings, not general
    # tournament standings. Membership in its rows is the Day 2 evidence.
    # Never infer qualification from a rank threshold or from a decklist link.
    for p in players.values():
        p['day2']=True
        p['day2_source']=f"{BASE}{path}"
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
    # A URL in the standings row already has a verified player/rank association.
    # Avoid rejecting it when the decklist page has different header markup.
    mapped=roster_deck_links(soup,players)
    print(f"Standings row associations: {len(mapped)} URLs covering "
          f"{len(set().union(*mapped.values()) if mapped else set())} players",flush=True)
    verified=0
    unassociated=[]
    # Cache each URL once, but attach it to every player whose own standings
    # row explicitly references that URL. Unique URLs != unique players.
    deck_cache={}
    for link in links:
        try:
            deck_soup=get(link)
            item=parse_deck_cards(deck_soup,link)
            deck_cache[link]=item
            if item is None:
                print(f"SKIP invalid/unrecognized 60-card decklist: {link}",flush=True)
                continue
            ranks=set(mapped.get(link,()))
            if not ranks:
                identity=parse_deck_identity(deck_soup)
                if identity:
                    candidate,name=identity
                    if candidate in players and normalize_name(name)==normalize_name(players[candidate]['name']):
                        ranks.add(candidate)
            if not ranks:
                unassociated.append(link)
                print(f"SKIP cannot match list to roster: {link}",flush=True)
            for rank in sorted(ranks):
                if players[rank]['decklist'] is None:
                    players[rank].update(item)
                    verified+=1
        except (requests.RequestException,ValueError) as exc:
            print(f"SKIP {link}: {exc}",flush=True)
        finally:
            time.sleep(delay)
    print(f"Worlds: {verified} verified player lists attached from {len(links)} unique URLs; "
          f"{len(unassociated)} valid URLs without roster association",flush=True)
    # Second pass checks player profiles for additional event-specific links.
    missing=[rank for rank,p in sorted(players.items()) if p['decklist'] is None]
    profiles=roster_player_profiles(soup,players)
    print(f"Worlds roster audit: {len(players)} players, {len(missing)} without attached lists, "
          f"{len(profiles)} player profiles available",flush=True)
    for rank in missing:
        player=players[rank]
        profile=profiles.get(rank)
        if not profile:
            print(f"MISSING #{rank} {player['name']}: no player profile link",flush=True)
            continue
        try:
            profile_soup=get(profile)
            candidates=sorted(player_worlds_links(profile_soup))
            print(f"PROFILE #{rank} {player['name']}: {len(candidates)} Worlds candidate URLs",flush=True)
            for url in candidates:
                try:
                    # An explicit standings-row association is authoritative.
                    # Do not infer that a list belongs to a player solely
                    # because the profile links to it: validate identity otherwise.
                    if url in deck_cache:
                        item=deck_cache[url]
                        if item is None:continue
                        if rank not in mapped.get(url,set()):
                            continue
                    else:
                        deck_soup=get(url)
                        item=parse_deck_cards(deck_soup,url)
                        deck_cache[url]=item
                        if item is None:continue
                        identity=parse_deck_identity(deck_soup)
                        if not identity or identity[0]!=rank or normalize_name(identity[1])!=normalize_name(player['name']):
                            print(f"SKIP profile candidate without matching Worlds identity: {url}",flush=True)
                            continue
                    player.update(item)
                    verified+=1
                    print(f"RECOVERED #{rank} {player['name']}: {url}",flush=True)
                    break
                except requests.RequestException as exc:
                    print(f"SKIP profile candidate {url}: {exc}",flush=True)
                finally:
                    if url not in links:time.sleep(delay)
        except requests.RequestException as exc:
            print(f"SKIP player profile #{rank} {player['name']}: {exc}",flush=True)
        finally:
            time.sleep(delay)
    remaining=[p for p in players.values() if p['decklist'] is None]
    print(f"Worlds final roster audit: {len(players)} players; {verified} verified lists; "
          f"{len(remaining)} still missing",flush=True)
    for player in remaining:
        print(f"UNRESOLVED #{player['rank']} {player['name']}",flush=True)
    if len(pages)>1 and remaining:
        embedded=worlds_decklists(pages[-1][1],players,TID)
        for item in embedded:
            if item['rank'] in players and players[item['rank']]['decklist'] is None:
                players[item['rank']].update(item);verified+=1
    remaining=[p for p in players.values() if p["decklist"] is None]
    print(f"FINAL: {len(players)} Worlds players, {verified} validated decklists, {len(remaining)} without a verified list",flush=True)
    # The source is the confirmed Worlds roster: only its members are saved.
    # Preserve those standings even when no decklists are published/recognized.
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
