#!/usr/bin/env python3
"""Self-healing Azerbaijani IPTV playlist generator.

Every run (daily, on GitHub Actions):
 1. Pulls fresh channel/stream/feed data from the iptv-org public API.
 2. Drops streams whose FEED language is not az/tr/en/ru/uk (fixes e.g.
    an Arabic DW feed being picked for the DW entry). LANG_EXEMPT opts
    sports broadcasters out of that rule.
 3. DISCOVERY: fetches each broadcaster's own live page (SOURCES) and
    extracts static .m3u8 URLs. Tokenized URLs are never kept. Findings
    persist in discovered.json and are re-probed daily.
 4. HEALTH-CHECKS every candidate with a real HTTP probe and picks the
    best WORKING one; broken links are replaced automatically.
 5. LAST-KNOWN-GOOD RETENTION: a channel with no working candidate keeps
    its previous URL rather than vanishing -- but that URL is probed too,
    so it cannot outlive the stream. (The runner sits outside Azerbaijan,
    so .az / AZ_HOSTS keep the geo benefit of the doubt.)
 6. Writes playlist.m3u and WAITING.md, plus a commit message hint.
Set SKIP_CHECK=1 to skip probing and discovery (local testing only).
"""
import datetime, http.client, json, os, re, socket, ssl
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

