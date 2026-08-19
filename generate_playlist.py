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
import datetime, http.client, json, os, re, socket, ssl, sys, unicodedata
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

# SINGLE AUTHOR: only the GitHub runner writes the generated files, so a
# local run can never race the bot or hand it a half-finished playlist.
# Locally this is a preview: everything is computed and reported, nothing
# is written. Pass --write to override deliberately.
IS_CI = os.environ.get("GITHUB_ACTIONS") == "true"
WRITE = IS_CI or "--write" in sys.argv
PREVIEW_NOTE = "PREVIEW - local vantage; runner is authoritative"

def preview_banner():
    if WRITE and not IS_CI:
        print("!! --write on a local run: these files are normally the runner's")
        return
    if WRITE:
        return
    print("=" * 72)
    print(f"!! {PREVIEW_NOTE}")
    print("!! Nothing is written. Counts reflect what THIS machine can reach,")
    print("!! which differs from the runner's vantage. Do not quote these")
    print("!! numbers as published figures.")
    print("=" * 72)

preview_banner()

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
AUTO_STATE_FILE = "auto_state.json"
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
# broadcast_area, languages and format live on the FEED, not the channel
# (channels.json has no broadcast_area field at all).
_feeds = get("feeds.json")
feed_langs = {(f["channel"], f["id"]): set(f.get("languages") or [])
              for f in _feeds}
chan_langs, chan_areas, chan_format = {}, {}, {}
for _f in _feeds:
    _ch = _f["channel"]
    chan_langs.setdefault(_ch, set()).update(_f.get("languages") or [])
    chan_areas.setdefault(_ch, set()).update(_f.get("broadcast_area") or [])
    _m = re.match(r"(\d+)", _f.get("format") or "")
    if _m:
        chan_format[_ch] = max(chan_format.get(_ch, 0), int(_m.group(1)))
logos = {}
for l in get("logos.json"):
    if l.get("channel") and l["channel"] not in logos:
        logos[l["channel"]] = l["url"]

# Substrings matched against the WHOLE URL, so a path slug counts too, not
# just the hostname. Everything here is skipped as a candidate, in retention
# and in discovery, and the health check falls through to the alternates.
BAD_HOSTS = ["raw.githubusercontent.com",       # dead restream repo
             "zabava-htlive.cdn.ngenix.net",    # Wink CDN: "not available
             # in your territory" from Azerbaijan (Che, REN TV et al).
             # amagi's Samsung TV Plus UK playouts: three for three 403 from
             # Baku while passing the US runner -- Curiosity NOW, Earth Touch
             # and NatureTime -- so the slug family is treated as a rule
             # rather than blocklisted one URL at a time as each surfaces.
             # Both spellings occur, sometimes in the same URL.
             # Deliberately NOT "samsunguk": WaterBear and INWILD ride that
             # slug and neither vantage has been measured, so it stays open.
             "samsung-gb",
             "samsunggb",
             # Pirate restreamers. Both PASS from Baku -- which is the whole
             # point: a Baku pass proves a stream is watchable and says
             # nothing about whether it is legal to carry, and a pirate
             # restream passes by its nature. Ranking would happily promote
             # them, so legality has to be enforced separately from
             # reachability. Host-level, so every path on them is excluded.
             "ayakkabiparti.lol",   # serves natgeo/viasat pay-channel rips
             "freem3u.xyz"]         # promoted from a single-URL blocklist
                                    # entry: the whole host is an aggregator
# Confirmed dead, geo-blocked from inside Azerbaijan, or not a legal free
# feed. Excluded as candidates, from retention, and from discovery, so they
# cannot come back. The channel ids stay in PICKS and rejoin automatically
# the day a working stream appears.
STREAM_BLOCKLIST = {
    "https://mn-nl.mncdn.com/cbcsports_live/cbcsports/playlist.m3u8",
    "https://mn-nl.mncdn.com/blutv_beyaztv2/live.m3u8",
    # 403 from Azerbaijan (TRT's own CDN geo-blocks it)
    "https://tv-trtbelgesel.medya.trt.com.tr/master.m3u8",
    # mediatriple broadcast is gone (404)
    "https://b01c02nl.mediatriple.net/videoonlylive/mtsxxkzwwuqtglive/broadcast_5fe462afc6a0e.smil/playlist.m3u8",
    # ATV (TR): times out from Azerbaijan; health check picks an alternate
    "https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/atv/atv_1080p.m3u8",
    # BBC News via Samsung TV Plus US: 403 from Azerbaijan but fine from the
    # runner, and it outranks BBC's own edge on quality, so ranking alone
    # would keep pinning BBC News to a stream the user cannot watch.
    "https://pb-iiczlgfysam0q.akamaized.net/v1/amcnetworks_bbcnews_1/samsungheadend_us/latest/main/hls/playlist.m3u8",
    # Travelxp 4K: a Tata Play pay-DTH origin leak, not a free feed, so the
    # legal-only rule forbids it. It has to be named here rather than merely
    # left out of WATCHLIST: iptv-org carries it, and rank() reads the
    # akamaized host as official at 2160p, so it would outrank Travelxp's
    # legitimate Samsung-India playout and get pinned as the pick.
    "https://deltatesttatasky.akamaized.net/out/i/968284.m3u8",
    # ISP test endpoint leaking FilmBox's pay channel DocuBox
    "https://dash3.antik.sk/live/test_docubox_medium_atk/playlist.m3u8",
    # passes US runner, 403 from Azerbaijan (reverse vantage split)
    "https://amg00170-amg00170c4-samsung-gb-4232.playouts.now.amagi.tv/playlist.m3u8",
    # 1080p wins ranking on the US runner but 403s from Azerbaijan;
    # the Rakuten-DE feed passes both vantages
    "https://amg00416-amg00416c9-samsung-in-4882.playouts.now.amagi.tv/playlist/amg00416-travelxp-travelxphd-samsungin/playlist.m3u8",
    # NatureTime: passes US runner, 403 from Baku (vantage split)
    "https://amg01515-amg01515c43-samsung-gb-9038.playouts.now.amagi.tv/playlist.m3u8",
    # BBC Earth: same split, measured this round
    "https://pb-zjy36qhp8e8cz.akamaized.net/BBC_Earth_US.m3u8",
    # upstream mislabels Love Nature Australia playouts under NatureTime.ca
    "https://amg00090-blueantllc-lovenature-au-samsungau-wggcn.amagi.tv/playlist/amg00090-blueantllc-lovenature-au-samsungau/playlist.m3u8",
    "https://amg00090-blueantllc-lovenatureau-samsungnz-r3iaz.amagi.tv/playlist/amg00090-blueantllc-lovenatureau-samsungnz/playlist.m3u8",
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
    if keys & TOKEN_PARAMS:
        return True
    # exact-key matching misses names like authToken, which is how a Pluto
    # stitcher URL carrying an expiring JWT nearly got pinned as a PICK
    return any(frag in k for k in keys
               for frag in ("token", "expires", "signature", "wmsauthsign"))

def url_allowed(url):
    return (url not in STREAM_BLOCKLIST
            and not any(b in url for b in BAD_HOSTS))

# A candidate that has failed the probe this many consecutive runs is
# dropped from discovered.json / skipped in WATCHLIST, so dead leads do
# not accumulate forever.
PRUNE_AFTER = 60
DEFAULT_STATE = {"discovered": {}, "watchlist": {}}

def load_state(path=DISCOVERED_FILE):
    """discovered.json: {"discovered": {cid: {url: {page, fails}}},
    "watchlist": {url: {fails}}}. Older flat {cid: {url: page}} files are
    migrated on read."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return json.loads(json.dumps(DEFAULT_STATE))
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT_STATE))
    if "discovered" in data or "watchlist" in data:
        raw_disc, raw_wl = data.get("discovered") or {}, data.get("watchlist") or {}
    else:
        raw_disc, raw_wl = data, {}          # migrate the old flat schema
    disc = {}
    for cid, m in raw_disc.items():
        if not isinstance(m, dict):
            continue
        for url, v in m.items():
            if isinstance(v, str):
                entry = {"page": v, "fails": 0}
            elif isinstance(v, dict):
                entry = {"page": v.get("page", ""), "fails": int(v.get("fails", 0) or 0)}
            else:
                continue
            disc.setdefault(cid, {})[url] = entry
    wl = {u: {"fails": int((v or {}).get("fails", 0) or 0)}
          for u, v in raw_wl.items() if isinstance(v, dict)}
    return {"discovered": disc, "watchlist": wl}

state = load_state()

# ---------------- Baku vantage data (BAKU.json) --------------------------
# The runner sits in the US and the viewer is in Baku, so a probe from CI
# answers a different question than "can this actually be watched". BAKU.json
# records what THIS machine measured: {url: {"ok": bool, "ts": "YYYY-MM-DD"}}.
# It is written only by a local run and only read by the runner -- the single
# deliberate exception to "only the runner writes", because only this machine
# can produce it. It is committed from here like code.
# It biases RANKING and gates bench seats (see SUBSTITUTES). It never excludes
# anything -- STREAM_BLOCKLIST and BAD_HOSTS remain the only tools that do.
#
# LAST VERDICT WINS, WITH NO EXPIRY. There is no scheduled sync: this machine
# is usually off, and Baku data refreshes only as a side effect of a
# maintenance preview. A freshness window would therefore not model "recent
# truth", it would model "how long since someone happened to run a preview" --
# and every reading would silently decay to unknown, which is precisely the
# state that lets a geo-blocked URL win a seat. So a verdict stands until a
# newer probe of that same URL overwrites it, however old it is. The timestamp
# is kept for the reader, not for the logic. The cost is that a transient
# failure sticks until re-probed; the benefit is that the system stays safe
# under arbitrarily stale data, which is the condition it actually runs in.
BAKU_FILE = "BAKU.json"

def load_baku(path=BAKU_FILE):
    """Return (raw entries, {url: +1 ok / -1 failed}) for every URL on record."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}
    raw, pref = {}, {}
    for url, e in data.items():
        if not isinstance(e, dict):
            continue
        raw[url] = {"ok": bool(e.get("ok")), "ts": str(e.get("ts") or "")}
        pref[url] = 1 if raw[url]["ok"] else -1
    return raw, pref

baku_raw, baku_pref = load_baku()

def baku_verdict(url):
    """The most recent Baku reading for a URL: True if it played here, False
    if it did not, None if it was never measured. Age is irrelevant -- see the
    no-expiry note above."""
    e = baku_raw.get(url)
    return None if e is None else bool(e.get("ok"))

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
# "expected_fail": True marks an override that is verified from Baku and
# KNOWN to fail from the runner. Its daily failure is vantage noise, not
# news, so it is reported on a quiet line and counted separately -- which
# is the whole point: an unflagged override that starts failing still
# stands out instead of being lost among the known-noisy ones. The run
# also says so if a flagged override starts passing, since the flag is
# then stale.
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
    # BBC's own worldwide CDN. iptv-org's highest-ranked BBC News stream is
    # a Samsung TV Plus US feed that 403s from Azerbaijan while passing from
    # the runner, so ranking alone would keep picking an unwatchable stream.
    # The "ww" edge works from both; the "uk" edge 403s outside the UK.
    "BBCNews.uk": {"url": "https://vs-hls-push-ww-live.akamaized.net/x=4/i=urn:bbc:pips:service:bbc_news_channel_hd/mobile_wifi_main_hd_abr_v2.m3u8",
                   "quality": "720p", "user_agent": None, "referrer": None},
    # Sky News, pinned to the Xumo/NBCUniversal FAST host that
    # xemzi.short.gy/1000018 resolves to -- one hop fewer, no query string,
    # and Sky is a Comcast/NBCU channel so this is its own distributor. The
    # shortener stays in the candidate pool as a fallback, not blocklisted.
    "SkyNews.ie": {"url": "https://xumo-drct-skynews-nc91a.fast.nbcuni.com/live/master.m3u8",
                   "quality": "1080p", "user_agent": None, "referrer": None},
    # showtv.com.tr/canli-yayin serves this with st= and e= session params
    # appended; dropping those two leaves a static URL that still answers
    # from Azerbaijan, so Show TV enters as a working pick, not a waiting one.
    "ShowTV.tr": {"url": "https://ciner.daioncdn.net/showtv/showtv.m3u8?ce=3&app=4bc856ef-4c68-4a94-bc87-37dfaaa66558",
                  "quality": "1080p", "user_agent": None, "referrer": None},
    # TRT Cocuk on TRT's own medya CDN. Verified 200 from Azerbaijan, but the
    # runner reaches it only intermittently -- one failed probe was enough to
    # drop it from the frozen Uşaq list. As an override it is never dropped
    # on a failed probe; the run logs a warning instead.
    "TRTCocuk.tr": {"url": "https://tv-trtcocuk.medya.trt.com.tr/master.m3u8",
                    "quality": "1440p", "user_agent": None, "referrer": None},
    # TRT Belgesel on TRT's own -dai host. Answers 200 with a manifest from
    # Azerbaijan; the runner failed all three candidates the same morning
    # ("404 not found, server error, unreachable"), so the vantage split is
    # measured, not assumed. Quality per iptv-org's label for the channel.
    "TRTBelgesel.tr": {"url": "https://tv-trtbelgesel-dai.medya.trt.com.tr/master.m3u8",
                       "quality": "720p", "user_agent": None, "referrer": None,
                       "expected_fail": True},
}
# A pin is still subject to the host rules: BAD_HOSTS and STREAM_BLOCKLIST
# record streams measured unusable, and "hand-verified" cannot outrank a
# measurement. Anything dropped here is named in the run summary.
override_blocked = []
for _cid, _ov in OVERRIDES.items():
    if not url_allowed(_ov["url"]):
        override_blocked.append(_cid)
        continue
    by[_cid] = [_ov] + by.get(_cid, [])

