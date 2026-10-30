#!/usr/bin/env python3
"""Detect Limitless tournament type by title; fail rather than guess."""
import argparse
import re
import requests
from bs4 import BeautifulSoup

def detect(tid):
    if not re.fullmatch(r"\d+",str(tid)):
        raise ValueError("Tournament ID must be numeric")
    response=requests.get(f"https://limitlesstcg.com/tournaments/{tid}",timeout=45,
                          headers={"User-Agent":"ComputerSearch/1.0"})
    response.raise_for_status()
    soup=BeautifulSoup(response.text,"html.parser")
    # Limitless tournament pages do not necessarily have an h1. Their
    # browser title and tournament heading are reliable alternatives.
    candidates=[]
    for node in [soup.select_one("h1"),soup.select_one("title"),
                 soup.select_one('meta[property="og:title"]')]:
        if node:
            value=node.get("content", "") if node.name=="meta" else node.get_text(" ",strip=True)
            if value: candidates.append(value)
    # As a last resort inspect the first portion of the page's visible text.
    candidates.append(soup.get_text(" ",strip=True)[:1200])
    for title in candidates:
        if re.search(r"\b(?:World Championships?\s+20\d{2}|20\d{2}\s+World Championships?)\b",title,re.I):
            return "worlds"
        if re.search(r"\b(?:International Championships?|EUIC|NAIC|LAIC|OCIC)\b",title,re.I):
            return "international"
        if re.search(r"\bRegional(?: Championships?)?\b",title,re.I):
            return "regional"
    raise ValueError(f"Unknown event type for {tid}; inspected titles: {candidates[:3]!r}")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--tournament-id",required=True)
    print(detect(parser.parse_args().tournament_id))