MIRRORS = ["https://iptv-org.github.io/api/{}",
           "https://raw.githubusercontent.com/iptv-org/api/gh-pages/{}"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ALLOWED_LANGS = {"aze", "tur", "eng", "rus", "ukr"}
# Feed-language exemption. The filter above exists to stop a wrong-language
# feed being picked for a channel (an Arabic DW, say). These ids are opted
# out because the tag is not a content problem for this playlist:
#   - the sports broadcasters carry EPL/UCL but are tagged in local languages
#   - Fashion TV's working feed is tagged 'fra' and is near-wordless anyway
LANG_EXEMPT = {"Futbol.tj", "FutbolTV.uz", "UzReportTV.uz", "QazSport.kz",
               "M4Sport.hu", "Teledeporte.es", "OlympicChannel.es",
               "FashionTVParisLOriginal.fr"}
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE  # many IPTV hosts have bad certs

PLAYLIST = "playlist.m3u"
WAITING_FILE = "WAITING.md"
DISCOVERED_FILE = "discovered.json"
COMMIT_MSG_FILE = ".bot_commit_msg"

# Connection-level failures (no HTTP status at all). On Azerbaijan-facing
# CDNs these mean "refusing this datacenter IP", not "stream is dead".
CONN_ERRORS = (http.client.RemoteDisconnected, ConnectionError,
               TimeoutError, socket.timeout, urllib.error.URLError)

# Azerbaijani broadcasters do not all serve from .az hosts, so the TLD
# alone is not enough to decide who deserves the geo benefit of the doubt.
AZ_HOSTS = {"rtmp.baku.tv", "cbcsports-live.lg.mncdn.com"}

def az_facing(host):
    return host.endswith(".az") or host in AZ_HOSTS

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
# Confirmed dead or geo-blocked from inside Azerbaijan. Excluded as
# candidates, from retention, and from discovery, so they cannot come
# back. The channel ids stay in PICKS and rejoin automatically the day a
# working stream appears.
STREAM_BLOCKLIST = {
    "https://mn-nl.mncdn.com/cbcsports_live/cbcsports/playlist.m3u8",
    "https://mn-nl.mncdn.com/blutv_beyaztv2/live.m3u8",
    # 403 from Azerbaijan (TRT's own CDN geo-blocks it)
    "https://tv-trtbelgesel.medya.trt.com.tr/master.m3u8",
    # mediatriple broadcast is gone (404)
    "https://b01c02nl.mediatriple.net/videoonlylive/mtsxxkzwwuqtglive/broadcast_5fe462afc6a0e.smil/playlist.m3u8",
    # ATV (TR): times out from Azerbaijan; health check picks an alternate
    "https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/atv/atv_1080p.m3u8",
}

# Query parameters that mark a URL as per-session. Such URLs are never
# adopted from discovery -- they expire, and refreshing them would mean
# writing a token scraper.
TOKEN_PARAMS = {"token", "st", "e", "exp", "expires", "sig", "sign",
                "auth", "wmsauthsign", "hdnts", "key", "hash"}

def looks_tokenized(url):
    try:
        q = urllib.parse.urlsplit(url).query
    except ValueError:
        return True
    keys = {k.lower() for k, _ in urllib.parse.parse_qsl(q, keep_blank_values=True)}
    return bool(keys & TOKEN_PARAMS)

def url_allowed(url):
    return (url not in STREAM_BLOCKLIST
            and not any(b in url for b in BAD_HOSTS))

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
    if cid not in LANG_EXEMPT and langs and not (langs & ALLOWED_LANGS):
        continue  # wrong-language feed (e.g. DW Arabic/Espanol)
    by.setdefault(cid, []).append(s)

# Official stream URLs taken from each broadcaster's own live page and
# merged ahead of the iptv-org candidates, so ranking prefers them. Each
# one is verified static (no per-session token) and still health-checked
# like any other candidate -- but never dropped when the probe fails, see
# best_working().
OVERRIDES = {
    # TRT's own CDN, the one tabii uses
    "TRT1.tr": {"url": "https://trt.daioncdn.net/trt-1/master.m3u8?app=web",
                "quality": "1080p", "user_agent": None, "referrer": None},
    # cbcsport.az/live/ -- iptv-org's mn-nl host is stale (see
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

# Hand-found static candidates for channels iptv-org has no working entry
# for. Probed every run like any other candidate; they simply join the
# playlist the day they start answering. Never tokenized URLs.
WATCHLIST = {
    "TRT2.tr": ["https://trt.daioncdn.net/trt-2/master.m3u8?app=web"],
    "TRTBelgesel.tr": ["https://trt.daioncdn.net/trt-belgesel/master.m3u8?app=web"],
}
for _cid, _urls in WATCHLIST.items():
    for _u in _urls:
        if url_allowed(_u) and not looks_tokenized(_u):
            by.setdefault(_cid, []).append(
                {"url": _u, "quality": None, "user_agent": None,
                 "referrer": None, "feed": None})

# Broadcasters' own live pages, scraped daily for static .m3u8 URLs.
# Official domains ONLY -- never aggregators or restream sites.
SOURCES = {
    # arbtv.az/now currently answers with a JS "One moment, please..."
    # interstitial that reloads itself, so nothing is extractable without
    # running JS. Kept because it costs one request and may change back.
    "ARB.az":      ["http://arbtv.az/now", "https://www.arbtv.az/"],
    # 24.arbtv.az and gunesh.arbtv.az are NXDOMAIN; these are the domains
    # the broadcasters actually register.
    "ARB24.az":    ["http://arb24.az/"],
    "ARBGunes.az": ["https://www.arbgunesh.az/"],
    "VavTV.tr":    ["https://www.vavtv.com.tr/canli-yayin"],
    # SpaceTV.az: TODO -- iptv-org lists https://spacetv.az/ but that
    # domain has no A record (SOA only), so there is no official page to
    # scrape. Add here once the real domain is known.
}

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
    """Return (state, detail). State is 'ok', 'geo' (blocked for the
    runner, may still work in Azerbaijan) or 'dead'. Detail is a coarse,
    stable reason -- deliberately not precise, so WAITING.md does not
    churn between equivalent failures."""
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
                return "ok", "ok"
            return "dead", "not a manifest"
    except urllib.error.HTTPError as e:
        # 403/451 only earns the benefit of the doubt on AZ-facing hosts.
        # Anywhere else (and for 404/5xx) it means unusable from here.
        if e.code in (403, 451):
            return ("geo", "geo-blocked") if az_facing(host) else ("dead", "403 forbidden")
        if e.code == 404:
            return "dead", "404 not found"
        if 500 <= e.code < 600:
            return "dead", "server error"
        return "dead", f"http {e.code}"
    except CONN_ERRORS:
        # no HTTP response at all: on AZ-facing CDNs treat as geo-blocked
        if az_facing(host):
            return "geo", "geo-blocked"
        return "dead", "unreachable"
    except Exception:
        return "dead", "unreachable"

PICKS = {
"Azərbaycan 🇦🇿": ["AzTV.az","IctimaiTV.az","XezerTV.az","CBCSport.az","IdmanTV.az","BakuTV.az","APATv.az","AnewZTV.az","MedeniyyetTV.az","KanalS.az","Kanal35.az","NaxcivanTV.az","AlvinChannelTV.az","GunAzTV.us","AzStarTV.ca","SpaceTV.az","ARB24.az","ARBGunes.az","StartTV.az","AzadTV.az","ARB.az"],
"Ukrayna": ["FREEDOM.ua","Pershyi.ua"],
"Türkiyə – Ümumi": ["TRT1.tr","ATV.tr","KanalD.tr","StarTV.tr","NOWTV.tr","TV8.tr","Kanal7.tr","BeyazTV.tr","TRTAvaz.tr","TRTTurk.tr","TRT2.tr"],
"Xəbər – Türkiyə": ["TRTHaber.tr","HaberGlobal.tr","AHaber.tr","HaberturkTV.tr","TGRTHaber.tr","NTV.tr","24TV.tr","360.tr","TVNET.tr","HalkTV.tr","BloombergHT.tr","CNBCe.tr"],
"İdman": ["CBCSport.az","IdmanTV.az","ASpor.tr","TRT3.tr","TRTSporYildiz.tr","HTSporTV.tr","FBTV.tr","RedBullTV.at","beINSPORTSXTRA.us","FIFAPlus.uk","CBSSportsGolazoNetwork.us","Stadium.us","FuboSportsNetwork.us","Unbeaten.us","Futbol.tj","FutbolTV.uz","UzReportTV.uz","QazSport.kz","M4Sport.hu","Teledeporte.es","OlympicChannel.es"],
"Uşaq": ["TRTCocuk.tr","MinikaCocuk.tr","MinikaGo.tr","TRTDiyanetCocuk.tr","Carousel.ru"],
"Musiqi": ["TRTMuzik.tr","KralPopTV.tr","PowerTurkTV.tr","Number1TV.tr","DreamTurk.tr"],
"Sənədli": ["TRTBelgesel.tr","TGRTBelgesel.tr","CGTNDocumentary.cn","FashionTVParisLOriginal.fr","LoveNature.ca","SmithsonianChannelSelects.us","DMAX.tr","WildEarth.za","NatureTime.ca","INWILD.nl","PlutoTVScience.us","PlutoTVAdventure.us"],
"· russia": ["ChannelOne.ru","Russia1.ru","NTV.ru","STS.ru","RENTV.ru","Che.ru"],
"Beynəlxalq Xəbər": ["TRTWorld.tr","EuronewsEnglish.fr","EuronewsRussian.fr","DW.de","CGTN.cn","BloombergTV.us","SkyNews.ie","ABCNews.au","NHKWorldJapan.jp"],
}
# Streamless ids (IdmanTV, AzadTV, ARB, SpaceTV, ARB24, ARBGunes,
# StartTV, DMAX...) are kept on purpose: they join automatically the day
# a working stream appears, and are listed in WAITING.md meanwhile.
# CBCSport/IdmanTV are dual-grouped on purpose (Azərbaycan + İdman).

RENAME = {"Russia1.ru": "russia 1", "EuronewsRussian.fr": "Euronews russian",
          # carried under the Paris L'Original feed; keep the plain name
          "FashionTVParisLOriginal.fr": "Fashion TV"}

def display_name(cid):
    return RENAME.get(cid) or (channels.get(cid) or {}).get("name") or cid

GROUP_OF = {}
for _g, _idl in PICKS.items():
    for _cid in _idl:
        GROUP_OF.setdefault(_cid, []).append(_g)

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
            # first occurrence wins (dual-grouped ids repeat). Retention
            # honours BAD_HOSTS and STREAM_BLOCKLIST too, so a banned host
            # can never be reinstated by last-known-good.
            if cid and url_allowed(line):
                prev.setdefault(cid, {"name": name, "opts": opts, "url": line})
            cid, name, opts = None, "", []
    return prev

def opt_value(opts, key):
    for o in opts:
        if o.startswith(key):
            return o.split("=", 1)[1]
    return None

def load_prev_waiting(path=WAITING_FILE):
    """Channel names listed in the previous WAITING.md (first table only)."""
    names, started = set(), False
    try:
        txt = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return names
    for line in txt.splitlines():
        if line.startswith("| Channel "):
            started = True
            continue
        if started:
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and set("".join(cells)) <= set("-: "):
                continue
            if cells:
                names.add(cells[0])
    return names

# ---------------- discovery (broadcasters' own sites only) ----------------
SECOND_LEVEL = {"com", "net", "org", "gov", "edu", "co", "ac"}

def registrable(host):
    parts = (host or "").lower().split(".")
    if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])