# Hand-found static candidates for channels iptv-org has no working entry
# for. Probed every run like any other candidate; they simply join the
# playlist the day they start answering. Never tokenized URLs.
# TRT's daioncdn slugs are inconsistent: trt-1 and trtworld both work,
# but trt2/trt-2 and trtbelgesel/trt-belgesel all 404 -- TRT simply does
# not publish those two there. Kept on the unhyphenated form (the shape
# that works for trtworld) so the daily probe keeps trying if that changes.
WATCHLIST = {
    "TRT2.tr": ["https://trt.daioncdn.net/trt2/master.m3u8?app=web"],
    # TRT Belgesel: the -dai host is the one reported working (Nov 2025);
    # both are TRT's own domains. iptv-org's only entry is the plain
    # tv-trtbelgesel.medya host, which is in STREAM_BLOCKLIST (403 from AZ),
    # and the daioncdn slug is one of the ones TRT does not publish.
    # The -dai host is pinned in OVERRIDES now; these two stay as backups.
    "TRTBelgesel.tr": ["https://tv-trtbelgesel.live.trt.com.tr/master.m3u8",
                       "https://trt.daioncdn.net/trtbelgesel/master.m3u8?app=web"],
    # Pluto TV Nature's only iptv-org stream sits on a DACH feed tagged
    # deu, so the language filter drops it before ranking ever sees it.
    # Same jmp2.uk shape as the Pluto entries already carried, with the
    # channel id read off the images.pluto.tv logo URL in iptv-org's data.
    "PlutoTVNature.de": ["https://jmp2.uk/plu-5be1c3f9851dd5632e2c91b2.m3u8"],
    # Documentary+ backup only; the LINEAR-887 feed it publishes on today
    # is healthy, and ranking prefers whichever answers.
    "DocumentaryPlus.us": ["https://ef79b15c8c7c46c7a9de9d33001dbd07.mediatailor.us-west-2.amazonaws.com/v1/master/ba62fe743df0fe93366eba3a257d792884136c7f/LINEAR-859-DOCUMENTARYPLUS-DOCUMENTARYPLUS/mt/documentaryplus/859/hls/master/playlist.m3u8"],
    # Travelxp's official wurl Rakuten-DE playout, as a second candidate
    # behind the Samsung-India one that 403s. Both come from iptv-org's
    # provider files (<country>_<provider>.m3u), where the entries carry
    # no tvg-id at all -- nothing keys them to a channel, so hand-keying
    # here is the only way they can ever be found. The Rakuten-DE feed may
    # carry German audio; pending a verdict once it plays. Earth Touch TV
    # came in the same way and has since been pinned as an OVERRIDE.
    # The Samsung-India playout that used to head this list is in
    # STREAM_BLOCKLIST now: it outranked everything on the runner and 403s
    # from Azerbaijan, so it published as a channel nobody in Baku could watch.
    "Travelxp.in": ["https://travelxp-travelxp-2-de.rakuten.wurl.tv/playlist.m3u8"],
    # Earth Touch TV, demoted from OVERRIDES. Its pin claimed "Baku-verified"
    # but no probe from any vantage ever passed: bare, VLC, Tizen, ExoPlayer,
    # no-User-Agent, and Referer/Origin variants for samsungtvplus, wurl and
    # amagi all returned 403 from Baku, and the runner 403s too. Kept here as
    # the record of the only known URL -- currently INERT, because the
    # samsung-gb BAD_HOSTS rule excludes it. It revives only if that rule is
    # relaxed or the slug family starts answering.
    "EarthTouchTV.za": ["https://amg01823-earthtouch-amg01823c1-samsung-gb-862.playouts.now.amagi.tv/playlist/amg01823-earthtouch-earthtouch-samsunggb/playlist.m3u8"],
    # NatureTime's genuine slugs. The two blocklisted URLs above carry
    # "lovenature-au" in the path: upstream files Love Nature Australia
    # playouts under NatureTime.ca, so ranking kept picking the wrong
    # channel's feed. These two name naturetime and answer from Azerbaijan.
    # ("url", "quality") labels a candidate whose resolution is known from
    # iptv-org but which the probe cannot report; a bare string means unknown.
    "NatureTime.ca": [("https://bamusa-naturetime-emea-eng-rakuten.amagi.tv/playlist.m3u8", "1080p"),
                      "https://amg00090-blueantmedia-naturetime-samsungse-axgcn.amagi.tv/playlist/amg00090-blueantmedia-naturetime-samsungse/playlist.m3u8"],
    # ---- SUBSTITUTES bench, last-known-good URLs -------------------------
    # Bench readiness must not depend on iptv-org churn: a reserve that
    # vanishes upstream would silently stop being able to cover. Each of
    # these is the URL the channel was last published on. Upstream still
    # lists every one of them today, the Pluto/jmp2 ones included, so all
    # of these copies are deduped and latent by design -- they arm only if
    # iptv-org drops the URL. Latent is the intended resting state; do not
    # read a deduped entry as a dead one.
    "BBCEarth.uk": ["https://pb-zjy36qhp8e8cz.akamaized.net/BBC_Earth_US.m3u8"],
    "SmithsonianChannelSelects.us": ["https://jmp2.uk/plu-5f21ea08007a49000762d349.m3u8"],
    # The samsung-gb playout this used to name is in STREAM_BLOCKLIST now
    # (200 for the runner, 403 from Azerbaijan). This rakuten-us playout is
    # the same channel and answers 200 from Azerbaijan. Hand-keyed: the
    # provider file entry carries no tvg-id.
    "CuriosityNOW.de": ["https://amg00170-curiositystream-amg00170c3-rakuten-us-2289.playouts.now.amagi.tv/playlist/amg00170-curiositystreamllcfast-curiositynowrow-rakutenus/playlist.m3u8"],
    "TerraMaterWILD.de": ["https://amg01775-amg01775c1-amgplt0343.playout.now3.amagi.tv/playlist/amg01775-amg01775c1-amgplt0343/playlist.m3u8"],
    "CNAOriginals.sg": ["https://amg01082-cna-amg01082c1-rlaxx-us-11304.playouts.now.amagi.tv/playlist.m3u8"],
    "NHKWorldJapan.jp": ["https://masterpl.hls.nhkworld.jp/hls/w/live/smarttv.m3u8"],
    "WildEarth.za": ["https://dqga3jatxofgx.cloudfront.net/WildEarth.m3u8"],
    "RTDocumentary.ru": ["https://rt-rtd.rttv.com/dvr/rtdoc/playlist.m3u8"],
    "WaterBear.ch": ["https://amg01415-waterbearnetwor-waterbear-samsunguk-1h0y8.amagi.tv/playlist/amg01415-waterbearnetwor-waterbear-samsunguk/playlist.m3u8"],
    "LoveThePlanet.es": ["https://amg01821-lovetv-amg01821c8-xumo-us-3443.playouts.now.amagi.tv/playlist.m3u8"],
    "AutenticHistory.de": ["https://9e754fa707344ccca6d84955c8fcaf36.mediatailor.us-east-1.amazonaws.com/v1/master/44f73ba4d03e9607dcd9bebdcb8494d86964f1d8/RlaxxTV-eu_AutenticHistory/playlist.m3u8"],
    "ChinaTravel.cn": ["https://fastlive.cctvplus.com/out/v1/ca6f9297b7314a63959435028af287fc/index.m3u8"],
    "PlutoTVScience.us": ["https://jmp2.uk/plu-563a970aa1a1f7fe7c9daad7.m3u8"],
    "PlutoTVHistory.de": ["https://jmp2.uk/plu-5d4af1803e7983b391d73b13.m3u8"],
    # ----------------------------------------------------------------------
    # cnnturk.com's own player. 403 from Azerbaijan today while Dream Turk
    # on the same duhnet CDN answers, so it is channel-level geo-blocking,
    # not a dead link -- probed daily so it joins the moment that lifts.
    "CNNTurk.tr": ["https://live.duhnet.tv/S2/HLS_LIVE/cnnturknp/playlist.m3u8"],
    # TRT Cocuk recovery seeds. Its only iptv-org stream is on the medya
    # host that geo-blocks, and TRT's daioncdn slugs are inconsistent
    # (trtworld unhyphenated works, trt-1 hyphenated works), so both
    # spellings are seeded. Both 404 today; probed daily regardless.
    "TRTCocuk.tr": ["https://trt.daioncdn.net/trtcocuk/master.m3u8?app=web",
                    "https://trt.daioncdn.net/trt-cocuk/master.m3u8?app=web"],
    # CNN International has no free official feed: cnn.com gates live behind
    # a TV-provider login and no Pluto/Samsung/Rakuten/Xumo endpoint for it
    # is reachable. It holds position 3 as a waiting pick; add a verified
    # static URL here if one ever appears.
}
# An entry is a bare URL, or ("url", "quality") when the resolution is known
# from iptv-org's label. Quality only affects ranking and the display suffix;
# it is never trusted over a probe, because it is not measured here.
watchlist_live = {}
watchlist_suppressed = []
for _cid, _urls in WATCHLIST.items():
    _known = {s["url"] for s in by.get(_cid, [])}
    for _entry in _urls:
        _u, _q = _entry if isinstance(_entry, tuple) else (_entry, None)
        if not url_allowed(_u):
            # suppressed, not forgotten: named in the run summary so a
            # WATCHLIST line cannot quietly become dead config
            watchlist_suppressed.append((_cid, _u))
            continue
        if looks_tokenized(_u):
            continue
        if _u in _known:
            continue  # iptv-org already carries it; no need to probe twice
        if state["watchlist"].get(_u, {}).get("fails", 0) >= PRUNE_AFTER:
            continue  # pruned: dead for PRUNE_AFTER runs, see run summary
        watchlist_live[_u] = _cid
        by.setdefault(_cid, []).append(
            {"url": _u, "quality": _q, "user_agent": None,
             "referrer": None, "feed": None})

