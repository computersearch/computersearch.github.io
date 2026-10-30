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
    h=soup.select_one("h1")
    title=h.get_text(" ",strip=True) if h else ""
    if re.search(r"(?:World Championships?\s+20\d{2}|20\d{2}\s+World Championships?)",title,re.I):return "worlds"
    if re.search(r"Regional(?: Championships?)?",title,re.I):return "regional"
    raise ValueError(f"Unknown event type: {title!r}; refusing to guess")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--tournament-id",required=True)
    print(detect(parser.parse_args().tournament_id))