def same_site(a, b):
    ra = registrable(urllib.parse.urlsplit(a).hostname)
    rb = registrable(urllib.parse.urlsplit(b).hostname)
    return bool(ra) and ra == rb

M3U8_RE = re.compile(r"""https?://[^\s"'<>\\)]+?\.m3u8[^\s"'<>\\)]*""")
JSON_FIELD_RE = re.compile(
    r"""["'](?:file|source|src|hls)["']\s*:\s*["']([^"']+)["']""", re.I)

def fetch_page(url, timeout=10):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "az-AZ,az;q=0.9,tr;q=0.8,en;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read(3_000_000).decode("utf-8", "replace"), r.geturl()

def extract_streams(text, base):
    t = text.replace("\\/", "/").replace("\\u002F", "/").replace("&amp;", "&")
    out = set(M3U8_RE.findall(t))
    for v in JSON_FIELD_RE.findall(t):
        v = v.replace("\\/", "/")
        if ".m3u8" in v:
            out.add(urllib.parse.urljoin(base, v))
    return {u.rstrip("\\\"',);") for u in out}

# A broadcaster's "live" page is sometimes a portal listing many other
# channels (vavtv.com.tr lists ~20). Harvesting those wholesale would
# attribute a rival channel's stream to this one, so a page yielding more
# than PORTAL_LIMIT URLs is treated as a portal: only URLs whose path
# names the channel are kept. A genuine single-channel page is unaffected.
PORTAL_LIMIT = 2