# ---------------------------------------------------------------------
# SOURCE POLICY -- applies to SOURCES and AUTO_RULES alike, and is a hard
# rule, not a preference. Streams may come from exactly two places:
#   1. the iptv-org public database, and
#   2. a broadcaster's own domain (its official live page).
# Never add a scraper for an aggregator, a restream site, an IPTV portal,
# or a third-party playlist dump, however convenient. Legal-only.
# ---------------------------------------------------------------------

# Channel ids that must never be auto-added, whatever AUTO_RULES says.
# Seeded with channels that were deliberately removed by hand, so the
# rules engine cannot quietly undo that curation.
EXCLUDE = {
    # dropped in the first cleanup
    "AyazTV.az", "ELTV.az", "KapazTV.az", "VilayetTV.az", "KNMusicTV.az",
    "TJKTV.tr",
    # dropped in the Turkish music cleanup
    "Number1Damar.tr", "Number1Dance.tr", "PowerDance.tr", "PowerLove.tr",
    # dropped because it 403s from Azerbaijan
    "CBSSportsHQ.us",
    # state broadcasters that backfilled Beynəlxalq Xəbər; seats refill by
    # ranking as usual
    "RT.ru", "RTIndia.in", "Telesur.ve",
    # hand-removed in the per-group policy overhaul; EXCLUDE so neither the
    # İdman/Sənədli rules nor the monthly AZ sweep can ever bring them back
    "AlvinChannelTV.az", "TRTTurk.tr", "HaberturkTV.tr", "BloombergHT.tr",
    "FinansTurkTV.tr", "Haber61TV.tr", "LifeTV.tr", "TRTArabi.tr",
    "TurkHaberTV.tr", "KralPopTV.tr", "MBCFM.ae", "Number1Ask.tr",
    "CNBCe.tr", "GuneydoguTV.tr",
}

# Subscription broadcasters. Never auto-added from any source -- carrying
# them would breach the legal-only rule in the SOURCE POLICY above.
# Matched case-insensitively against the channel name and its network.
# Free-to-air Match! (the main channel) is deliberately absent, so it can
# land in İdman if a stream ever passes; the premium Match! tier is here.
PAY_TV_BLOCK = {
    "bein", "sky sport", "setanta", "eurosport", "discovery", "espn",
    "fox sport", "dazn", "viaplay", "canal+", "supersport", "arena sport",
    "match! futbol", "match! arena", "match! igra", "match! premier",
    "match! ultra", "match! strana", "match! boets", "match! planeta",
    "okko", "khl", "boks tv",
    # same tier, added by judgement
    "premier sport", "sportklub", "polsat sport", "digi sport",
    "nova sport", "tnt sports", "optus sport", "sportsnet", "bt sport",
    "movistar", "orange sport", "telekom sport", "ziggo sport",
    "star sports", "ufc fight pass", "nba league pass", "nfl sunday ticket",
}
# Sports sub-genres that are not what this playlist is for. Sports only.
NICHE_SKIP = re.compile(
    r"college|campus|horse|equestrian|rodeo|poker|billiard|fishing|"
    r"hunting|cornhole|pickleball", re.I)

