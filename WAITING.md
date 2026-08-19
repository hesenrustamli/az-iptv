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
| Beyaz TV | Türkiyə – Ümumi | 0 | all known streams blocklisted |
| CBS Sports Golazo Network | İdman | 1 | server error |
| Che! | · russia | 1 | unreachable |
| CNN International | Beynəlxalq Xəbər | 0 | no candidate URLs |
| CNN Turk | Xəbər – Türkiyə | 1 | 403 forbidden |
| DW Documentary | Sənədli | 0 | no candidate URLs |
| Futbol | İdman | 1 | unreachable |
| Idman TV | Azərbaycan 🇦🇿; İdman | 0 | no candidate URLs |
| Olympic Channel | İdman | 3 | 403 forbidden |
| Plex Documentary | Sənədli | 0 | no candidate URLs |
| Space TV | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| Start TV | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| TRT 2 | Türkiyə – Ümumi | 2 | 403 forbidden, 404 not found |
| TV 8.5 | Türkiyə – Ümumi | 0 | no candidate URLs |
| Wild Nature | Sənədli | 0 | no candidate URLs |

## Substitutes

The bench for a locked group. One substitute enters for each
member with no working stream, in bench order, and steps back
when the member returns. Membership and the editorial order of
the group itself never change.

| Substitute | Group | Bench rank | Status |
| --- | --- | --- | --- |
| TGRT Belgesel | Sənədli | 1 | streamless - all known streams blocklisted |
| DMAX | Sənədli | 2 | streamless - no candidate URLs |
| BBC Earth | Sənədli | 3 | in play - covering a hidden member |
| Smithsonian Channel Selects | Sənədli | 4 | in play - covering a hidden member |
| Curiosity NOW | Sənədli | 5 | in play - covering a hidden member |
| Terra Mater WILD | Sənədli | 6 | ready - no seat needed this run |
| CNA Originals | Sənədli | 7 | ready - no seat needed this run |
| NHK World-Japan | Sənədli | 8 | ready - no seat needed this run |
| WildEarth | Sənədli | 9 | ready - no seat needed this run |
| RT Documentary | Sənədli | 10 | ready - no seat needed this run |
| WaterBear | Sənədli | 11 | ready - no seat needed this run |
| Love The Planet | Sənədli | 12 | ready - no seat needed this run |
| Autentic History | Sənədli | 13 | ready - no seat needed this run |
| China Travel | Sənədli | 14 | ready - no seat needed this run |
| Pluto TV Science | Sənədli | 15 | ready - no seat needed this run |
| Pluto TV History | Sənədli | 16 | ready - no seat needed this run |

## Alternates found

Working streams found on a broadcaster's own site for channels
that are already live. Listed only; never swapped in.

_None._

## New channels

Added automatically by AUTO_RULES from the iptv-org database,
not hand-picked. To drop one for good, add its id to EXCLUDE
in `generate_playlist.py`.

| Channel | Group | Channel id |
| --- | --- | --- |
| ACC Digital Network | İdman | `ACCDigitalNetwork.us` |
| Belarus-5 | İdman | `Belarus5.by` |
| Cricket Gold | İdman | `CricketGold.au` |
| DiviSport | İdman | `DiviSport.ua` |
| DraftKings Network | İdman | `DraftKingsNetwork.us` |
| Dynamo Kyiv TV | İdman | `DynamoKyivTV.ua` |
| Equalympic | İdman | `Equalympic.ua` |
| F1 Channel | İdman | `F1Channel.ie` |
| Fast&FunBox | İdman | `FastFunBox.nl` |
| FIFA+ Women | İdman | `FIFAPlusWomen.uk` |
| Fight Network | İdman | `FightNetwork.ca` |
| FightBox | İdman | `FightBox.nl` |
| FITE 24/7 | İdman | `FITE247.us` |
| FloHockey | İdman | `FloHockey.us` |
| FloRacing | İdman | `FloRacing.us` |
| Football | İdman | `Football.ru` |
| FUEL TV | İdman | `FUELTV.pt` |
| Glory Kickboxing | İdman | `GloryKickboxing.us` |
| GolTV Latin America | İdman | `GolTVLatinAmerica.us` |
| InTrouble | İdman | `InTrouble.nl` |
| Kozoom TV | İdman | `KozoomTV.fr` |
| KTV Sport | İdman | `KTVSport.kw` |
| Maincast Cybersport | İdman | `MaincastCybersport.ua` |
| Maincast Sport | İdman | `MaincastSport.ua` |
| MLB | İdman | `MLB.us` |
| MMA-TV.com | İdman | `MMATVcom.ru` |
| NBA TV | İdman | `NBATV.us` |
| NBC Sports NOW | İdman | `NBCSportsNOW.us` |
| NFL Channel | İdman | `NFLChannel.us` |
| NHL Network | İdman | `NHLNetwork.us` |
| Pluto TV Snooker 900 | İdman | `PlutoTVSnooker900.de` |
| Pluto TV Snooker 900 | İdman | `PlutoTVSnooker900.se` |
| RACER International | İdman | `RACERInternational.pl` |
| Racer Network | İdman | `RacerNetwork.us` |
| Racer Select | İdman | `RacerSelect.us` |
| Sport 1 Baltic | İdman | `Sport1Baltic.ua` |
| Sportdigital FUSSBALL | İdman | `SportdigitalFUSSBALL.de` |
| Strongman | İdman | `Strongman.us` |
| Trace Sport Stars | İdman | `TraceSportStars.fr` |
| Willow Sports | İdman | `WillowSports.us` |
