# 0002: Alert on state transitions, with baseline and cooldown

**Status:** accepted

Alerts fire only when something changes compared with stored state. A listing appearing, `sold_out` changing to `in_stock` or `preorder`, a new set, or a source breaking all count. A listing that is still in stock never fires again.

- The first successful check of each source is a **baseline**: it is recorded silently.
- Stock events for the same listing are limited to one alert per 6 hours.
- Brown Dust 2 events alert immediately at any hour, with no quiet hours.
- Other Weiss Schwarz `new_set` events are batched into the 9:00 AM email digest.
- Price changes are recorded and charted but never alert.

## Why

Restocks of the Brown Dust 2 booster sell out within minutes, so speed matters more than quiet. But stores flip stock flags often, and a flood of repeat alerts would get the channel muted. That is worse than missing one alert.