# Channels the iptv-org database has no entry for at all. Their ids are
# written in the shape iptv-org would use, so upstream data merges
# seamlessly the day the channel is added -- setdefault means the real
# record always wins over this stub. Without the stub, display_name()
# would print the raw id and channels.get(cid) would hand None to code
# that expects a channel record.
LOCAL_CHANNELS = {
    "EarthTouchTV.za":    "Earth Touch TV",
    "DWDocumentary.de":   "DW Documentary",
    "WildNature.ca":      "Wild Nature",
    "PlexDocumentary.us": "Plex Documentary",
}
for _cid, _name in LOCAL_CHANNELS.items():
    channels.setdefault(_cid, {"id": _cid, "name": _name})

# A locked group contains exactly these channels, in exactly this order,
# and AUTO_RULES never touch it. Use it for a group that is curated rather
# than grown -- the ordering is editorial, so nothing may be appended,
# reordered or displaced by ranking.
LOCKED_GROUPS = {
    # Frozen: membership is hand-curated. No AUTO_RULE may add to these,
    # and nothing is reordered or displaced by ranking. Stream healing and
    # waiting-list returns still run daily for every member.
    "Ukrayna": ["FREEDOM.ua", "Pershyi.ua"],
    "Uşaq": ["TRTCocuk.tr", "MinikaCocuk.tr", "MinikaGo.tr",
             "TRTDiyanetCocuk.tr", "Carousel.ru",
             "BabyFirst.us"],                       # promoted from auto
    "· russia": ["ChannelOne.ru", "Russia1.ru", "NTV.ru", "STS.ru",
                 "RENTV.ru", "Che.ru"],
    "Türkiyə – Ümumi": [
        "TRT1.tr", "ATV.tr", "KanalD.tr", "StarTV.tr", "NOWTV.tr", "TV8.tr",
        "Kanal7.tr", "TRTAvaz.tr",
        "ShowTV.tr",        # override: token-free form of its own player URL
        "TV85.tr",          # waiting: no reachable official source exists
        "BeyazTV.tr", "TRT2.tr",                    # waiting upstream
    ],
    "Xəbər – Türkiyə": [
        "TRTHaber.tr", "HaberGlobal.tr", "AHaber.tr", "TGRTHaber.tr",
        "NTV.tr", "24TV.tr", "360.tr", "TVNET.tr", "HalkTV.tr",
        "ASTV.tr", "DHA.tr",                        # promoted from auto
        "CNNTurk.tr",                               # waiting: 403 from AZ
    ],
    "Musiqi": [
        "TRTMuzik.tr", "PowerTurkTV.tr", "Number1TV.tr", "DreamTurk.tr",
        # MBC FM is removed and Musiqi is frozen, so the international seat
        # it held disappears rather than refilling. MTV Biggest Pop is the
        # survivor and becomes a permanent pick.
        "MTVBiggestPop.us",
        "PowerTurkAkustik.tr", "PowerTurkSlow.tr", "PowerTurkTaptaze.tr",
    ],
    "Sənədli": [
        "TRTBelgesel.tr",       # 1  WATCHLIST candidates, probe pending
        "LoveNature.ca",        # 2  live, 2160p
        "EarthTouchTV.za",      # 3  waiting: its only known URL 403s from
                                #    both vantages and rides the excluded
                                #    samsung-gb slug. The bench covers it
        "CGTNDocumentary.cn",   # 4  live
        "DWDocumentary.de",     # 5  waiting: YouTube-only brand, no linear
                                #    feed exists
        "Travelxp.in",          # 6  live on the Rakuten-DE wurl playout;
                                #    the Samsung-India one 403s. Audio
                                #    language pending a user verdict
        "DocumentaryPlus.us",   # 7  live (promoted from auto)
        "AdventureEarth.de",    # 8  live (promoted from auto)
        "Getfactual.us",        # 9  live via Get.factual's Samsung-UK feed
                                #    (its own CloudFront origin), which
                                #    iptv-org carries -- not waiting on any
                                #    Pluto relist
        "WildNature.ca",        # 10 waiting: no reachable feed; identity
                                #    pending user verdict
        "NatureTime.ca",        # 11 live (feed is the Love Nature AU playout
                                #    labelled NatureTime -- user to verify
                                #    the content in VLC)
        "PlutoTVNature.de",     # 12 WATCHLIST candidate, probe pending
        "PlexDocumentary.us",   # 13 waiting: no such linear channel exists;
                                #    pending user verdict
    ],
    "Beynəlxalq Xəbər": [
        "TRTWorld.tr",          # 1
        "BBCNews.uk",           # 2  (override: BBC's own worldwide CDN)
        "CNNInternational.us",  # 3  (waiting: no free official feed found)
        "EuronewsEnglish.fr",   # 4
        "EuronewsRussian.fr",   # 5  (RENAME keeps "russian" lowercase)
        "AlJazeera.qa",         # 6  English feed
        "SkyNews.ie",           # 7  (override: pinned Xumo/NBCU host)
        "France24.fr",          # 8  English feed
        "DW.de",                # 9  English feed
    ],
}

# An ordered bench for a locked group. A locked group publishes exactly its
# members, so a member with no working stream simply leaves the group one
# shorter; SUBSTITUTES lets a named reserve cover that seat without ever
# touching membership. Each run, as many bench channels enter as there are
# hidden members, taken in bench order and skipping any bench channel with
# no working stream of its own. They render AFTER the members, so the
# editorial order of positions 1..N never reshuffles, and they step back on
# the run their cover is no longer needed. A starter never loses its claim
# on its position -- the bench covers, it does not replace.
# Bench channels are stream-hunted exactly like waiting members (daily
# iptv-org refresh plus WATCHLIST probing), so one enters the day a stream
# surfaces. Meant for locked groups; a bench on a grown group would just
# race its own auto-adds.
SUBSTITUTES = {
    # Ranks 1-2 are the two Turkish documentary channels that used to sit
    # in PICKS; both are streamless today (TGRT Belgesel's only known URL
    # is in STREAM_BLOCKLIST, the mediatriple broadcast is gone, and DMAX
    # has no candidate at all), so cover starts at rank 3 in practice.
    # Everything from rank 3 down is a former Sənədli auto-add kept on as
    # a known-good reserve rather than lost when the group was locked.
    "Sənədli": ["TGRTBelgesel.tr", "DMAX.tr", "BBCEarth.uk",
                "SmithsonianChannelSelects.us", "CuriosityNOW.de",
                "TerraMaterWILD.de", "CNAOriginals.sg", "NHKWorldJapan.jp",
                "WildEarth.za", "RTDocumentary.ru", "WaterBear.ch",
                "LoveThePlanet.es", "AutenticHistory.de", "ChinaTravel.cn",
                "PlutoTVScience.us", "PlutoTVHistory.de"],
}
bench_ids = {cid for _bench in SUBSTITUTES.values() for cid in _bench}

# Ceiling on auto-adds per group. PICKS entries never count against a cap
# and are never displaced -- caps only trim the automatic tail. Groups
# absent from this dict are uncapped.
AUTO_CAP = {"İdman": 40}
# Azərbaycan is deliberately uncapped: its sweep is monthly and additive,
# so there is no tail to trim.
# Hard ceiling on the whole playlist. Auto-adds are trimmed lowest-rank
# first to stay under it; PICKS entries and OVERRIDES are never trimmed.
TOTAL_MAX = 199
# An incumbent auto-add keeps its slot until it has failed this many runs
# in a row, so a single bad probe does not churn the playlist.
STICKY_FAILS = 2

def categories_of(c):
    return {x.lower() for x in (c.get("categories") or [])}

def is_international(cid):
    areas = chan_areas.get(cid, set())
    return (any(a.startswith("r/") for a in areas)
            or len([a for a in areas if a.startswith("c/")]) > 1)

def reach_score(cid):
    """Region-wide > multi-country > one country > local."""
    areas = chan_areas.get(cid, set())
    if any(a.startswith("r/") for a in areas):
        return 3
    countries = [a for a in areas if a.startswith("c/")]
    if len(countries) > 1:
        return 2
    return 1 if countries else 0

