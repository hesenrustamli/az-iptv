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
| ABC News Live | Beynəlxalq Xəbər | `ABCNewsLive.us` |
| ACC Digital Network | İdman | `ACCDigitalNetwork.us` |
| Adventure Earth | Sənədli | `AdventureEarth.de` |
| Africa 24 English | Beynəlxalq Xəbər | `Africa24English.fr` |
| Al Arabiya English | Beynəlxalq Xəbər | `AlArabiyaEnglish.sa` |
| Al Jazeera | Beynəlxalq Xəbər | `AlJazeera.qa` |
| Arirang UN | Beynəlxalq Xəbər | `ArirangUN.kr` |
| AS TV | Xəbər – Türkiyə | `ASTV.tr` |
| Autentic History | Sənədli | `AutenticHistory.de` |
| BabyFirst | Uşaq | `BabyFirst.us` |
| BBC Earth | Sənədli | `BBCEarth.uk` |
| BBC News | Beynəlxalq Xəbər | `BBCNews.uk` |
| Belarus-5 | İdman | `Belarus5.by` |
| Bondi Rescue | Sənədli | `BondiRescue.de` |
| CGTN russian | Beynəlxalq Xəbər | `CGTNRussian.cn` |
| China Travel | Sənədli | `ChinaTravel.cn` |
| CNA Originals | Sənədli | `CNAOriginals.sg` |
| Cricket Gold | İdman | `CricketGold.au` |
| Curiosity NOW | Sənədli | `CuriosityNOW.de` |
| DHA | Xəbər – Türkiyə | `DHA.tr` |
| Discovering China | Sənədli | `DiscoveringChina.cn` |
| DiviSport | İdman | `DiviSport.ua` |
| DocuBox | Sənədli | `DocuBox.nl` |
| Documentary+ | Sənədli | `DocumentaryPlus.us` |
| DraftKings Network | İdman | `DraftKingsNetwork.us` |
| Dynamo Kyiv TV | İdman | `DynamoKyivTV.ua` |
| Equalympic | İdman | `Equalympic.ua` |
| F1 Channel | İdman | `F1Channel.ie` |
| Fast&FunBox | İdman | `FastFunBox.nl` |
| FIFA+ Women | İdman | `FIFAPlusWomen.uk` |
| Fight Network | İdman | `FightNetwork.ca` |
| FightBox | İdman | `FightBox.nl` |
| Finans Turk TV | Xəbər – Türkiyə | `FinansTurkTV.tr` |
| FITE 24/7 | İdman | `FITE247.us` |
| FloHockey | İdman | `FloHockey.us` |
| FloRacing | İdman | `FloRacing.us` |
| Football | İdman | `Football.ru` |
| France 24 | Beynəlxalq Xəbər | `France24.fr` |
| FUEL TV | İdman | `FUELTV.pt` |
| Glory Kickboxing | İdman | `GloryKickboxing.us` |
| GolTV Latin America | İdman | `GolTVLatinAmerica.us` |
| Guneydogu TV | Xəbər – Türkiyə | `GuneydoguTV.tr` |
| Haber61 TV | Xəbər – Türkiyə | `Haber61TV.tr` |
| History Asia | Sənədli | `HistoryAsia.us` |
| i24NEWS English World | Beynəlxalq Xəbər | `i24NEWSEnglishWorld.il` |
| Ink Master | Sənədli | `InkMaster.us` |
| InTrouble | İdman | `InTrouble.nl` |
| Jail | Sənədli | `Jail.uk` |
| Kozoom TV | İdman | `KozoomTV.fr` |
| KTV Sport | İdman | `KTVSport.kw` |
| Life TV | Xəbər – Türkiyə | `LifeTV.tr` |
| Love The Planet | Sənədli | `LoveThePlanet.es` |
| Maincast Cybersport | İdman | `MaincastCybersport.ua` |
| Maincast Sport | İdman | `MaincastSport.ua` |
| MLB | İdman | `MLB.us` |
| MMA-TV.com | İdman | `MMATVcom.ru` |
| NBA TV | İdman | `NBATV.us` |
| NBC Sports NOW | İdman | `NBCSportsNOW.us` |
| News of the World | Beynəlxalq Xəbər | `NewsoftheWorld.us` |
| NewsWorld | Beynəlxalq Xəbər | `NewsWorld.hk` |
| NFL Channel | İdman | `NFLChannel.us` |
| NHL Network | İdman | `NHLNetwork.us` |
| NowMedia Television | Beynəlxalq Xəbər | `NowMediaTelevision.us` |
| Number 1 Ask | Musiqi | `Number1Ask.tr` |
| Pluto TV Alien Invasion | Sənədli | `PlutoTVAlienInvasion.de` |
| Pluto TV American True Crime | Sənədli | `PlutoTVAmericanTrueCrime.de` |
| Pluto TV Animals | Sənədli | `PlutoTVAnimals.de` |
| Pluto TV Britain at War | Sənədli | `PlutoTVBritainatWar.de` |
| Pluto TV Conspiracy | Sənədli | `PlutoTVConspiracy.de` |
| Pluto TV Dokumentar | Sənədli | `PlutoTVDokumentar.se` |
| Pluto TV Food | Sənədli | `PlutoTVFood.de` |
| Pluto TV History | Sənədli | `PlutoTVHistory.de` |
| Pluto TV Snooker 900 | İdman | `PlutoTVSnooker900.de` |
| Pluto TV Snooker 900 | İdman | `PlutoTVSnooker900.se` |
| PowerTurk Akustik | Musiqi | `PowerTurkAkustik.tr` |
| PowerTurk Slow | Musiqi | `PowerTurkSlow.tr` |
| PowerTurk Taptaze | Musiqi | `PowerTurkTaptaze.tr` |
| RACER International | İdman | `RACERInternational.pl` |
| Racer Network | İdman | `RacerNetwork.us` |
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
