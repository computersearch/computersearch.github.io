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
    if is_worlds and verified==0:
        print("DIAGNOSTIC: Worlds HTML structure was not recognized. Please share the Worlds heading/card-anchor counts above.",flush=True)
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