def notable(cid, c):
    """Reject local stations, closed channels and NSFW. A feed whose
    broadcast_area is only city (ct/) or subdivision (s/) level is below
    country level. An unknown area is not held against a channel."""
    if c.get("closed") or c.get("is_nsfw"):
        return False
    areas = chan_areas.get(cid, set())
    if not areas:
        return True
    return any(a.startswith(("c/", "r/")) for a in areas)

def is_pay_tv(cid, c):
    hay = f"{c.get('name') or ''} {c.get('network') or ''}".lower()
    return any(tok in hay for tok in PAY_TV_BLOCK)

# Evaluated against the whole iptv-org database every run. First match
# wins, so the country-specific rules are listed before the broad
# catch-alls -- otherwise the later rules could never fire.
AUTO_RULES = [
    ("İdman",           lambda cid, c, L: "sports" in categories_of(c)),
    # Sənədli used to have a rule here; the group is locked now, so it is
    # curated by hand and the rules engine has no route into it.
    # The only remaining route for a genuinely new channel outside İdman.
    # Runs monthly, not daily -- see AZ_SWEEP_DAYS. EXCLUDE always wins,
    # so a hand-removed Azerbaijani channel can never come back.
    ("Azərbaycan 🇦🇿",   lambda cid, c, L: c.get("country") == "AZ"),
]
AZ_SWEEP_GROUP = "Azərbaycan 🇦🇿"
AZ_SWEEP_DAYS = 28        # minimum days between new-channel sweeps

# Probing every stream of every matching channel would dominate the run,
# so only this many best-ranked streams per auto-candidate are checked.
AUTO_PROBE_PER_CHANNEL = 2

def latin_only(name):
    """True if every letter is Latin (Azerbaijani/Turkish diacritics pass,
    Cyrillic/Greek/Arabic/CJK do not)."""
    for ch in name:
        if ch.isalpha():
            try:
                if not unicodedata.name(ch).startswith("LATIN"):
                    return False
            except ValueError:
                return False
    return True

def auto_group_for(cid, c):
    L = chan_langs.get(cid, set())
    for group, pred in AUTO_RULES:
        if group in LOCKED_GROUPS:
            continue          # locked groups are curated, never grown
        try:
            if pred(cid, c, L):
                return group
        except Exception:
            continue
    return None

# Broadcasters' own live pages, scraped daily for static .m3u8 URLs.
# Official domains ONLY -- see SOURCE POLICY above.
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
            "bloomberg.com", "nhkworld.jp", "cgtn.com", "cosmonova",
            "nbcuni.com"]
# Shapes that correlate with restreams and leaked origins. Report-only: this
# names candidates for a HUMAN legality ruling and blocks nothing by itself,
# because provenance is a judgement no probe can make. A ruling is enforced by
# adding to STREAM_BLOCKLIST or BAD_HOSTS, after which the URL stops being a
# candidate at all and drops off this list.
SUSPECT_TLDS = (".lol", ".xyz", ".icu", ".sbs")

def suspect_reason(url):
    """Why this URL deserves a human look, or None."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "unparsable URL"
    host = (parts.hostname or "").lower()
    if host.endswith(SUSPECT_TLDS):
        return f".{host.rsplit('.', 1)[-1]} TLD"
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
        return "bare IP host"
    # startswith, not "in": FAST manifests are full of /latest/ segments, and
    # matching those buries the real hits. The leaks seen so far all begin the
    # segment with test -- test_docubox_medium_atk, test_uatv, test_bbc_world.
    if any(seg.lower().startswith("test") for seg in parts.path.split("/") if seg):
        return "'test' path segment"
    return None

def qscore(s):
    q = s.get("quality") or ""
    try: return int(q.replace("p", "").replace("i", ""))
    except ValueError: return 0
def rank(s):
    # Baku's measured verdict outranks provenance and resolution both: a
    # stream the viewer cannot open is worth less than a lower-quality one
    # they can. This is also what breaks the iptv-org-before-WATCHLIST tie
    # that used to publish a geo-blocked feed over a working alternate.
    # 0 means never measured here, never "measured a while ago".
    return (baku_pref.get(s["url"], 0),
            any(d in s["url"] for d in OFFICIAL), qscore(s))

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
# Azərbaycan is NOT frozen: it is the one group still open to new channels,
# via the monthly AZ sweep below. Alvin is in EXCLUDE so it cannot return.
"Azərbaycan 🇦🇿": ["AzTV.az","IctimaiTV.az","XezerTV.az","CBCSport.az","IdmanTV.az","BakuTV.az","APATv.az","AnewZTV.az","MedeniyyetTV.az","KanalS.az","Kanal35.az","NaxcivanTV.az","GunAzTV.us","AzStarTV.ca","SpaceTV.az","ARB24.az","ARBGunes.az","StartTV.az","AzadTV.az","ARB.az"],
"Ukrayna": LOCKED_GROUPS["Ukrayna"],
"Türkiyə – Ümumi": LOCKED_GROUPS["Türkiyə – Ümumi"],
"Xəbər – Türkiyə": LOCKED_GROUPS["Xəbər – Türkiyə"],
"İdman": ["CBCSport.az","IdmanTV.az","ASpor.tr","TRT3.tr","TRTSporYildiz.tr","HTSporTV.tr","FBTV.tr","RedBullTV.at","beINSPORTSXTRA.us","FIFAPlus.uk","CBSSportsGolazoNetwork.us","Stadium.us","FuboSportsNetwork.us","Unbeaten.us","Futbol.tj","FutbolTV.uz","UzReportTV.uz","QazSport.kz","M4Sport.hu","Teledeporte.es","OlympicChannel.es"],
"Uşaq": LOCKED_GROUPS["Uşaq"],
"Musiqi": LOCKED_GROUPS["Musiqi"],
"Sənədli": LOCKED_GROUPS["Sənədli"],
"· russia": LOCKED_GROUPS["· russia"],
"Beynəlxalq Xəbər": LOCKED_GROUPS["Beynəlxalq Xəbər"],
}
# Streamless ids (IdmanTV, AzadTV, ARB, SpaceTV, ARB24, ARBGunes,
# StartTV...) are kept on purpose: they join automatically the day a
# working stream appears, and are listed in WAITING.md meanwhile. The
# same is true of the SUBSTITUTES bench, which is probed alongside them.
# CBCSport/IdmanTV are dual-grouped on purpose (Azərbaycan + İdman).

RENAME = {"Russia1.ru": "russia 1", "EuronewsRussian.fr": "Euronews russian",
          # carried under the Paris L'Original feed; keep the plain name
          "FashionTVParisLOriginal.fr": "Fashion TV"}

def display_name(cid):
    name = RENAME.get(cid) or (channels.get(cid) or {}).get("name") or cid
    # hard rule: the words russia/russian never appear capitalised, whether
    # the entry is hand-picked or auto-added
    return re.sub(r"Russia", "russia", name)

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
    cid, name, opts, grp = None, "", [], ""
    for line in raw:
        if line.startswith("#EXTINF"):
            m = re.search(r'tvg-id="([^"]*)"', line)
            cid = m.group(1) if m else None
            g = re.search(r'group-title="([^"]*)"', line)
            grp = g.group(1) if g else ""
            name = line.split(",", 1)[1] if "," in line else ""
            opts = []
        elif line.startswith("#EXTVLCOPT"):
            opts.append(line)
        elif line and not line.startswith("#"):
            # first occurrence wins (dual-grouped ids repeat). Retention
            # honours BAD_HOSTS and STREAM_BLOCKLIST too, so a banned host
            # can never be reinstated by last-known-good.
            if cid and url_allowed(line):
                prev.setdefault(cid, {"name": name, "opts": opts,
                                      "url": line, "group": grp})
            cid, name, opts, grp = None, "", [], ""
    return prev

def load_auto_state(path=AUTO_STATE_FILE):
    """{"incumbents": {cid: {...}}, "last_az_discovery": "YYYY-MM-DD"}"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        inc = (data or {}).get("incumbents") or {}
        return {"incumbents": {c: {"group": (v or {}).get("group", ""),
                                   "fails": int((v or {}).get("fails", 0) or 0)}
                               for c, v in inc.items() if isinstance(v, dict)},
                "last_az_discovery": (data or {}).get("last_az_discovery") or ""}
    except (FileNotFoundError, ValueError):
        return {"incumbents": {}, "last_az_discovery": ""}

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

# ---------------- probe everything ----------------
skip_check = os.environ.get("SKIP_CHECK") == "1"
TODAY = datetime.date.today()
all_ids = {cid for idl in PICKS.values() for cid in idl}
# Bench channels are not playlist members, but they are hunted for streams
# exactly like waiting members so a substitute can enter the day one
# surfaces. Everything that probes or retains works off this set.
probe_ids = all_ids | bench_ids
previous = load_previous()
prev_waiting_names = load_prev_waiting()

