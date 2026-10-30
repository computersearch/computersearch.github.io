#!/usr/bin/env python3
"""Import verified Masters Division Regional and 2026 Worlds decklists from LimitlessTCG.
Runs on GitHub Actions; never fabricates unavailable lists.
Requires: requests, beautifulsoup4.
"""
import argparse, json, re, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE="https://limitlesstcg.com"
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"tournaments"
HEADERS={"User-Agent":"ComputerSearch/1.0 (noncommercial tournament archive; respectful rate limiting)"}
session=requests.Session()
session.headers.update(HEADERS)

def get(path):
    r=session.get(urljoin(BASE,path),timeout=45)
    r.raise_for_status()
    return BeautifulSoup(r.text,"html.parser")

def tournament_ids():
    soup=get("/tournaments")
    events=[]
    for a in soup.select('a[href]'):
        href=a.get("href","")
        m=re.fullmatch(r"/tournaments/(\d+)",href)
        if not m:continue
        label=a.get_text(" ",strip=True)
        if "Regional" not in label:continue
        if m[1] not in [x[0] for x in events]:events.append((m[1],label))
    return events

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
    if not rank or not 1<=rank<=64 or not name:return None
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    archetype=title.split(" by ",1)[0].strip()
    return dict(rank=rank,name=name,deck=archetype,decklist=cards,decklist_url=url)

def standings(soup):
    players={}
    for tr in soup.select("tr"):
        cells=tr.find_all("td",recursive=False)
        if len(cells)<2:continue
        raw=cells[0].get_text(" ",strip=True).lstrip("#").strip()
        if not raw.isdigit():continue
        rank=int(raw)
        if rank>64 or rank<1:continue
        name=cells[1].get_text(" ",strip=True)
        if name:players[rank]=dict(rank=rank,name=name,deck=None,decklist=None,decklist_url=None)
    return players

def worlds_decklists(soup, players, tid="515"):
    """Parse Worlds' expanded /decklists page, which has no /decks/list links.

    Each published list is an inline section beginning with a placement and
    player name, followed by an archetype and linked card rows. We match both
    name AND rank against the official standings and require exactly 60 cards.
    """
    from bs4 import NavigableString, Tag
    from unicodedata import normalize

    def norm(value):
        return re.sub(r"[^a-z0-9]+", "", normalize("NFKD", value).casefold().encode("ascii", "ignore").decode())

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    # Traverse text and anchors in their real DOM order. The Worlds page's
    # headings may be plain text inside a div, rather than h2/h3 elements.
    nodes=list(soup.descendants)
    order={id(node):i for i,node in enumerate(nodes)}
    name_by_rank={rank:norm(p["name"]) for rank,p in players.items()}
    heading_re=re.compile(r"^(\d{1,3})(?:st|nd|rd|th)\s+(.+)$",re.I)
    headings=[]
    for i,node in enumerate(nodes):
        if not isinstance(node,NavigableString):continue
        value=clean(node)
        m=heading_re.fullmatch(value)
        if not m:continue
        rank=int(m[1])
        if rank in name_by_rank and norm(m[2])==name_by_rank[rank]:
            headings.append((i,rank))
    # Some page variants separate the ordinal and the player name into two
    # text nodes. Support those without relaxing the name/placement check.
    if not headings:
        strings=[(i,clean(n)) for i,n in enumerate(nodes) if isinstance(n,NavigableString) and clean(n)]
        for k,(i,value) in enumerate(strings[:-1]):
            m=re.fullmatch(r"(\d{1,3})(?:st|nd|rd|th)",value,re.I)
            if m and int(m[1]) in name_by_rank and norm(strings[k+1][1])==name_by_rank[int(m[1])]:
                headings.append((i,int(m[1])))
    headings=sorted(set(headings))
    print(f"Worlds inline player headings matching standings: {len(headings)}",flush=True)
    card_re=re.compile(r"/cards/([A-Za-z0-9-]+)/([A-Za-z0-9-]+)(?:[/?#]|$)")
    card_links=[]
    for a in soup.select('a[href]'):
        m=card_re.search(a.get('href',''))
        if m:card_links.append((order.get(id(a),-1),a,m))
    results=[]
    for pos,(start,rank) in enumerate(headings):
        end=headings[pos+1][0] if pos+1<len(headings) else len(nodes)
        # Only the first named archetype before the Pokémon category heading
        # is accepted; no guesses from card names.
        before=[]
        for node in nodes[start+1:end]:
            if not isinstance(node,NavigableString):continue
            value=clean(node)
            if re.fullmatch(r"Pok[eé]mon\s*\(\d+\)",value,re.I):break
            if value:before.append(value)
        archetype=''
        for value in before:
            if value in ('USD','EUR') or re.fullmatch(r"[€$]?\s*\d+(?:[.,]\d+)?\s*[€$]?",value):continue
            if re.fullmatch(r"Pok[eé]mon|Trainer|Energy",value,re.I):continue
            # Ignore currency-only and site navigation text.
            if value.lower() in ('copy to clipboard','open all','close all'):continue
            archetype=value
            break
        cards=[]
        for i,a,m in card_links:
            if i<=start or i>=end:continue
            label=clean(a.get_text(' ',strip=True))
            found=re.fullmatch(r"(\d{1,2})\s+(.+)",label)
            if not found:continue
            qty=int(found[1])
            if not 1<=qty<=60:continue
            cards.append(dict(quantity=qty,name=found[2],set=m[1],number=m[2]))
        total=sum(card['quantity'] for card in cards)
        if total==60 and archetype:
            results.append(dict(rank=rank,name=players[rank]['name'],deck=archetype,
                decklist=cards,decklist_url=f"{BASE}/tournaments/{tid}/decklists"))
        elif cards:
            print(f"SKIP Worlds #{rank} ({players[rank]['name']}): {total} cards; archetype={archetype!r}")
    return results