def name_token(cid):
    return re.sub(r"[^a-z0-9]", "", cid.split(".")[0].lower())

def names_channel(url, cid):
    token = name_token(cid)
    if not token:
        return False
    for seg in urllib.parse.urlsplit(url).path.lower().split("/"):
        seg = re.sub(r"[^a-z0-9]", "", seg.split(".")[0])
        if seg and (seg == token or seg.startswith(token) or token.startswith(seg)):
            return True
    return False

def discover(log):
    """Fetch each SOURCES page and return {cid: {url: page}}. Never fatal."""
    found = {}
    for cid, pages in SOURCES.items():
        for page in pages:
            try:
                html, final = fetch_page(page)
            except Exception as e:
                log.append(f"  {cid}: {page} -> {type(e).__name__} (skipped)")
                continue
            urls = extract_streams(html, final)
            for ifr in re.findall(r"""<iframe[^>]+src=["']([^"']+)""", html, re.I)[:6]:
                full = urllib.parse.urljoin(final, ifr.replace("\\/", "/"))
                if not full.startswith("http") or not same_site(full, final):
                    continue
                try:
                    sub, subfinal = fetch_page(full)
                except Exception as e:
                    log.append(f"  {cid}: iframe {full[:70]} -> {type(e).__name__}")
                    continue
                urls |= extract_streams(sub, subfinal)
            keep = {u for u in urls if url_allowed(u) and not looks_tokenized(u)}
            portal = len(keep) > PORTAL_LIMIT
            if portal:  # keep only what actually names this channel
                keep = {u for u in keep if names_channel(u, cid)}
            dropped = len(urls) - len(keep)
            log.append(f"  {cid}: {page} -> {len(urls)} m3u8 found, "
                       f"{len(keep)} kept"
                       f"{f', {dropped} filtered' if dropped else ''}"
                       f"{' [portal page: name-matched only]' if portal else ''}")
            for u in sorted(keep):
                log.append(f"      {u}")
                found.setdefault(cid, {})[u] = page
    return found

def load_discovered(path=DISCOVERED_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {c: dict(v) for c, v in data.items()} if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}

# ---------------- probe everything ----------------
skip_check = os.environ.get("SKIP_CHECK") == "1"
all_ids = {cid for idl in PICKS.values() for cid in idl}
previous = load_previous()
prev_waiting_names = load_prev_waiting()

discovery_log = []
discovered = load_discovered()
if not skip_check:
    for _cid, _urlmap in discover(discovery_log).items():
        discovered.setdefault(_cid, {}).update(_urlmap)
# stale entries can be retired by the blocklist just like anything else
discovered = {c: {u: p for u, p in m.items()
                  if url_allowed(u) and not looks_tokenized(u)}
              for c, m in discovered.items()}
discovered = {c: m for c, m in discovered.items() if m}