discovery_log = []
discovered = {c: dict(m) for c, m in state["discovered"].items()}
if not skip_check:
    for _cid, _urlmap in discover(discovery_log).items():
        for _u, _page in _urlmap.items():
            discovered.setdefault(_cid, {}).setdefault(_u, {"page": _page, "fails": 0})
            discovered[_cid][_u]["page"] = _page
# stale entries can be retired by the blocklist just like anything else
discovered = {c: {u: e for u, e in m.items()
                  if url_allowed(u) and not looks_tokenized(u)}
              for c, m in discovered.items()}
discovered = {c: m for c, m in discovered.items() if m}

disc_by = {}
for _cid, _urlmap in discovered.items():
    for _u in sorted(_urlmap):
        disc_by.setdefault(_cid, []).append(
            {"url": _u, "quality": None, "user_agent": None,
             "referrer": None, "feed": None})

# ---- auto-include candidates (PICKS always wins; these only ever add) ----
skip_paytv, skip_gate, skip_niche, skip_script = 0, 0, 0, 0

def auto_eligible_group(cid, count=False):
    """The group this channel would be auto-added to, or None if any gate
    rejects it. Gates are identical for newcomers and incumbents."""
    global skip_paytv, skip_gate, skip_niche, skip_script
    c = channels.get(cid)
    if c is None or cid in probe_ids or cid in EXCLUDE:
        return None
    group = auto_group_for(cid, c)
    if group is None:
        return None
    if is_pay_tv(cid, c):
        if count: skip_paytv += 1
        return None
    if not notable(cid, c):
        if count: skip_gate += 1
        return None
    if group == "İdman" and NICHE_SKIP.search(c.get("name") or ""):
        if count: skip_niche += 1
        return None
    if not latin_only(c.get("name") or ""):
        if count: skip_script += 1
        return None
    return group

auto_candidates = {}   # cid -> (group, [streams to probe])
for _cid in channels:
    _pool = [s for s in by.get(_cid, []) if url_allowed(s["url"])]
    if not _pool:
        continue
    _group = auto_eligible_group(_cid, count=True)
    if _group is None:
        continue
    _pool = sorted(_pool, key=rank, reverse=True)[:AUTO_PROBE_PER_CHANNEL]
    auto_candidates[_cid] = (_group, _pool)

# Retained URLs are probed as well: a last-known-good entry must not
# outlive the stream it points at.
prev_streams = {
    cid: {"url": p["url"], "feed": None,
          "user_agent": opt_value(p["opts"], "#EXTVLCOPT:http-user-agent"),
          "referrer": opt_value(p["opts"], "#EXTVLCOPT:http-referrer")}
    for cid, p in previous.items() if cid in probe_ids}

candidates = []
for cid in probe_ids:
    candidates.extend(by.get(cid, []))
    candidates.extend(disc_by.get(cid, []))
candidates.extend(prev_streams.values())
for _group, _pool in auto_candidates.values():
    candidates.extend(_pool)
status, detail_of = {}, {}
override_warnings = []   # pinned despite an unexpected probe failure
override_expected = []   # pinned, flagged expected_fail: known vantage noise
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
    if ov is not None and url_allowed(ov["url"]):
        _det = status.get(skey(ov), "unprobed")
        (override_expected if ov.get("expected_fail")
         else override_warnings).append(f"{cid} (probe={_det})")
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

# Resolve auto-adds: a rule match only becomes an entry if one of its
# streams actually passes the probe.
auto_state = load_auto_state()
incumbents = auto_state["incumbents"]
# New-channel discovery for Azərbaycan is monthly. Everything else about
# that group -- stream healing, retention, WAITING.md probing, and the daily
# SOURCES scrape for channels already waiting -- stays on the daily cycle.
try:
    _last_az = datetime.date.fromisoformat(auto_state.get("last_az_discovery") or "")
except ValueError:
    _last_az = None
az_sweep_active = _last_az is None or (TODAY - _last_az).days >= AZ_SWEEP_DAYS
# On an active run the state is restamped to today, so the next window is
# today + AZ_SWEEP_DAYS -- not today, which is the window just consumed.
next_az_discovery = ((TODAY if az_sweep_active else _last_az)
                     + datetime.timedelta(days=AZ_SWEEP_DAYS))
# First ever run: seed incumbency from whatever the published playlist
# already carries that PICKS does not account for.
if not incumbents:
    for _cid, _p in previous.items():
        if _cid not in all_ids:
            incumbents[_cid] = {"group": _p.get("group", ""), "fails": 0}

eligible = {}          # cid -> (group, stream) - passed gates AND probe
for _cid, (_group, _pool) in auto_candidates.items():
    _hit = _pick(_pool) if not skip_check else (_pool[0] if _pool else None)
    if _hit is not None:
        eligible[_cid] = (_group, _hit)

def auto_rank_key(cid, stream=None):
    return (-reach_score(cid),
            -max(chan_format.get(cid, 0), qscore(stream) if stream else 0),
            display_name(cid).lower())

# ---- sticky incumbents: hold the slot unless something really changed ----
auto_add = {}          # cid -> (group, stream or None => retain previous url)
vacated = []
for _cid in sorted(incumbents):
    _st = incumbents[_cid]
    _group = auto_eligible_group(_cid)
    if _group is None:
        vacated.append((_cid, "no longer matches a rule / excluded"))
        del incumbents[_cid]
        continue
    if _cid in eligible:
        _st.update(group=_group, fails=0)
        auto_add[_cid] = (_group, eligible[_cid][1])
        continue
    _st["fails"] = int(_st.get("fails", 0)) + 1
    if _st["fails"] >= STICKY_FAILS:
        vacated.append((_cid, f"failed {_st['fails']} consecutive runs"))
        del incumbents[_cid]
    elif _cid in previous and url_allowed(previous[_cid]["url"]):
        _st["group"] = _group
        auto_add[_cid] = (_group, None)   # hold the slot on last-known-good
    else:
        vacated.append((_cid, "failed with no previous URL to hold"))
        del incumbents[_cid]

# ---- newcomers fill whatever room the caps leave ----
capped_out = 0
for _group in sorted({g for g, _ in eligible.values()}):
    _held = [c for c, (g, _s) in auto_add.items() if g == _group]
    _cap = AUTO_CAP.get(_group)
    if _cap is not None and len(_held) > _cap:      # cap was lowered
        _held.sort(key=lambda c: auto_rank_key(c, (eligible.get(c) or (None, None))[1]))
        for _cid in _held[_cap:]:
            vacated.append((_cid, f"over the {_group} cap of {_cap}"))
            auto_add.pop(_cid, None)
            incumbents.pop(_cid, None)
            capped_out += 1
        _held = _held[:_cap]
    _room = None if _cap is None else max(0, _cap - len(_held))
    _new = [(c, s) for c, (g, s) in eligible.items()
            if g == _group and c not in auto_add]
    if _group == AZ_SWEEP_GROUP and not az_sweep_active:
        _new = []      # monthly sweep dormant; incumbents still hold slots
    _new.sort(key=lambda r: auto_rank_key(r[0], r[1]))
    if _room is not None and len(_new) > _room:
        capped_out += len(_new) - _room
        _new = _new[:_room]
    for _cid, _hit in _new:
        auto_add[_cid] = (_group, _hit)
        incumbents[_cid] = {"group": _group, "fails": 0}

def rebuild_auto_by_group():
    out = {}
    for cid, (g, _s) in auto_add.items():
        out.setdefault(g, []).append(cid)
    for g in out:
        out[g].sort(key=lambda c: display_name(c).lower())
    return out

auto_by_group = rebuild_auto_by_group()

# ---------------- build the playlist ----------------
# Pass 1 renders the hand-curated entries so the global ceiling knows how
# many slots PICKS actually occupies; pass 2 appends the auto-adds.
picks_lines = {}
count = 0
published = set()
published_urls = set()
adopted = {}   # cid -> page it was discovered on
retained, stale, no_stream, unknown_id = [], [], [], []
bench_rows = []       # (cid, group, bench rank, state) for the report
substituted = {}      # group -> bench ids standing in this run
hidden_members = {}   # group -> members that published nothing this run

def entry_for(cid):
    """Resolve one hand-curated entry to ((name, opts, url), source), or
    (None, reason) when there is nothing to publish. Deliberately free of
    side effects -- the caller records the diagnostics, so a bench channel
    can be tested for readiness without polluting the pick-level reports."""
    best = best_working(cid)
    prev = previous.get(cid)
    if best is not None and cid in channels:
        q = best.get("quality")
        opts = []
        if best.get("user_agent"):
            opts.append(f'#EXTVLCOPT:http-user-agent={best["user_agent"]}')
        if best.get("referrer"):
            opts.append(f'#EXTVLCOPT:http-referrer={best["referrer"]}')
        return (display_name(cid) + (f" ({q})" if q else ""),
                opts, best["url"]), "live"
    if prev and retained_usable(cid):
        # last-known-good, and it still answers: keep the channel
        return (prev["name"], prev["opts"], prev["url"]), "retained"
    if prev:
        return None, "stale"          # retained URL went dead -> hide it
    if cid not in channels:
        return None, "unknown id"
    return None, ("no stream" if (by.get(cid) or disc_by.get(cid))
                  else "no candidates")

