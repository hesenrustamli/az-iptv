# Waiting list

Channels kept in the playlist config that have no working stream
right now. Every one is re-probed on each run and rejoins
`playlist.m3u` automatically as soon as a candidate passes.

| Channel | Group | Candidates tried | Result |
| --- | --- | --- | --- |
| AnewZ TV | Azərbaycan 🇦🇿 | 1 | 403 forbidden |
| ARB | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| ARB 24 | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| ARB Gunes | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| BBC One | İdman | 50 | 403 forbidden |
| Beyaz TV | Türkiyə – Ümumi | 0 | all known streams blocklisted |
| Canal 11 | İdman | 0 | no candidate URLs |
| Che! | · russia | 1 | unreachable |
| CNN International | Beynəlxalq Xəbər | 0 | no candidate URLs |
| CNN Turk | Xəbər – Türkiyə | 1 | 403 forbidden |
| DW Documentary | Sənədli | 0 | no candidate URLs |
| Earth Touch TV | Sənədli | 0 | no candidate URLs |
| Football | İdman | 1 | unreachable |
| Idman TV | Azərbaycan 🇦🇿; İdman | 0 | no candidate URLs |
| ITV1 | İdman | 0 | no candidate URLs |
| L'Equipe | İdman | 0 | no candidate URLs |
| MTRK Sport | İdman | 0 | no candidate URLs |
| ORF 1 | İdman | 1 | server error |
| Plex Documentary | Sənədli | 0 | no candidate URLs |
| Pluto TV Sports | İdman | 0 | no candidate URLs |
| Rai Sport | İdman | 0 | no candidate URLs |
| RTE2 | İdman | 0 | no candidate URLs |
| RTP 2 | İdman | 1 | empty response |
| RTSH Sport | İdman | 1 | unreachable |
| ServusTV | İdman | 1 | 403 forbidden |
| SIC | İdman | 1 | 403 forbidden |
| Space TV | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| Sport1 | İdman | 0 | no candidate URLs |
| Sportdigital FUSSBALL | İdman | 0 | no candidate URLs |
| Start TV | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| TRT 2 | Türkiyə – Ümumi | 2 | 403 forbidden, 404 not found |
| TRT Spor | İdman | 1 | unreachable |
| TV 8.5 | Türkiyə – Ümumi | 0 | no candidate URLs |
| Wild Nature | Sənədli | 0 | no candidate URLs |
| ZDF | İdman | 1 | 403 forbidden |
| Zo'r TV | İdman | 0 | no candidate URLs |

## Substitutes

The bench for a locked group. One substitute enters for each
member with no working stream, in bench order, and steps back
when the member returns. Membership and the editorial order of
the group itself never change.

| Substitute | Group | Bench rank | Status |
| --- | --- | --- | --- |
| FloHockey | İdman | 1 | in play - covering a hidden member |
| FUEL TV | İdman | 2 | in play - covering a hidden member |
| Trace Sport Stars | İdman | 3 | in play - covering a hidden member |
| FIFA+ | İdman | 4 | in play - covering a hidden member |
| FIFA+ Women | İdman | 5 | in play - covering a hidden member |
| SKI TV | İdman | 6 | streamless - unreachable |
| Sport | İdman | 7 | streamless - 403 forbidden |
| Willow Sports | İdman | 8 | in play - covering a hidden member |
| Pluto TV Sport | İdman | 9 | in play - covering a hidden member |
| Golf Channel | İdman | 10 | streamless - 403 forbidden |
| F1 Channel | İdman | 11 | runner-alive, no Baku pass on record (failed here) |
| Fubo Sports Network | İdman | 12 | in play - covering a hidden member |
| NBC Sports NOW | İdman | 14 | in play - covering a hidden member |
| Golazo Network | İdman | 18 | in play - covering a hidden member |
| Pluto TV Competition | İdman | 19 | in play - covering a hidden member |
| InTrouble | İdman | 23 | in play - covering a hidden member |
| Kozoom TV | İdman | 24 | in play - covering a hidden member |
| KTV Sport | İdman | 25 | in play - covering a hidden member |
| Monster Jam | İdman | 26 | in play - covering a hidden member |
| Nautical Channel | İdman | 27 | in play - covering a hidden member |
| Oman Sports TV | İdman | 29 | in play - covering a hidden member |
| PFL MMA | İdman | 31 | in play - covering a hidden member |
| Sky Racing 1 | İdman | 36 | in play - covering a hidden member |
| Sky Racing 2 | İdman | 37 | in play - covering a hidden member |
| TGRT Belgesel | Sənədli | 1 | streamless - all known streams blocklisted |
| DMAX | Sənədli | 2 | streamless - no candidate URLs |
| BBC Earth | Sənədli | 3 | in play - covering a hidden member |
| Smithsonian Channel Selects | Sənədli | 4 | in play - covering a hidden member |
| Curiosity NOW | Sənədli | 5 | in play - covering a hidden member |
| Terra Mater WILD | Sənədli | 6 | in play - covering a hidden member |
| CNA Originals | Sənədli | 7 | ready - no seat needed this run |
| NHK World-Japan | Sənədli | 8 | ready - no seat needed this run |
| WildEarth | Sənədli | 9 | ready - no seat needed this run |
| RT Documentary | Sənədli | 10 | ready - no seat needed this run |
| WaterBear | Sənədli | 11 | ready - no seat needed this run |
| Love The Planet | Sənədli | 12 | ready - no seat needed this run |
| _+27 more_ | Sənədli | | _self-curated tail, not shown_ |
| _+20 more_ | İdman | | _self-curated tail, not shown_ |

## Alternates found

Working streams found on a broadcaster's own site for channels
that are already live. Listed only; never swapped in.

_None._

## New channels

Added automatically by AUTO_RULES from the iptv-org database,
not hand-picked. To drop one for good, add its id to EXCLUDE
in `generate_playlist.py`.

_None._
