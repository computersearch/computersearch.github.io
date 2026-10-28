# Computer Search — modular version

Open `index.html` in Firefox, or publish this entire folder to GitHub Pages. Keep the folder structure intact.

## Add a deck

1. Copy an existing file in `decks/` to `decks/my-new-deck.js`.
2. Change `slug`, `name`, `rank`, `points`, `share`, `featuredCard`, `description`, and `groups`.
3. Keep the list at exactly **60 cards** and make each group count match its cards. Invalid decks fail validation with an error in the browser console.
4. Add `<script src="decks/my-new-deck.js"></script>` to `index.html` **after** `js/deck-registry.js` and **before** `js/app.js`.
5. The deck automatically appears in the rankings and gets a detail page at `#/deck/my-new-deck`. Top-three decks appear in the homepage featured area if `rank` is 1, 2, or 3.

Each deck is an instance of the `Deck` class, managed by `DeckRegistry` in `js/deck-registry.js`. The shared interface, TCGdex resolver, card styling, energy images, and Cardmarket integration remain in `js/app.js` and `index.html`. The deck files contain **data only**, not duplicated UI logic.

Note: learned TCGdex mappings remain in the browser's local storage; the built-in mappings remain in the shared app code. This is a static-site architecture with no server or database required.


## v25
Deck Builder removed. This version returns to the modular ranked deck browsing experience with four deck files. No personal deck editing or browser deck library is included.

## Tournament results
The Tournaments tab loads `tournaments/581.json`, seeded with the verified top 64 Louisville 2026 Masters placements from Limitless. The published decklist fields remain empty until successfully retrieved. Run `python -m http.server 8000` in this directory, then open http://localhost:8000; file:// blocks JSON fetch in Firefox.

To update from Limitless: `pip install requests beautifulsoup4` and `python tools/import_limitless.py 581`. The importer rate-limits requests, verifies player placements and 60-card lists when possible, and writes a JSON file. Respect Limitless terms and access rules.

## Ciphermaniac public data integration (v27)

Run `python tools/import_ciphermaniac.py` to discover the latest Regional from Ciphermaniac's public `reports/tournaments.json`, retrieve `decks.json` and `players.json`, and export a top-64 tournament JSON file. The importer **fails closed** if it cannot verify all 64 player placements; it includes a decklist only when the original data provides 60 cards with exact set and collector IDs. Run the importer on a server or GitHub Actions, not in the browser: Ciphermaniac R2 has restricted CORS. Attribution and source links are preserved. The original v26 Louisville snapshot remains included; no new live import is claimed until the script successfully runs against the remote data.

## v28: no local Python needed
Upload the **contents** of this folder to the root of a GitHub repository. In GitHub, enable Actions and enable Pages with **Deploy from a branch** (`main`, `/ (root)`). Under Actions select **Update tournament data** > **Run workflow** for the first import; the workflow also runs daily at 06:25 UTC. It runs Python on GitHub's servers and commits verified JSON into `tournaments/`. Your computer only needs a web browser.

The importer intentionally refuses to overwrite snapshots unless it can validate 64 placements. If upstream formats change, the GitHub Actions run will fail and existing published data remains intact. The website shows a bundled Louisville fallback until a successful import. API access, source permissions and the complete browser experience have not been tested end-to-end.

## v30: Player decklist viewer
Tournament results now link to `#/tournament/deck/{rank}` for any player with a verified
60-card `decklist` in the imported JSON. Each card is rendered with its exact set and
collector number, with artwork looked up through the existing TCGdex integration.
The viewer also provides a Pokémon TCG Live text export. Players without published
complete lists remain unlinked. This feature becomes populated after a successful
GitHub Actions import; the bundled Louisville snapshot contains no complete lists.