disc_by = {}
for _cid, _urlmap in discovered.items():
    for _u in sorted(_urlmap):
        disc_by.setdefault(_cid, []).append(
            {"url": _u, "quality": None, "user_agent": None,
             "referrer": None, "feed": None})

# Retained URLs are probed as well: a last-known-good entry must not
# outlive the stream it points at.
prev_streams = {
    cid: {"url": p["url"], "feed": None,
          "user_agent": opt_value(p["opts"], "#EXTVLCOPT:http-user-agent"),
          "referrer": opt_value(p["opts"], "#EXTVLCOPT:http-referrer")}
    for cid, p in previous.items() if cid in all_ids}

candidates = []
for cid in all_ids:
    candidates.extend(by.get(cid, []))
    candidates.extend(disc_by.get(cid, []))
candidates.extend(prev_streams.values())
status, detail_of = {}, {}
override_warnings = []
if not skip_check:
    with ThreadPoolExecutor(max_workers=24) as ex:
        for s, (st, det) in zip(candidates, ex.map(probe, candidates)):
            status[skey(s)] = st
            detail_of[skey(s)] = det

def _pick(pool):
    for s in sorted(pool, key=rank, reverse=True):
        if status.get(skey(s)) == "ok":
            return s
    for s in sorted(pool, key=rank, reverse=True):  # geo may work in AZ
        if status.get(skey(s)) == "geo":
            return s
    return None

def best_working(cid):
    pool = by.get(cid, [])
    if skip_check:
        return sorted(pool, key=rank, reverse=True)[0] if pool else None
    hit = _pick(pool)
    if hit is not None:
        return hit
    # Only a channel that would otherwise be waiting adopts a discovered
    # URL -- a live channel is never swapped out from under itself.
    hit = _pick(disc_by.get(cid, []))
    if hit is not None:
        return hit
    # Hand-verified overrides are never dropped on a failed probe: they
    # were checked against the broadcaster's own player, and the runner
    # sits outside Azerbaijan, so a failure here says more about the
    # runner's vantage point than the stream. Warn instead.
    ov = OVERRIDES.get(cid)
    if ov is not None:
        override_warnings.append(f"{cid} (probe={status.get(skey(ov), 'unprobed')})")
        return ov
    return None

def retained_usable(cid):
    """A retained URL survives only if it still probes ok -- unless it sits
    on an AZ-facing host, which keeps the geo benefit of the doubt."""
    s = prev_streams.get(cid)
    if s is None:
        return False
    if skip_check:
        return True
    if az_facing((urllib.parse.urlsplit(s["url"]).hostname or "").lower()):
        return True
    return status.get(skey(s)) == "ok"

# ---------------- build the playlist ----------------
lines = ["#EXTM3U"]
count = 0
published = set()
adopted = {}   # cid -> page it was discovered on
retained, stale, no_stream, unknown_id = [], [], [], []
for group, idl in PICKS.items():
    for cid in idl:
        best = best_working(cid)
        prev = previous.get(cid)
        if best is not None and cid in channels:
            disp = display_name(cid)
            q = best.get("quality")
            disp = disp + (f" ({q})" if q else "")
            opts = []
            if best.get("user_agent"):
                opts.append(f'#EXTVLCOPT:http-user-agent={best["user_agent"]}')
            if best.get("referrer"):
                opts.append(f'#EXTVLCOPT:http-referrer={best["referrer"]}')
            url = best["url"]
            if cid in discovered and url in discovered[cid]:
                adopted[cid] = discovered[cid][url]
        elif prev and retained_usable(cid):
            # last-known-good, and it still answers: keep the channel
            disp, opts, url = prev["name"], prev["opts"], prev["url"]
            retained.append(cid)
        elif prev:
            stale.append(cid)  # retained URL went dead -> hide it this run
            continue
        elif cid not in channels:
            unknown_id.append(cid)
            continue
        else:
            if by.get(cid) or disc_by.get(cid):
                no_stream.append(cid)
            continue
        lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logos.get(cid,"")}" '
                     f'group-title="{group}",{disp}')
        lines.extend(opts)
        lines.append(url)
        published.add(cid)
        count += 1

with open(PLAYLIST, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"OK: {count} channels written")

