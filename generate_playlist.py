#!/usr/bin/env python3
"""Auto-generates a curated Azerbaijani IPTV playlist from the iptv-org public API.
Rules: only AZ/TR/RU/EN channels, no dead github-hosted streams, prefer official CDNs."""
import json, urllib.request

MIRRORS = ["https://iptv-org.github.io/api/{}",
           "https://raw.githubusercontent.com/iptv-org/api/gh-pages/{}"]
def get(name):
    last = None
    for m in MIRRORS:
        try:
            with urllib.request.urlopen(m.format(name), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            last = e
    raise last

channels = {c["id"]: c for c in get("channels.json")}
streams_raw = get("streams.json")
logos = {}
for l in get("logos.json"):
    if l.get("channel") and l["channel"] not in logos:
        logos[l["channel"]] = l["url"]

BAD_HOSTS = ["raw.githubusercontent.com"]  # dead restream repo
by = {}
for s in streams_raw:
    cid = s.get("channel")
    if cid and not any(b in s["url"] for b in BAD_HOSTS):
        by.setdefault(cid, []).append(s)

# Verified working TRT 1 stream (TRT's own CDN, used by tabii)
by["TRT1.tr"] = [{"url": "https://trt.daioncdn.net/trt-1/master.m3u8?app=web",
                  "quality": "1080p", "user_agent": None, "referrer": None}] + by.get("TRT1.tr", [])

OFFICIAL = ["trt.com.tr", "daioncdn", "baku.tv", "itv.az", "atv.az",
            "xezerxeber.az", "yodacdn", "mncdn"]
def qscore(s):
    q = s.get("quality") or ""
    try: return int(q.replace("p", "").replace("i", ""))
    except ValueError: return 0
def rank(s):
    return (any(d in s["url"] for d in OFFICIAL), qscore(s))

PICKS = {
"Azərbaycan 🇦🇿": ["AzTV.az","IctimaiTV.az","XezerTV.az","DunyaTV.az","CBCSport.az","BakuTV.az","APATv.az","AnewZTV.az","MedeniyyetTV.az","KanalS.az","Kanal35.az","KapazTV.az","NaxcivanTV.az","ELTV.az","AyazTV.az","VilayetTV.az","AlvinChannelTV.az","KNMusicTV.az","GunAzTV.us","AzStarTV.ca","SpaceTV.az","ARB24.az","ARBGunes.az","StartTV.az"],
"Türkiyə – Ümumi": ["TRT1.tr","ATV.tr","KanalD.tr","StarTV.tr","NOWTV.tr","TV8.tr","Kanal7.tr","BeyazTV.tr","TRTAvaz.tr","TRTTurk.tr","EuroD.tr","KanalDDrama.tr","DreamTurk.tr","TRT2.tr"],
"Xəbər – Türkiyə": ["TRTHaber.tr","HaberGlobal.tr","AHaber.tr","HaberturkTV.tr","TGRTHaber.tr","NTV.tr","24TV.tr","360.tr","TVNET.tr","HalkTV.tr","Tele1.tr","UlkeTV.tr","BloombergHT.tr","CNBCe.tr"],
"İdman": ["ASpor.tr","TRT3.tr","TRTSporYildiz.tr","HTSporTV.tr","FBTV.tr","TJKTV.tr","RedBullTV.at"],
"Uşaq": ["TRTCocuk.tr","MinikaCocuk.tr","MinikaGo.tr","TRTDiyanetCocuk.tr","Carousel.ru"],
"Musiqi": ["TRTMuzik.tr","KralPopTV.tr","PowerTurkTV.tr","PowerTV.tr","PowerDance.tr","PowerLove.tr","Number1TV.tr","Number1Dance.tr","Number1Damar.tr","MuzTV.ru","RUTV.ru","EuropaPlusTV.ru"],
"Sənədli və Həyat tərzi": ["TRTBelgesel.tr","TGRTBelgesel.tr","CGTNDocumentary.cn","Tastemade.us","TastemadeTravel.us","FashionTVEurope.fr"],
"rusiya": ["ChannelOne.ru","Russia1.ru","NTV.ru","STS.ru","RENTV.ru"],
"Ukrayna (rus dilində)": ["FREEDOM.ua"],
"Beynəlxalq Xəbər": ["TRTWorld.tr","EuronewsEnglish.fr","EuronewsRussian.fr","DW.de","CGTN.cn","BloombergTV.us","SkyNews.ie","ABCNews.au","NHKWorldJapan.jp","ArirangTV.kr","CNA.sg","TVPWorld.pl"],
}
# Note: SpaceTV/ARB24/ARBGunes/StartTV/TRT2 stay in PICKS so they return
# automatically the day iptv-org gets a working stream for them again.

lines = ["#EXTM3U"]
count = 0
for group, idl in PICKS.items():
    for cid in idl:
        if cid not in by or cid not in channels:
            continue  # no working stream right now -> skipped
        best = sorted(by[cid], key=rank, reverse=True)[0]
        name = channels[cid]["name"]
        q = best.get("quality")
        disp = name + (f" ({q})" if q else "")
        lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logos.get(cid,"")}" group-title="{group}",{disp}')
        if best.get("user_agent"):
            lines.append(f'#EXTVLCOPT:http-user-agent={best["user_agent"]}')
        if best.get("referrer"):
            lines.append(f'#EXTVLCOPT:http-referrer={best["referrer"]}')
        lines.append(best["url"])
        count += 1

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"OK: {count} channels written")
