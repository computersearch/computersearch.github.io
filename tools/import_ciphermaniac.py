#!/usr/bin/env python3
"""Import a verified top-64 snapshot from Ciphermaniac public R2 data.

Usage: python tools/import_ciphermaniac.py [--event '2026-10-24, Regional Championship Puebla']
Does not overwrite existing output unless upstream data is usable.
"""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE='https://r2.ciphermaniac.com/'
OUT=Path(__file__).resolve().parents[1]/'tournaments'

def fetch(path):
    req=Request(BASE+path,headers={'User-Agent':'DeckforgeTournamentArchive/0.1 (public data import; contact project owner)','Accept':'application/json'})
    with urlopen(req,timeout=30) as resp:
        return json.load(resp)

def records(payload):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        for key in ('decks','players','entries','results','items','data'):
            if isinstance(payload.get(key),list):return payload[key]
    return []

def val(row,*keys):
    for k in keys:
        if row.get(k) is not None:return row[k]
    return None

def cards_from(row):
    raw=val(row,'cards','cardlist','decklist','list')
    if isinstance(raw,dict):raw=val(raw,'cards','list','entries')
    if isinstance(raw,str):
        cards=[]
        for line in raw.splitlines():
            m=re.match(r'^\s*(\d+)\s+(.+?)\s+([A-Z0-9]{2,6})\s+(\d+[a-zA-Z]?)\s*$',line)
            if m:cards.append(dict(quantity=int(m[1]),name=m[2],set=m[3],number=m[4]))
        return cards if sum(x['quantity'] for x in cards)==60 else None
    if isinstance(raw,list):
        cards=[]
        for c in raw:
            if not isinstance(c,dict):return None
            qty=val(c,'quantity','qty','count','copies','amount')
            name=val(c,'name','cardName','card')
            if isinstance(name,dict):name=name.get('name')
            code=val(c,'set','setCode','set_code')
            number=val(c,'number','collectorNumber','collector_number')
            if not all([qty,name,code,number]):return None
            cards.append(dict(quantity=int(qty),name=str(name),set=str(code),number=str(number)))
        return cards if sum(x['quantity'] for x in cards)==60 else None
    return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--event');ap.add_argument('--latest',action='store_true');args=ap.parse_args()
    catalog=fetch('reports/tournaments.json')
    if not isinstance(catalog,list):raise ValueError('Unexpected tournament catalog')
    event=args.event or next((e for e in catalog if 'Regional Championship' in e),None)
    if event not in catalog:raise ValueError('Tournament not found in catalog: '+str(event))
    prefix='reports/'+quote(event,safe='')+'/'
    decks=records(fetch(prefix+'decks.json'))
    if not decks:raise RuntimeError('No deck records; refusing to publish empty event')
    try:players=records(fetch(prefix+'players.json'))
    except Exception:players=[]
    ranked={}
    for row in players+decks:
        if not isinstance(row,dict):continue
        rank=val(row,'placing','placement','place','rank','standing')
        if isinstance(rank,str):rank=re.sub(r'[^0-9]','',rank)
        try:rank=int(rank)
        except (TypeError,ValueError):continue
        if rank<1 or rank>64:continue
        name=val(row,'pilot','player','playerName','name')
        if isinstance(name,dict):name=val(name,'name','displayName')
        if not isinstance(name,str) or not name.strip():continue
        name=name.strip()
        previous=ranked.get(rank,{})
        if previous and previous['name']!=name:
            raise RuntimeError(f'Conflicting names at placement {rank}: {previous["name"]} vs {name}')
        cards=cards_from(row)
        ranked[rank]={'rank':rank,'name':name,'deck':val(row,'archetype','deckName','deckType') or previous.get('deck'),
                      'decklist':cards or previous.get('decklist'),'decklist_url':None}
    if len(ranked)<64:
        raise RuntimeError(f'Only {len(ranked)} of 64 placements matched; refusing incomplete import')
    if any(i not in ranked for i in range(1,65)):
        raise RuntimeError('Noncontiguous placements; refusing import')
    result={'id':'ciphermaniac-'+event[:10],'name':event.split(', ',1)[-1], 'date':event[:10],
            'source':BASE+prefix,'provider':'Ciphermaniac R2','standings':[ranked[i] for i in range(1,65)],
            'note':'Decklists only included when 60 cards with exact print IDs could be verified.'}
    OUT.mkdir(exist_ok=True)
    path=OUT/('ciphermaniac-'+event[:10]+'.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    manifest=OUT/'index.json'
    entries=json.loads(manifest.read_text()) if manifest.exists() else []
    entry={'id':result['id'],'name':result['name'],'date':result['date'],'file':path.name,'source':result['source'],'verified_decks':sum(bool(x['decklist']) for x in ranked.values())}
    entries=[x for x in entries if x.get('id')!=entry['id']]+[entry]
    entries.sort(key=lambda x:x.get('date',''),reverse=True)
    manifest.write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n')
    print(f'Wrote {path}: 64 placements, {entry["verified_decks"]} verified decklists')

if __name__=='__main__':main()