def emit(group, cid, fields, source):
    """Append one resolved entry to a group's hand-curated block."""
    disp, opts, url = fields
    if source == "retained":
        retained.append(cid)
    if cid in discovered and url in discovered[cid]:
        adopted[cid] = discovered[cid][url]
    picks_lines.setdefault(group, []).append(
        f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logos.get(cid,"")}" '
        f'group-title="{group}",{disp}')
    picks_lines[group].extend(opts)
    picks_lines[group].append(url)
    published.add(cid)
    published_urls.add(url)

for group, idl in PICKS.items():
    placed = 0
    for cid in idl:
        fields, source = entry_for(cid)
        if fields is None:
            if source == "stale":
                stale.append(cid)
            elif source == "unknown id":
                unknown_id.append(cid)
            elif source == "no stream":
                no_stream.append(cid)
            continue
        emit(group, cid, fields, source)
        count += 1
        placed += 1
    # ---- substitutes: cover hidden members, never displace them ----------
    # One seat per member that published nothing this run, filled in bench
    # order and rendered after the members, so positions 1..N never move.
    # The seat is held only while the cover is needed.
    seats = len(idl) - placed
    hidden_members[group] = seats
    # A substitute exists for exactly one reason: to give the viewer
    # something watchable in a seat that would otherwise be empty. So a seat
    # requires BOTH that the runner's probe passes this run AND that Baku has
    # a pass on record for that same URL, at any age. A recorded fail blocks
    # the seat until a newer pass replaces it, and never-measured does not
    # seat -- a stream nobody in Baku has opened is a hope, not a substitute.
    # The seat
    # falls through to the next rank meeting both. Starters are untouched:
    # editorial picks publish best-effort, with BAKU steering only which of
    # their URLs is chosen, through ranking.
    for pos, cid in enumerate(SUBSTITUTES.get(group, []), 1):
        fields, source = entry_for(cid)
        if fields is None:
            bench_rows.append((cid, group, pos, "streamless"))
        elif baku_verdict(fields[2]) is not True:
            bench_rows.append((cid, group, pos, "gated"))
        elif seats <= 0 or cid in published:
            bench_rows.append((cid, group, pos, "ready"))
        else:
            emit(group, cid, fields, source)
            count += 1
            seats -= 1
            substituted.setdefault(group, []).append(cid)
            bench_rows.append((cid, group, pos, "in play"))

# ---- global ceiling: trim lowest-ranked auto-adds, never PICKS ----
picks_count = count
trimmed = []
if TOTAL_MAX is not None:
    worst_first = sorted(auto_add, key=lambda c: auto_rank_key(
        c, (eligible.get(c) or (None, None))[1]), reverse=True)
    while worst_first and (picks_count + len(auto_add)) > TOTAL_MAX:
        cid = worst_first.pop(0)
        trimmed.append(cid)
        auto_add.pop(cid, None)
        incumbents.pop(cid, None)
    auto_by_group = rebuild_auto_by_group()

# ---- pass 2: assemble, auto-adds after the hand-curated entries ----
lines = ["#EXTM3U"]
for group in PICKS:
    lines.extend(picks_lines.get(group, []))
    for cid in auto_by_group.get(group, []):
        best = auto_add[cid][1]
        if best is None:                       # incumbent held on last-known-good
            p = previous.get(cid)
            if p is None:
                continue
            disp, opts, url = p["name"], p["opts"], p["url"]
        else:
            q = best.get("quality")
            disp = display_name(cid) + (f" ({q})" if q else "")
            opts = []
            if best.get("user_agent"):
                opts.append(f'#EXTVLCOPT:http-user-agent={best["user_agent"]}')
            if best.get("referrer"):
                opts.append(f'#EXTVLCOPT:http-referrer={best["referrer"]}')
            url = best["url"]
        if url in published_urls:   # dedupe: same stream already carried
            continue
        lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logos.get(cid,"")}" '
                     f'group-title="{group}",{disp}')
        lines.extend(opts)
        lines.append(url)
        published.add(cid)
        published_urls.add(url)
        count += 1

if WRITE:
    with open(PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"OK: {count} channels written")
else:
    print(f"PREVIEW: {count} channels (nothing written -- only the GitHub "
          f"runner writes these files; pass --write to override)")

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

def bench_status_text(cid, state):
    """A bench channel reads like the waiting members it sits alongside, so
    a streamless one borrows the waiting list's own reason."""
    if state == "streamless":
        return f"streamless - {candidate_summary(cid)[1]}"
    if state == "gated":
        # named precisely: a recorded fail needs a new URL, a never-measured
        # one only needs a local run to look at it
        fields, _src = entry_for(cid)
        why = ("failed here" if fields and baku_verdict(fields[2]) is False
               else "never measured here")
        return f"runner-alive, no Baku pass on record ({why})"
    if state == "ready":
        return "ready - no seat needed this run"
    return "in play - covering a hidden member"

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

auto_rows = sorted(
    ((display_name(cid), grp, cid) for cid, (grp, _s) in auto_add.items()
     if cid in published),
    key=lambda r: r[0].lower())
# auto-adds that were not in the previous playlist -> named in the commit
new_auto = [r for r in auto_rows if r[2] not in previous]

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
    out += ["", "## Substitutes", "",
            "The bench for a locked group. One substitute enters for each",
            "member with no working stream, in bench order, and steps back",
            "when the member returns. Membership and the editorial order of",
            "the group itself never change.", ""]
    if bench_rows:
        out += ["| Substitute | Group | Bench rank | Status |",
                "| --- | --- | --- | --- |"]
        out += [f"| {display_name(c)} | {g} | {p} | {bench_status_text(c, s)} |"
                for c, g, p, s in bench_rows]
    else:
        out.append("_None._")
    out += ["", "## Alternates found", "",
            "Working streams found on a broadcaster's own site for channels",
            "that are already live. Listed only; never swapped in.", ""]
    if alternate_rows:
        out += ["| Channel | Group | Alternate URL | Found on |",
                "| --- | --- | --- | --- |"]
        out += [f"| {c} | {g} | {u} | {p} |" for c, g, u, p in alternate_rows]
    else:
        out.append("_None._")
    out += ["", "## New channels", "",
            "Added automatically by AUTO_RULES from the iptv-org database,",
            "not hand-picked. To drop one for good, add its id to EXCLUDE",
            "in `generate_playlist.py`.", ""]
    if auto_rows:
        out += ["| Channel | Group | Channel id |", "| --- | --- | --- |"]
        out += [f"| {n} | {g} | `{i}` |" for n, g, i in auto_rows]
    else:
        out.append("_None._")
    return "\n".join(out) + "\n"

report_text = render_report()
if WRITE:
    with open(WAITING_FILE, "w", encoding="utf-8") as f:
        f.write(report_text)

# ---------------- prune candidates that have been dead for ages ----------
pruned = []
if not skip_check:
    for _cid, _m in list(discovered.items()):
        for _u, _entry in list(_m.items()):
            if status.get((None, _u)) in ("ok", "geo"):
                _entry["fails"] = 0
                continue
            _entry["fails"] = int(_entry.get("fails", 0)) + 1
            if _entry["fails"] >= PRUNE_AFTER:
                del _m[_u]
                pruned.append(f"discovered {display_name(_cid)}: {_u}")
        if not _m:
            del discovered[_cid]
    for _u, _cid in watchlist_live.items():
        _e = state["watchlist"].setdefault(_u, {"fails": 0})
        if status.get((None, _u)) in ("ok", "geo"):
            _e["fails"] = 0
            continue
        _e["fails"] = int(_e.get("fails", 0)) + 1
        if _e["fails"] >= PRUNE_AFTER:
            pruned.append(f"watchlist {display_name(_cid)}: {_u} "
                          f"(now inert; delete the line from WATCHLIST)")

if WRITE:
    with open(DISCOVERED_FILE, "w", encoding="utf-8") as f:
        json.dump({"discovered": {c: dict(sorted(m.items()))
                                  for c, m in sorted(discovered.items())},
                   "watchlist": dict(sorted(state["watchlist"].items()))},
                  f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(AUTO_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"incumbents": {c: incumbents[c] for c in sorted(incumbents)},
                   "last_az_discovery": (TODAY.isoformat() if az_sweep_active
                                         else (auto_state.get("last_az_discovery") or ""))},
                  f, indent=2, ensure_ascii=False)
        f.write("\n")

