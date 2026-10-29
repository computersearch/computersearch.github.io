#!/usr/bin/env python3
"""Import published Masters Division Regional decklists from main LimitlessTCG.
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
    """Find deck links in anchors, data attributes and embedded scripts.

    Limitless's large decklists pages may encode paths in scripts or relative URLs.
    """
    html=str(soup)
    # HTML-escaped and JSON-escaped slashes are common in inline payloads.
    html=html.replace(r"\/", "/").replace("&amp;", "&")
    ids=list(dict.fromkeys(re.findall(r"(?:https?://(?:www\.)?limitlesstcg\.com)?/?decks/list/(\d+)(?=[^0-9]|$)",html)))
    if not ids:
        # Print safe structural diagnostics, not the multi-megabyte response.
        paths=re.findall(r'(?:href|data-href|data-url)=["\']([^"\']+)',html,re.I)
        print("DEBUG: decklist page bytes:",len(html),"links:",len(paths),"sample:",paths[:12],flush=True)
        print("DEBUG: /decks/list/ occurrences:",html.count('/decks/list/'),flush=True)
    return [f"{BASE}/decks/list/{deck_id}" for deck_id in ids]

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

def import_event(tid,delay,max_decks):
    print(f"Checking Limitless tournament {tid}",flush=True)
    soup=get(f"/tournaments/{tid}")
    heading=soup.find("h1")
    name=heading.get_text(" ",strip=True) if heading else f"Regional {tid}"
    if "Regional" not in name:raise ValueError("Event is not a Regional Championship: "+name)
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
    print(f"Found {len(links)} decklist links; checking up to {max_decks}",flush=True)
    verified=0
    for link in links[:max_decks]:
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
    if verified==0:
        print("NO UPDATE: no verified 60-card lists matched player standings; preserving existing data")
        return False
    # The original tournament page has a visible date, but do not invent it.
    match=re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d\d)",event_text)
    date=datetime.strptime(" ".join(match.groups()),"%d %B %Y").date().isoformat() if match else ""
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
    p.add_argument("--tournament-id",help="Main Limitless numeric tournament ID (e.g. 583)")
    p.add_argument("--delay",type=float,default=1.2)
    p.add_argument("--max-decks",type=int,default=100)
    args=p.parse_args()
    ids=[(args.tournament_id,"manual")] if args.tournament_id else tournament_ids()[:3]
    if not ids:raise RuntimeError("No recent Regional Championships found on Limitless")
    for tid,_ in ids:
        if import_event(tid,max(args.delay,1.0),max(1,args.max_decks)):return
    raise RuntimeError("No tournament produced a validated import. Existing JSON was preserved.")

if __name__=="__main__":main()
