#!/usr/bin/env python3
"""Self-healing Azerbaijani IPTV playlist generator.

Every run (daily, on GitHub Actions):
 1. Pulls fresh channel/stream/feed data from the iptv-org public API.
 2. Drops streams whose FEED language is not az/tr/en/ru (fixes e.g.
    an Arabic DW feed being picked for the DW entry).
 3. HEALTH-CHECKS every candidate stream with a real HTTP probe and
    picks the best WORKING one; broken links are replaced by working
    alternates automatically, channels with no working stream are
    skipped until one appears.
 4. Writes playlist.m3u.
Set SKIP_CHECK=1 to skip health checks (for local testing only).
"""
import json, os, ssl, urllib.request
from concurrent.futures import ThreadPoolExecutor

MIRRORS = ["https://iptv-org.github.io/api/{}",
           "https://raw.githubusercontent.com/iptv-org/api/gh-pages/{}"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ALLOWED_LANGS = {"aze", "tur", "eng", "rus"}
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE  # many IPTV hosts have bad certs

def get(name):
    last = None
    for m in MIRRORS:
        try:
            req = urllib.request.Request(m.format(name), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            last = e
    raise last

channels = {c["id"]: c for c in get("channels.json")}
feed_langs = {(f["channel"], f["id"]): set(f.get("languages") or [])
              for f in get("feeds.json")}
logos = {}
for l in get("logos.json"):
    if l.get("channel") and l["channel"] not in logos:
        logos[l["channel"]] = l["url"]

BAD_HOSTS = ["raw.githubusercontent.com"]  # dead restream repo
by = {}
for s in get("streams.json"):
    cid = s.get("channel")
    if not cid or any(b in s["url"] for b in BAD_HOSTS):
        continue
    langs = feed_langs.get((cid, s.get("feed")))
    if langs and not (langs & ALLOWED_LANGS):
        continue  # wrong-language feed (e.g. DW Arabic/Espanol)
    by.setdefault(cid, []).append(s)

# Verified TRT 1 stream (TRT's own CDN, used by tabii)
by["TRT1.tr"] = [{"url": "https://trt.daioncdn.net/trt-1/master.m3u8?app=web",
                  "quality": "1080p", "user_agent": None, "referrer": None}] \
                + by.get("TRT1.tr", [])

OFFICIAL = ["trt.com.tr", "daioncdn", "baku.tv", "itv.az", "atv.az",
            "xezerxeber.az", "yodacdn", "mncdn", "akamaized", "trt.com",
            "bloomberg.com", "nhkworld.jp", "cgtn.com", "cosmonova"]
def qscore(s):
    q = s.get("quality") or ""
    try: return int(q.replace("p", "").replace("i", ""))
    except ValueError: return 0
def rank(s):
    return (any(d in s["url"] for d in OFFICIAL), qscore(s))

def probe(stream):
    """Return 'ok', 'geo' (403/451: blocked for the runner, may still
    work in Azerbaijan) or 'dead'."""
    url = stream["url"]
    headers = {"User-Agent": stream.get("user_agent") or UA}
    if stream.get("referrer"):
        headers["Referer"] = stream["referrer"]
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12, context=SSL_CTX) as r:
            body = r.read(2048)
            ctype = (r.headers.get("Content-Type") or "").lower()
            if b"#EXTM3U" in body or "mpegurl" in ctype or "octet-stream" in ctype:
                return "ok"
            return "dead"
    except urllib.error.HTTPError as e:
        return "geo" if e.code in (403, 451) else "dead"
    except Exception:
        return "dead"

PICKS = {
"Azərbaycan 🇦🇿": ["AzTV.az","IctimaiTV.az","XezerTV.az","CBCSport.az","IdmanTV.az","BakuTV.az","APATv.az","AnewZTV.az","MedeniyyetTV.az","KanalS.az","Kanal35.az","NaxcivanTV.az","AlvinChannelTV.az","GunAzTV.us","AzStarTV.ca","SpaceTV.az","ARB24.az","ARBGunes.az","StartTV.az","AzadTV.az","ARB.az"],
"Ukrayna (rus dilində)": ["FREEDOM.ua"],
"Türkiyə – Ümumi": ["TRT1.tr","ATV.tr","KanalD.tr","StarTV.tr","NOWTV.tr","TV8.tr","Kanal7.tr","BeyazTV.tr","TRTAvaz.tr","TRTTurk.tr","EuroD.tr","KanalDDrama.tr","DreamTurk.tr","TRT2.tr"],
"Xəbər – Türkiyə": ["TRTHaber.tr","HaberGlobal.tr","AHaber.tr","HaberturkTV.tr","TGRTHaber.tr","NTV.tr","24TV.tr","360.tr","TVNET.tr","HalkTV.tr","BloombergHT.tr","CNBCe.tr"],
"İdman": ["CBCSport.az","IdmanTV.az","ASpor.tr","TRT3.tr","TRTSporYildiz.tr","HTSporTV.tr","FBTV.tr","RedBullTV.at"],
"Uşaq": ["TRTCocuk.tr","MinikaCocuk.tr","MinikaGo.tr","TRTDiyanetCocuk.tr","Carousel.ru"],
"Musiqi": ["TRTMuzik.tr","KralPopTV.tr","PowerTurkTV.tr","PowerTV.tr","PowerDance.tr","PowerLove.tr","Number1TV.tr","Number1Dance.tr","Number1Damar.tr","MuzTV.ru","RUTV.ru","EuropaPlusTV.ru"],
"Sənədli və Həyat tərzi": ["TRTBelgesel.tr","TGRTBelgesel.tr","CGTNDocumentary.cn","Tastemade.us","TastemadeTravel.us","FashionTVEurope.fr","RealWild.uk","LoveNature.ca","SmithsonianChannelSelects.us","DMAX.tr"],
"russia": ["ChannelOne.ru","Russia1.ru","NTV.ru","STS.ru","RENTV.ru","Che.ru"],
"Beynəlxalq Xəbər": ["TRTWorld.tr","EuronewsEnglish.fr","EuronewsRussian.fr","DW.de","CGTN.cn","BloombergTV.us","SkyNews.ie","ABCNews.au","NHKWorldJapan.jp","ArirangTV.kr","CNA.sg","TVPWorld.pl"],
}
# Streamless ids (IdmanTV, AzadTV, ARB, SpaceTV, ARB24, ARBGunes,
# StartTV, DMAX, TRT2...) are kept on purpose: they join automatically
# the day a working stream appears. CBCSport/IdmanTV are dual-grouped
# on purpose (Azərbaycan + İdman).

RENAME = {"Russia1.ru": "russia 1", "EuronewsRussian.fr": "Euronews russian"}

# ---- health-check all candidate streams concurrently ----
skip_check = os.environ.get("SKIP_CHECK") == "1"
all_ids = {cid for idl in PICKS.values() for cid in idl}
candidates = []
for cid in all_ids:
    candidates.extend(by.get(cid, []))
status = {}
if not skip_check:
    with ThreadPoolExecutor(max_workers=24) as ex:
        for s, st in zip(candidates, ex.map(probe, candidates)):
            status[id(s)] = st

def best_working(cid):
    ordered = sorted(by.get(cid, []), key=rank, reverse=True)
    if not ordered:
        return None
    if skip_check:
        return ordered[0]
    for s in ordered:
        if status.get(id(s)) == "ok":
            return s
    for s in ordered:  # geo-blocked for the US runner may work in AZ
        if status.get(id(s)) == "geo":
            return s
    return None

lines = ["#EXTM3U"]
count, dropped = 0, []
for group, idl in PICKS.items():
    for cid in idl:
        best = best_working(cid)
        if best is None or cid not in channels:
            if cid in by:
                dropped.append(cid)
            continue
        name = RENAME.get(cid) or channels[cid]["name"]
        q = best.get("quality")
        disp = name + (f" ({q})" if q else "")
        lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logos.get(cid,"")}" '
                     f'group-title="{group}",{disp}')
        if best.get("user_agent"):
            lines.append(f'#EXTVLCOPT:http-user-agent={best["user_agent"]}')
        if best.get("referrer"):
            lines.append(f'#EXTVLCOPT:http-referrer={best["referrer"]}')
        lines.append(best["url"])
        count += 1

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"OK: {count} channels written")
if dropped:
    print("Dropped this run (no working stream found):", ", ".join(sorted(set(dropped))))