def import_event(tid,delay,max_decks):
    print(f"Checking Limitless tournament {tid}",flush=True)
    soup=get(f"/tournaments/{tid}")
    heading=soup.find("h1")
    name=heading.get_text(" ",strip=True) if heading else f"Regional {tid}"
    is_worlds=(str(tid)=="515" and "World" in name)
    if "Regional" not in name and not is_worlds:
        raise ValueError("Event is neither a Regional Championship nor verified 2026 Worlds: "+name)
    players=standings(soup)
    if len(players)<64:
        try:players=standings(get(f"/tournaments/{tid}/standings"))
        except requests.HTTPError:pass
    if len(players)<64:
        print(f"NO UPDATE: only {len(players)}/64 placements; preserving existing data")
        return False
    event_text=soup.get_text(" ",strip=True)
    soup=get(f"/tournaments/{tid}/decklists")
    links=find_decks(soup)
    verified=0
    if is_worlds:
        embedded=worlds_decklists(soup,players)
        print(f"Found {len(embedded)} verified embedded Worlds decklists",flush=True)
        for item in embedded[:max_decks]:
            players[item["rank"]].update(item)
            verified+=1
    print(f"Found {len(links)} separate decklist links; checking up to {max_decks}",flush=True)
    for link in links[:max(0,max_decks-verified)]:
        try:
            item=parse_deck(get(link),tid,link)
            if item and item["rank"] in players:
                expected=players[item["rank"]]["name"]
                # No rank-only merge: the names must match.
                if re.sub(r"\W+","",expected.casefold())==re.sub(r"\W+","",item["name"].casefold()):
                    players[item["rank"]].update(item)
                    verified+=1
                else:print(f"Name mismatch at #{item['rank']}: {expected!r} vs {item['name']!r}")
        except (requests.RequestException,ValueError) as exc:
            print(f"SKIP {link}: {exc}")
        time.sleep(delay)
    if is_worlds:
        # Every top-64 Masters player reached the final standings phase.
        for player in players.values():player["day2"]=True
    if verified==0:
        print("NO UPDATE: no verified 60-card lists matched player standings; preserving existing data")
        return False
    # The original tournament page has a visible date, but do not invent it.
    match=re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d\d)",event_text)
    date=datetime.strptime(" ".join(match.groups()),"%d %B %Y").date().isoformat() if match else ""
    if is_worlds:
        # Confirmed 2026 Masters event start date; avoid accidentally using a different date from page copy.
        date="2026-08-28"
        name="2026 World Championships"
    result=dict(id="limitless-"+tid,name=name,date=date,source=f"{BASE}/tournaments/{tid}",
        provider="LimitlessTCG",standings=[players[i] for i in range(1,65)],
        note="Only publicly published, validated 60-card lists are displayed.")
    OUT.mkdir(exist_ok=True)
    filename=f"limitless-{tid}.json"
    (OUT/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    indexfile=OUT/"index.json"
    index=json.loads(indexfile.read_text()) if indexfile.exists() else []
    entry=dict(id=result["id"],name=name,date=date,file=filename,source=result["source"],verified_decks=verified)
    index=[x for x in index if x.get("id")!=entry["id"]]+[entry]
    index.sort(key=lambda x:x.get("date",""),reverse=True)
    indexfile.write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n")
    print(f"SUCCESS: {name}: 64 placements, {verified} verified 60-card lists")
    return True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--tournament-id",help="Main Limitless numeric tournament ID (e.g. 515 for 2026 Worlds)")
    p.add_argument("--delay",type=float,default=1.2)
    p.add_argument("--max-decks",type=int,default=100)
    args=p.parse_args()
    ids=[(args.tournament_id,"manual")] if args.tournament_id else tournament_ids()[:3]
    if not ids:raise RuntimeError("No recent Regional Championships found on Limitless")
    for tid,_ in ids:
        if import_event(tid,max(args.delay,1.0),max(1,args.max_decks)):return
    raise RuntimeError("No tournament produced a validated import. Existing JSON was preserved.")

if __name__=="__main__":main()
