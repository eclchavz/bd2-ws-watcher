# 07: Official EN site and English-release alert

**What to build:** An `official-en` adapter for en.ws-tcg.com that behaves the same as ticket 06. On top of that, when an English Brown Dust 2 release is announced, an `english_release` event fires and sends its own clearly labelled alert.

**Blocked by:** 06

**Status:** done (on branch `ticket/06-07-official-sites`), except the live page-structure check: the build sandbox can't reach ws-tcg.com, so fixtures are hand-made around the known URL shape `/products/brd_bp/`.

- [ ] The page structure (or RSS feed) is confirmed live with `check-now official-en`, and a fixture is captured
- [x] A Seam 1 test: an English Brown Dust 2 announcement sends one `english_release` alert, labelled as English
- [x] A Seam 1 test: other new English sets are queued for the digest
- [x] The dashboard shows the JP and EN versions of a set side by side, or labelled by language
