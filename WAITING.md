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
| DMAX | Sənədli | 0 | no candidate URLs |
| Futbol | İdman | 1 | unreachable |
| Idman TV | Azərbaycan 🇦🇿; İdman | 0 | no candidate URLs |
| Olympic Channel | İdman | 3 | 403 forbidden |
| Space TV | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| Start TV | Azərbaycan 🇦🇿 | 0 | no candidate URLs |
| TGRT Belgesel | Sənədli | 0 | all known streams blocklisted |
| TRT 2 | Türkiyə – Ümumi | 2 | 403 forbidden, 404 not found |
| TRT Belgesel | Sənədli | 1 | 404 not found |

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
| Adventure Earth | Sənədli | `AdventureEarth.de` |
| Africa 24 English | Beynəlxalq Xəbər | `Africa24English.fr` |
| Al Arabiya English | Beynəlxalq Xəbər | `AlArabiyaEnglish.sa` |
| Al Jazeera | Beynəlxalq Xəbər | `AlJazeera.qa` |
| Arirang UN | Beynəlxalq Xəbər | `ArirangUN.kr` |
| AS TV | Xəbər – Türkiyə | `ASTV.tr` |
| Autentic History | Sənədli | `AutenticHistory.de` |
| BabyFirst | Uşaq | `BabyFirst.us` |
| Belarus-5 | İdman | `Belarus5.by` |
| Bondi Rescue | Sənədli | `BondiRescue.de` |
| CGTN russian | Beynəlxalq Xəbər | `CGTNRussian.cn` |
| China Travel | Sənədli | `ChinaTravel.cn` |
| CNA Originals | Sənədli | `CNAOriginals.sg` |
| Cricket Gold | İdman | `CricketGold.au` |
| DHA | Xəbər – Türkiyə | `DHA.tr` |
| Discovering China | Sənədli | `DiscoveringChina.cn` |
| DiviSport | İdman | `DiviSport.ua` |
| DocuBox | Sənədli | `DocuBox.nl` |
| Documentary+ | Sənədli | `DocumentaryPlus.us` |
| DraftKings Network | İdman | `DraftKingsNetwork.us` |
| Dynamo Kyiv TV | İdman | `DynamoKyivTV.ua` |
| Equalympic | İdman | `Equalympic.ua` |
| Fast&FunBox | İdman | `FastFunBox.nl` |
| FIFA+ Women | İdman | `FIFAPlusWomen.uk` |
| FightBox | İdman | `FightBox.nl` |
| Finans Turk TV | Xəbər – Türkiyə | `FinansTurkTV.tr` |
| FloHockey | İdman | `FloHockey.us` |
| FloRacing | İdman | `FloRacing.us` |
| France 24 | Beynəlxalq Xəbər | `France24.fr` |
| FUEL TV | İdman | `FUELTV.pt` |
| Glory Kickboxing | İdman | `GloryKickboxing.us` |
| GolTV Latin America | İdman | `GolTVLatinAmerica.us` |
| Guneydogu TV | Xəbər – Türkiyə | `GuneydoguTV.tr` |
| Haber61 TV | Xəbər – Türkiyə | `Haber61TV.tr` |
| History Asia | Sənədli | `HistoryAsia.us` |
| Ink Master | Sənədli | `InkMaster.us` |
| Jail | Sənədli | `Jail.uk` |
| Life TV | Xəbər – Türkiyə | `LifeTV.tr` |
| Love The Planet | Sənədli | `LoveThePlanet.es` |
| Number 1 Ask | Musiqi | `Number1Ask.tr` |
| Pluto TV Snooker 900 | İdman | `PlutoTVSnooker900.de` |
| Pluto TV Snooker 900 | İdman | `PlutoTVSnooker900.se` |
| Pluto TV Sport | İdman | `PlutoTVSport.se` |
| PowerTurk Akustik | Musiqi | `PowerTurkAkustik.tr` |
| PowerTurk Slow | Musiqi | `PowerTurkSlow.tr` |
| PowerTurk Taptaze | Musiqi | `PowerTurkTaptaze.tr` |
| RACER International | İdman | `RACERInternational.pl` |
| Racer Select | İdman | `RacerSelect.us` |
| RT Documentary | Sənədli | `RTDocumentary.ru` |
| Sport 1 Baltic | İdman | `Sport1Baltic.ua` |
| Sportdigital FUSSBALL | İdman | `SportdigitalFUSSBALL.de` |
| Strongman | İdman | `Strongman.us` |
| Terra Mater WILD | Sənədli | `TerraMaterWILD.de` |
| Trace Sport Stars | İdman | `TraceSportStars.fr` |
| TRT Arabi | Xəbər – Türkiyə | `TRTArabi.tr` |
| TurkHaber TV | Xəbər – Türkiyə | `TurkHaberTV.tr` |
| WaterBear | Sənədli | `WaterBear.ch` |
| Willow Sports | İdman | `WillowSports.us` |