# ---------------- Baku vantage data --------------------------------------
# The one file a local run writes and the runner never does: only this
# machine sits in Baku, so only it can answer "is this watchable". Committed
# from here like code. "geo" is not a verdict, so it is not recorded.
baku_measured = {}
if not IS_CI and not skip_check:
    for (_feed, _u), _st in status.items():
        if _st == "geo":
            continue
        baku_measured[_u] = baku_measured.get(_u, False) or (_st == "ok")
    _merged = dict(baku_raw)
    _merged.update({_u: {"ok": _ok, "ts": TODAY.isoformat()}
                    for _u, _ok in baku_measured.items()})
    with open(BAKU_FILE, "w", encoding="utf-8") as f:
        json.dump({u: _merged[u] for u in sorted(_merged)}, f,
                  indent=2, ensure_ascii=False)
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
# A channel that moved from the waiting table onto the SUBSTITUTES bench
# leaves new_waiting_names without having gained a stream, and would read as
# "is back". Bench members are reported in their own table, never here.
bench_names = {display_name(c) for c, _g, _p, _s in bench_rows}
returned = sorted(prev_waiting_names - new_waiting_names - bench_names)
parts, detail = [], []
if new_auto:
    names = ", ".join(r[0] for r in new_auto[:4])
    if len(new_auto) > 4:
        names += f", +{len(new_auto) - 4} more"
    parts.append(f"+{len(new_auto)} new ({names})")
for cid, page in sorted(adopted.items(), key=lambda kv: display_name(kv[0]).lower()):
    host = urllib.parse.urlsplit(page).hostname or page
    parts.append(f"discovered {display_name(cid)} on {host}")
    returned = [r for r in returned if r != display_name(cid)]
if returned:
    parts.append(f"{', '.join(returned)} {'is' if len(returned) == 1 else 'are'} back")
if pruned:
    parts.append(f"pruned {len(pruned)} dead candidate"
                 f"{'' if len(pruned) == 1 else 's'}")
    detail = ["", "Pruned:"] + [f"  {p}" for p in pruned]
if trimmed:
    parts.append(f"trimmed {len(trimmed)} over the {TOTAL_MAX} ceiling")
headline = "bot: " + ", ".join(parts) if parts else "Auto-update playlist"
if WRITE:
    with open(COMMIT_MSG_FILE, "w", encoding="utf-8") as f:
        f.write(headline + "\n")
        if detail:
            f.write("\n".join(detail) + "\n")

# ---------------- console report ----------------
def report(label, ids):
    if ids:
        print(f"{label}:", ", ".join(sorted(set(ids))))
report("Retained last-known-good (no working stream this run)", retained)
report("Dropped (last-known-good URL no longer responds)", stale)
report("Dropped (no working stream and no previous entry)", no_stream)
report("Skipped (id not in channels.json)", unknown_id)
report("WARNING: override kept despite failed probe", override_warnings)
report("Override kept (expected vantage-fail, verified from Baku)",
       override_expected)
# A flagged override that starts passing ON THE RUNNER means the flag has
# gone stale. Only the runner can tell: expected_fail marks a stream that
# works from Baku, so on a local preview it passes by definition and the
# check would fire every single run.
report("NOTE: expected_fail override now passes the runner's probe (flag is stale)",
       [c for c, o in OVERRIDES.items() if IS_CI and o.get("expected_fail")
        and status.get(skey(o)) == "ok"])
report("Blocklisted (only stream(s) removed by STREAM_BLOCKLIST)",
       [cid for cid in probe_ids if cid in blocked_ids
        and not by.get(cid) and not disc_by.get(cid)])
if discovery_log:
    print("Discovery:")
    for line in discovery_log:
        print(line)
print(f"Waiting list: {len(waiting_rows)} channel(s); "
      f"alternates found: {len(alternate_rows)}")
print(f"Auto-added by AUTO_RULES: {len(auto_rows)} channel(s) "
      f"({len(new_auto)} new this run)")
_per_group = {}
for _n, _g, _i in auto_rows:
    _per_group[_g] = _per_group.get(_g, 0) + 1
for _g in sorted(_per_group, key=lambda k: -_per_group[k]):
    cap = AUTO_CAP.get(_g)
    print(f"    {_g:20} {_per_group[_g]}{f' / cap {cap}' if cap else ''}")
for _n, _g, _i in auto_rows:
    print(f"  + {_i:34} {_n[:36]:36} -> {_g}")
print(f"AZ new-channel sweep: {'ACTIVE today' if az_sweep_active else 'dormant'}; "
      f"next AZ discovery: {next_az_discovery.isoformat()}")
print(f"Frozen groups: {len(LOCKED_GROUPS)}; machine-managed: İdman")
for _g, _bench in SUBSTITUTES.items():
    _act = substituted.get(_g, [])
    print(f"Substitutes {_g}: {len(_act)} of {len(_bench)} in play; "
          f"{hidden_members.get(_g, 0)} member(s) hidden")
    for _c, _bg, _pos, _st in bench_rows:
        if _bg == _g:
            print(f"    {_pos}. {display_name(_c)[:28]:28} "
                  f"{bench_status_text(_c, _st)}")
print(f"Overrides: {len(OVERRIDES)} pinned; {len(override_expected)} expected "
      f"vantage-fail, {len(override_warnings)} unexpected failure(s)")
if override_blocked:
    print(f"Overrides dropped by a host rule / blocklist: "
          f"{', '.join(sorted(override_blocked))}")
if watchlist_suppressed:
    print(f"WATCHLIST URLs suppressed by a host rule ({len(watchlist_suppressed)}):")
    for _c, _u in watchlist_suppressed:
        print(f"  - {display_name(_c)}: {_u[:88]}")
# ---- suspicious hosts: named for a human ruling, never acted on ----------
# Everything a channel of ours could publish is scanned, including auto-add
# pools. A URL already ruled on is gone from the pools by then, so this list
# is exactly the set still awaiting judgement.
_pools = {c: by.get(c, []) + disc_by.get(c, []) for c in probe_ids}
for _c, (_g, _pl) in auto_candidates.items():
    _pools.setdefault(_c, []).extend(_pl)
suspect_rows, _seen_sus = [], set()
for _c in sorted(_pools, key=lambda c: display_name(c).lower()):
    for _s in _pools[_c]:
        _why = suspect_reason(_s["url"])
        if _why and (_c, _s["url"]) not in _seen_sus:
            _seen_sus.add((_c, _s["url"]))
            suspect_rows.append((display_name(_c), _why, _s["url"],
                                 _s["url"] in published_urls))
if suspect_rows:
    _pub = sum(1 for r in suspect_rows if r[3])
    print(f"Suspicious hosts awaiting a human legality ruling "
          f"({len(suspect_rows)}; {_pub} currently published). A Baku pass "
          f"proves watchability, not legitimacy:")
    for _n2, _why, _u, _isp in sorted(suspect_rows, key=lambda r: (not r[3], r[0])):
        print(f"  {'PUBLISHED' if _isp else 'candidate':10} {_n2[:26]:26} "
              f"[{_why}] {_u[:74]}")

_ok = sum(1 for v in baku_pref.values() if v > 0)
print(f"Baku vantage: {len(baku_raw)} URL(s) on record ({_ok} pass, "
      f"{len(baku_raw) - _ok} fail), all biasing rank -- no expiry"
      + (f"; {len(baku_measured)} measured this run -> {BAKU_FILE}"
         if baku_measured else ""))
print(f"Skipped: pay-TV {skip_paytv}, below country level / closed / nsfw "
      f"{skip_gate}, niche sports {skip_niche}, non-Latin name {skip_script}, "
      f"over cap {capped_out}")
_tag = "" if WRITE else f"   <- {PREVIEW_NOTE}"
print(f"Total {count} / ceiling {TOTAL_MAX} "
      f"({picks_count} from PICKS, {len(auto_add)} auto){_tag}")
# entries != channels: CBC Sport and Idman TV are dual-grouped on purpose,
# so a count keyed by channel id reads one lower per duplicated channel.
_dupes = count - len(published)
print(f"Entries {count} = {len(published)} unique channels"
      + (f" + {_dupes} dual-grouped repeat(s)" if _dupes else ""))
if vacated:
    print(f"Vacated {len(vacated)} auto-slot(s):")
    for _cid, _why in vacated:
        print(f"  - {display_name(_cid)} ({_cid}): {_why}")
if trimmed:
    print(f"Trimmed {len(trimmed)} over the {TOTAL_MAX} ceiling "
          f"(lowest rank first):")
    for _cid in trimmed:
        print(f"  - {display_name(_cid)} ({_cid})")
if pruned:
    print(f"Pruned {len(pruned)} dead candidate(s):")
    for p in pruned:
        print(f"  - {p}")

preview_banner()
