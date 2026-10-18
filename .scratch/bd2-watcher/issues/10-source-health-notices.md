# 10: Broken-check notices

**What to build:** A check that raises an error, times out, or returns zero products where there used to be some counts as a failure. After 3 failures in a row, the source is marked broken and one `source_broken` notice goes to Discord. The next successful check marks it OK and sends `source_recovered`. While a source is broken, its failed checks don't create stock events.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] A Seam 1 test: 2 failures send nothing, the 3rd sends exactly one `source_broken`, and a 4th sends nothing
- [ ] A Seam 1 test: a success after being broken sends one `source_recovered`
- [x] A Seam 1 test: an empty result from a source that previously had listings counts as a failure, and its listings are not marked sold out (done early in ticket 02)
- [ ] Errors back off exponentially for that host
- [ ] The dashboard's sources section shows the failure count and the last error message
