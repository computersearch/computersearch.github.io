#!/usr/bin/env python3
"""Import published Limitless tournament placements and decklists (Masters).
Usage: pip install requests beautifulsoup4; python tools/import_limitless.py 581
"""
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://limitlesstcg.com'
DEST=Path(__file__).resolve().parents[1]/'tournaments'
S=requests.Session()
S.headers['User-Agent']='DeckforgeTournamentImporter/0.1 (public archive; respectful rate limit)'
def get(path):
    url=urljoin(BASE,path)
    if urlparse(url).netloc!='limitlesstcg.com': raise ValueError('Non-Limitless URL')
    time.sleep(1.5)
    r=S.get(url,timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text,'html.parser')
def parse_results(soup):
    rows=[]
    for tr in soup.select('tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)<2: continue
        rank=cells[0].get_text(' ',strip=True)
        if not re.fullmatch(r'\d+',rank):continue
        rank=int(rank)
        if rank>64:continue
        name=cells[1].get_text(' ',strip=True)
        if not name:continue
        link=None
        for a in tr.select('a[href]'):
            href=a.get('href','')
            if '/decklist' in href and href != '/decklists':
                link=urljoin(BASE,href)
                break
        rows.append(dict(rank=rank,name=name,deck=None,decklist=None,decklist_url=link))
    return sorted({x['rank']:x for x in rows}.values(),key=lambda x:x['rank'])
def parse_deck(soup):
    # Published Limitless lists usually include a plain text decklist / copy-list block.
    # Do not fabricate set codes from card display names.
    for node in soup.select('textarea, pre, [data-decklist]'):
        raw=node.get('data-decklist') or node.get_text('\n',strip=True)
        cards=[]
        for line in raw.splitlines():
            m=re.fullmatch(r'(\d+)\s+(.+?)\s+([A-Z0-9]{2,6})\s+(\d+[A-Za-z]?)',line.strip())
            if m:cards.append({'quantity':int(m[1]),'name':m[2],'set':m[3],'number':m[4]})
        if sum(c['quantity'] for c in cards)==60:return cards
    return None
def main(event):
    if not re.fullmatch(r'\d+',event):raise ValueError('numeric tournament ID required')
    soup=get('/tournaments/'+event)
    standings=parse_results(soup)
    if len(standings)!=64:raise RuntimeError(f'Expected 64 standings; found {len(standings)}. No output written.')
    oldfile=DEST/(event+'.json')
    old=json.loads(oldfile.read_text()) if oldfile.exists() else {}
    old_by_rank={x['rank']:x for x in old.get('standings',[])}
    count=0
    for p in standings:
        previous=old_by_rank.get(p['rank'],{})
        if previous.get('name')==p['name'] and previous.get('decklist'):
            p.update({k:previous.get(k) for k in ('deck','decklist','decklist_url')})
        if p['decklist_url']:
            try:
                cards=parse_deck(get(p['decklist_url']))
                if cards:p['decklist']=cards;count+=1
            except requests.RequestException as e:print('Deck fetch failed:',e,file=sys.stderr)
    output={**old,'id':event,'source':BASE+'/tournaments/'+event,'standings':standings}
    DEST.mkdir(exist_ok=True)
    oldfile.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(f'Imported {len(standings)} placements, {count} new verified 60-card lists. Missing lists remain unavailable.')
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else '581')
