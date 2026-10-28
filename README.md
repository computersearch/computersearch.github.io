# Computer Search

**Computer Search** is an independent, fan-made website for exploring competitive Pokémon Trading Card Game decks, tournament results, and the cards that make each strategy work.

The name is inspired by the idea of searching through a huge collection of Pokémon TCG cards to find exactly what you need. Computer Search brings that same spirit to competitive deck research: discover a deck, examine its cards, and learn from the players who use it.

## Why Computer Search was created

Competitive Pokémon TCG information is spread across tournament standings, published decklists, card databases, and individual player results. Finding a deck is often easy; understanding exactly what a player used, which card printings belong in the list, and how that deck performed can take more effort.

Computer Search was created to make that process simpler and more enjoyable. The goal is to provide one approachable place where players can explore successful archetypes, browse tournament placements, open published player decklists, view card artwork, and copy complete lists into Pokémon TCG Live.

Whether you're preparing for a tournament, learning a new deck, or simply curious about the competitive scene, Computer Search is meant to help you spend less time hunting for information and more time enjoying the game.

## What you can do

- **Discover decks:** Browse a curated selection of competitive archetypes and explore their cards.
- **Explore tournament results:** See player placements and deck archetypes from published events.
- **View player decklists:** Open a player's exact published 60-card list when complete card data is available.
- **See the cards:** Browse card images alongside quantities, set codes, and collector numbers.
- **Export a deck:** Copy supported lists in a format intended for Pokémon TCG Live.

Some tournament decklists are not publicly available. Computer Search marks those lists as unavailable rather than guessing their contents. Tournament imports depend on the availability and format of upstream data.

## A special thank you

Computer Search would not be possible without the work of people who make Pokémon TCG information accessible to the community.

**Thank you, [Limitless TCG](https://limitlesstcg.com/),** for collecting and publishing competitive tournament results and decklists. Your work is an invaluable resource for players who want to follow the game and learn from tournament performances.

**Thank you, [TCGdex](https://tcgdex.dev/),** for providing an accessible Pokémon TCG card database and API. Your work helps bring decklists to life with card information and artwork.

**Thank you, [Ciphermaniac](https://ciphermaniac.com/),** for building tools and datasets that make competitive tournament and deck information easier to explore. Your public data resources help make the tournament research experience possible.

These acknowledgements are expressions of appreciation, not claims of sponsorship, partnership, or endorsement.

## About this project

Computer Search is an independent community project, not affiliated with, sponsored by, or endorsed by The Pokémon Company, Nintendo, Creatures Inc., Game Freak, Limitless TCG, TCGdex, or Ciphermaniac. Pokémon and related names, characters, and imagery belong to their respective owners.

Data and artwork are credited to their respective sources. If you notice an inaccurate decklist, missing attribution, or another issue, please open an issue in this repository.

## Publishing the website

Computer Search is a static website designed for **GitHub Pages**. Upload the contents of this project to the root of your GitHub repository, then enable GitHub Pages under **Settings → Pages** using the `main` branch and `/ (root)` folder.

The included GitHub Actions workflow is intended to update tournament JSON data automatically. The live Ciphermaniac import has not yet been verified end-to-end; published decklists appear only when the imported data contains a validated complete list. You do not need to install Python on your own computer.