# ---------------- waiting list ----------------
def candidate_summary(cid):
    cands = by.get(cid, []) + disc_by.get(cid, [])
    if not cands:
        if cid in blocked_ids:
            return 0, "all known streams blocklisted"
        return 0, "no candidate URLs"
    if skip_check:
        return len(cands), "not probed"
    reasons = sorted({detail_of.get(skey(s), "unprobed") for s in cands})
    return len(cands), ", ".join(reasons)

waiting_rows = []
for cid in sorted(all_ids, key=lambda c: display_name(c).lower()):
    if cid in published or cid in OVERRIDES:
        continue
    n, why = candidate_summary(cid)
    waiting_rows.append((display_name(cid), "; ".join(GROUP_OF.get(cid, [])), n, why))

alternate_rows = []
for cid, urlmap in sorted(discovered.items(),
                          key=lambda kv: display_name(kv[0]).lower()):
    if cid not in published:
        continue
    for url, page in sorted(urlmap.items()):
        s = {"url": url, "feed": None}
        if status.get(skey(s)) == "ok" and cid not in adopted:
            alternate_rows.append((display_name(cid),
                                   "; ".join(GROUP_OF.get(cid, [])), url, page))

def render_report():
    out = ["# Waiting list", "",
           "Channels kept in the playlist config that have no working stream",
           "right now. Every one is re-probed on each run and rejoins",
           "`playlist.m3u` automatically as soon as a candidate passes.", ""]
    if waiting_rows:
        out += ["| Channel | Group | Candidates tried | Result |",
                "| --- | --- | --- | --- |"]
        out += [f"| {c} | {g} | {n} | {w} |" for c, g, n, w in waiting_rows]
    else:
        out.append("_Nothing waiting - every channel has a working stream._")
    out += ["", "## Alternates found", "",
            "Working streams found on a broadcaster's own site for channels",
            "that are already live. Listed only; never swapped in.", ""]
    if alternate_rows:
        out += ["| Channel | Group | Alternate URL | Found on |",
                "| --- | --- | --- | --- |"]
        out += [f"| {c} | {g} | {u} | {p} |" for c, g, u, p in alternate_rows]
    else:
        out.append("_None._")
    return "\n".join(out) + "\n"

report_text = render_report()
with open(WAITING_FILE, "w", encoding="utf-8") as f:
    f.write(report_text)

with open(DISCOVERED_FILE, "w", encoding="utf-8") as f:
    json.dump({c: dict(sorted(m.items())) for c, m in sorted(discovered.items())},
              f, indent=2, ensure_ascii=False)
    f.write("\n")

summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
if summary_path:
    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(f"## Playlist status {datetime.date.today().isoformat()}\n\n")
            f.write(f"{count} channels published.\n\n")
            f.write(report_text)
    except OSError as e:
        print(f"note: could not write step summary ({e})")

# ---------------- commit message hint ----------------
new_waiting_names = {r[0] for r in waiting_rows}
returned = sorted(prev_waiting_names - new_waiting_names)
msg = []
for cid, page in sorted(adopted.items(), key=lambda kv: display_name(kv[0]).lower()):
    host = urllib.parse.urlsplit(page).hostname or page
    msg.append(f"bot: discovered {display_name(cid)} on {host}")
    returned = [r for r in returned if r != display_name(cid)]
if returned:
    verb = "is back" if len(returned) == 1 else "are back"
    msg.append(f"bot: {', '.join(returned)} {verb}")
if not msg:
    msg.append("Auto-update playlist")
with open(COMMIT_MSG_FILE, "w", encoding="utf-8") as f:
    f.write(msg[0] + "\n")
    if len(msg) > 1:
        f.write("\n" + "\n".join(msg[1:]) + "\n")

# ---------------- console report ----------------
def report(label, ids):
    if ids:
        print(f"{label}:", ", ".join(sorted(set(ids))))
report("Retained last-known-good (no working stream this run)", retained)
report("Dropped (last-known-good URL no longer responds)", stale)
report("Dropped (no working stream and no previous entry)", no_stream)
report("Skipped (id not in channels.json)", unknown_id)
report("WARNING: override kept despite failed probe", override_warnings)
report("Blocklisted (only stream(s) removed by STREAM_BLOCKLIST)",
       [cid for cid in all_ids if cid in blocked_ids
        and not by.get(cid) and not disc_by.get(cid)])
if discovery_log:
    print("Discovery:")
    for line in discovery_log:
        print(line)
print(f"Waiting list: {len(waiting_rows)} channel(s); "
      f"alternates found: {len(alternate_rows)}")
