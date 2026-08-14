#!/usr/bin/env python3
"""Self-healing Azerbaijani IPTV playlist generator.

Every run (daily, on GitHub Actions):
 1. Pulls fresh channel/stream/feed data from the iptv-org public API.
 2. Drops streams whose FEED language is not az/tr/en/ru (fixes e.g.
    an Arabic DW feed being picked for the DW entry).
 3. HEALTH-CHECKS every candidate stream with a real HTTP probe and
    picks the best WORKING one; broken links are replaced by working
    alternates automatically.
 4. LAST-KNOWN-GOOD RETENTION: a channel with no working candidate this
    run keeps its previous URL from playlist.m3u instead of vanishing.
    A channel is only ever replaced by a verified-working stream, never
    silently deleted. (The health check runs from a US GitHub runner,
    which cannot reach several Azerbaijan-facing CDNs.)
 5. Writes playlist.m3u.
Set SKIP_CHECK=1 to skip health checks (for local testing only).
"""
import http.client, json, os, re, socket, ssl
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

MIRRORS = ["https://iptv-org.github.io/api/{}",
           "https://raw.githubusercontent.com/iptv-org/api/gh-pages/{}"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ALLOWED_LANGS = {"aze", "tur", "eng", "rus"}
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE  # many IPTV hosts have bad certs

PLAYLIST = "playlist.m3u"
# Connection-level failures (no HTTP status at all). On Azerbaijan-facing
# CDNs these mean "refusing this datacenter IP", not "stream is dead".
CONN_ERRORS = (http.client.RemoteDisconnected, ConnectionError,
               TimeoutError, socket.timeout, urllib.error.URLError)

def az_facing(host):
    return host.endswith(".az")

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

BAD_HOSTS = ["raw.githubusercontent.com",       # dead restream repo
             "zabava-htlive.cdn.ngenix.net"]    # Wink CDN: "not available
             # in your territory" from Azerbaijan (Che, REN TV et al).
             # Host-level so every stream on it is skipped and the health
             # check falls through to each channel's alternates.
# Confirmed dead from inside Azerbaijan (not geo-blocking). Excluded both
# as candidates and from last-known-good retention, so they cannot come
# back. CBCSport.az/BeyazTV.tr stay in PICKS and rejoin automatically the
# day iptv-org lists a working stream for them.
STREAM_BLOCKLIST = {
    "https://mn-nl.mncdn.com/cbcsports_live/cbcsports/playlist.m3u8",
    "https://mn-nl.mncdn.com/blutv_beyaztv2/live.m3u8",
}
by = {}
blocked_ids = set()  # ids that lost at least one stream to the blocklist
for s in get("streams.json"):
    cid = s.get("channel")
    if not cid or any(b in s["url"] for b in BAD_HOSTS):
        continue
    if s["url"] in STREAM_BLOCKLIST:
        blocked_ids.add(cid)
        continue
    langs = feed_langs.get((cid, s.get("feed")))
    if langs and not (langs & ALLOWED_LANGS):
        continue  # wrong-language feed (e.g. DW Arabic/Espanol)
    by.setdefault(cid, []).append(s)

# Official stream URLs taken from each broadcaster's own live page and
# merged ahead of the iptv-org candidates, so ranking prefers them. Each
# one is verified static (no per-session token) and still health-checked
# like any other candidate.
OVERRIDES = {
    # TRT's own CDN, the one tabii uses
    "TRT1.tr": {"url": "https://trt.daioncdn.net/trt-1/master.m3u8?app=web",
                "quality": "1080p", "user_agent": None, "referrer": None},
    # cbcsport.az/live/ — iptv-org's mn-nl host is stale (see
    # STREAM_BLOCKLIST); this edge works and needs no Referer/User-Agent
    "CBCSport.az": {"url": "https://cbcsports-live.lg.mncdn.com/cbcsports_live/cbcsports/playlist.m3u8",
                    "quality": "1080p", "user_agent": None, "referrer": None},
    # atv.az/live -> Ant Media player on ATV's own server (the same host
    # that already serves Kanal S). Needs no Referer/User-Agent.
    "AzadTV.az": {"url": "https://lives.atv.az:5443/ATV_TV_STREAM/streams/atvcanli.m3u8",
                  "quality": None, "user_agent": None, "referrer": None},
}
for _cid, _ov in OVERRIDES.items():
    by[_cid] = [_ov] + by.get(_cid, [])

OFFICIAL = ["trt.com.tr", "daioncdn", "baku.tv", "itv.az", "atv.az",
            "xezerxeber.az", "yodacdn", "mncdn", "akamaized", "trt.com",
            "bloomberg.com", "nhkworld.jp", "cgtn.com", "cosmonova"]
def qscore(s):
    q = s.get("quality") or ""
    try: return int(q.replace("p", "").replace("i", ""))
    except ValueError: return 0
def rank(s):
    return (any(d in s["url"] for d in OFFICIAL), qscore(s))

def skey(s):
    """Stable identity for a stream dict (used to key probe results)."""
    return (s.get("feed"), s["url"])

def probe(stream):
    """Return 'ok', 'geo' (blocked for the runner, may still work in
    Azerbaijan) or 'dead'."""
    url = stream["url"]
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
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
    except CONN_ERRORS:
        # no HTTP response at all: on AZ-facing CDNs treat as geo-blocked
        return "geo" if az_facing(host) else "dead"
    except Exception:
        return "dead"

PICKS = {
"Azərbaycan 🇦🇿": ["AzTV.az","IctimaiTV.az","XezerTV.az","CBCSport.az","IdmanTV.az","BakuTV.az","APATv.az","AnewZTV.az","MedeniyyetTV.az","KanalS.az","Kanal35.az","NaxcivanTV.az","AlvinChannelTV.az","GunAzTV.us","AzStarTV.ca","SpaceTV.az","ARB24.az","ARBGunes.az","StartTV.az","AzadTV.az","ARB.az"],
"Ukrayna": ["FREEDOM.ua","Pershyi.ua"],
"Türkiyə – Ümumi": ["TRT1.tr","ATV.tr","KanalD.tr","StarTV.tr","NOWTV.tr","TV8.tr","Kanal7.tr","BeyazTV.tr","TRTAvaz.tr","TRTTurk.tr","DreamTurk.tr","TRT2.tr"],
"Xəbər – Türkiyə": ["TRTHaber.tr","HaberGlobal.tr","AHaber.tr","HaberturkTV.tr","TGRTHaber.tr","NTV.tr","24TV.tr","360.tr","TVNET.tr","HalkTV.tr","BloombergHT.tr","CNBCe.tr"],
"İdman": ["CBCSport.az","IdmanTV.az","ASpor.tr","TRT3.tr","TRTSporYildiz.tr","HTSporTV.tr","FBTV.tr","RedBullTV.at","beINSPORTSXTRA.us","FIFAPlus.uk"],
"Uşaq": ["TRTCocuk.tr","MinikaCocuk.tr","MinikaGo.tr","TRTDiyanetCocuk.tr","Carousel.ru"],
"Musiqi": ["TRTMuzik.tr","KralPopTV.tr","PowerTurkTV.tr","Number1TV.tr"],
"Sənədli və Həyat tərzi": ["TRTBelgesel.tr","TGRTBelgesel.tr","CGTNDocumentary.cn","FashionTVEurope.fr","LoveNature.ca","SmithsonianChannelSelects.us","DMAX.tr","WildEarth.za","PBSNature.us","NatureTime.ca","INWILD.nl","PlutoTVScience.us","PlutoTVAdventure.us"],
"· russia": ["ChannelOne.ru","Russia1.ru","NTV.ru","STS.ru","RENTV.ru","Che.ru"],
"Beynəlxalq Xəbər": ["TRTWorld.tr","EuronewsEnglish.fr","EuronewsRussian.fr","DW.de","CGTN.cn","BloombergTV.us","SkyNews.ie","ABCNews.au","NHKWorldJapan.jp"],
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
            status[skey(s)] = st

def best_working(cid):
    ordered = sorted(by.get(cid, []), key=rank, reverse=True)
    if not ordered:
        return None
    if skip_check:
        return ordered[0]
    for s in ordered:
        if status.get(skey(s)) == "ok":
            return s
    for s in ordered:  # geo-blocked for the US runner may work in AZ
        if status.get(skey(s)) == "geo":
            return s
    return None

def load_previous(path=PLAYLIST):
    """Map channel id -> last published {name, opts, url} from playlist.m3u."""
    prev = {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read().splitlines()
    except FileNotFoundError:
        return prev
    cid, name, opts = None, "", []
    for line in raw:
        if line.startswith("#EXTINF"):
            m = re.search(r'tvg-id="([^"]*)"', line)
            cid = m.group(1) if m else None
            name = line.split(",", 1)[1] if "," in line else ""
            opts = []
        elif line.startswith("#EXTVLCOPT"):
            opts.append(line)
        elif line and not line.startswith("#"):
            # first occurrence wins (dual-grouped ids repeat); blocklisted
            # URLs are never retained
            if cid and line not in STREAM_BLOCKLIST:
                prev.setdefault(cid, {"name": name, "opts": opts, "url": line})
            cid, name, opts = None, "", []
    return prev

previous = load_previous()

lines = ["#EXTM3U"]
count = 0
retained, no_stream, unknown_id = [], [], []
for group, idl in PICKS.items():
    for cid in idl:
        best = best_working(cid)
        prev = previous.get(cid)
        if best is not None and cid in channels:
            name = RENAME.get(cid) or channels[cid]["name"]
            q = best.get("quality")
            disp = name + (f" ({q})" if q else "")
            opts = []
            if best.get("user_agent"):
                opts.append(f'#EXTVLCOPT:http-user-agent={best["user_agent"]}')
            if best.get("referrer"):
                opts.append(f'#EXTVLCOPT:http-referrer={best["referrer"]}')
            url = best["url"]
        elif prev:  # last-known-good: keep it rather than lose the channel
            disp, opts, url = prev["name"], prev["opts"], prev["url"]
            retained.append(cid)
        elif cid not in channels:
            unknown_id.append(cid)
            continue
        else:
            if cid in by:  # had candidates, none usable, nothing to fall back on
                no_stream.append(cid)
            continue
        lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logos.get(cid,"")}" '
                     f'group-title="{group}",{disp}')
        lines.extend(opts)
        lines.append(url)
        count += 1

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"OK: {count} channels written")
def report(label, ids):
    if ids:
        print(f"{label}:", ", ".join(sorted(set(ids))))
report("Retained last-known-good (no working stream this run)", retained)
report("Dropped (no working stream and no previous entry)", no_stream)
report("Skipped (id not in channels.json)", unknown_id)
# ids left with no candidates at all because STREAM_BLOCKLIST took them
report("Blocklisted (only stream(s) removed by STREAM_BLOCKLIST)",
       [cid for cid in all_ids if cid in blocked_ids and cid not in by])
