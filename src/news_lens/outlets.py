"""Static lookup of well-known news outlets.

Friendly names, country, outlet type, a political-lean rating, and an
institutional tier for the most common sources. Falls back to the bare
domain (and no lean/tier) for unknown outlets — the registry is for
display polish, spectrum-balanced selection, and institutional-axis
reporting, not gating.

Two independent axes
--------------------

This registry deliberately tracks TWO orthogonal dimensions, because
they answer different questions:

- `lean` — left ↔ right framing. The familiar axis.
- `tier` — the *institutional position* of the outlet. This is the axis
  Herman & Chomsky's propaganda model (Manufacturing Consent) cares
  about: the most consequential filtering is not left-vs-right, it is
  the consensus shared *across* the entire commercial-mainstream
  spectrum. An analysis that samples only mainstream outlets — however
  "balanced" left-to-right — can still miss every perspective outside
  that consensus. Surfacing `tier` lets the report tell the reader what
  kind of sample they are actually looking at.

Lean ratings — sources and methodology
---------------------------------------

Lean ratings here are sourced primarily from **AllSides Media Bias
Ratings** (allsides.com/media-bias/ratings), with **Ad Fontes Media**
and **Media Bias/Fact Check** as cross-references for contested cases.
AllSides uses a five-point scale — Left, Lean Left, Center, Lean Right,
Right — derived from blind bias surveys, third-party research, editorial
reviews, independent reviews, and community feedback.

Important caveats:
- Ratings reflect **news content**, not editorial pages. The WSJ news
  desk is rated Center; its op-ed page is Right.
- "Center" does NOT mean "neutral truth." It means the outlet's framing
  on average lands roughly between left- and right-leaning peers. A
  Center outlet still has framing patterns this pipeline will surface.
- For UK/non-US outlets AllSides has gaps; secondary sources include the
  Reuters Institute Digital News Report's perceived-bias surveys. Where
  sources disagree noticeably the lean is left None and the outlet is
  selected on relevance only.
- Ratings are inherently subjective. Edit this file to override any
  individual call you disagree with — the rest of the pipeline reads
  whatever you set here.

Institutional tier — definitions
--------------------------------

`tier` is a structural fact about funding and organization, NOT a
quality or trust judgment:

- "mainstream"  — commercial / legacy news organizations and major
                  commercial digital outlets. The bulk of what GDELT
                  indexes. Wire services live here too.
- "public"     — publicly funded broadcasters operating under an
                  editorial-independence charter (licence fee or
                  legislative appropriation): BBC, NPR, PBS, CBC, etc.
- "independent" — non-profit, reader-funded, or investigative outlets
                  operating outside the corporate/legacy bloc.
- "advocacy"   — outlets organized around an explicit political project,
                  movement, or cause. Their framing is a feature of
                  their mission, not a deviation from neutrality.
- "state"      — state-owned or state-funded outlets where the funder is
                  a national government. Editorial independence varies
                  and is often contested; the tag flags the funding
                  structure so the reader can weigh it.

Tier assignment is even more contestable than lean. When in doubt the
default is "mainstream". Edit freely.

Bias ratings deliberately do NOT include factual-reliability or quality
scores. Mixing them here would conflate distinct concerns. The pipeline
displays bias and institutional position; quality assessment is the
reader's call.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# Order matters: it's the canonical left-to-right ordering used by
# spectrum-balanced selection in discover.py.
SPECTRUM_ORDER: tuple[str, ...] = (
    "left",
    "center-left",
    "center",
    "center-right",
    "right",
)


# Institutional tiers. "mainstream" is the default for outlets without
# an explicit tag. Order is rough establishment → non-establishment.
INSTITUTIONAL_TIERS: tuple[str, ...] = (
    "mainstream",
    "public",
    "independent",
    "advocacy",
    "state",
)


class OutletInfo(NamedTuple):
    name: str
    country: str
    outlet_type: str  # newspaper | wire | broadcaster | magazine | digital
    lean: Optional[str] = None  # one of SPECTRUM_ORDER, or None
    tier: str = "mainstream"  # one of INSTITUTIONAL_TIERS
    owner: Optional[str] = None  # short human-readable ownership label
    owner_key: Optional[str] = None  # normalized key for grouping outlets by shared owner


_REGISTRY: dict[str, OutletInfo] = {
    # ── US — newspapers ──────────────────────────────────────────────
    "nytimes.com": OutletInfo("The New York Times", "US", "newspaper", "center-left"),
    "wsj.com": OutletInfo("The Wall Street Journal", "US", "newspaper", "center"),
    "washingtonpost.com": OutletInfo("The Washington Post", "US", "newspaper", "center-left"),
    "usatoday.com": OutletInfo("USA Today", "US", "newspaper", "center-left"),
    "latimes.com": OutletInfo("Los Angeles Times", "US", "newspaper", "center-left"),
    "chicagotribune.com": OutletInfo("Chicago Tribune", "US", "newspaper", "center"),
    "bostonglobe.com": OutletInfo("The Boston Globe", "US", "newspaper", "center-left"),
    "nypost.com": OutletInfo("New York Post", "US", "newspaper", "center-right"),
    "washingtonexaminer.com": OutletInfo("Washington Examiner", "US", "digital", "right"),
    # ── US — wire services ───────────────────────────────────────────
    "apnews.com": OutletInfo("Associated Press", "US", "wire", "center"),
    # ── US — broadcasters ────────────────────────────────────────────
    "cnn.com": OutletInfo("CNN", "US", "broadcaster", "center-left"),
    "foxnews.com": OutletInfo("Fox News", "US", "broadcaster", "right"),
    "abcnews.go.com": OutletInfo("ABC News", "US", "broadcaster", "center-left"),
    "nbcnews.com": OutletInfo("NBC News", "US", "broadcaster", "center-left"),
    "cbsnews.com": OutletInfo("CBS News", "US", "broadcaster", "center-left"),
    "msnbc.com": OutletInfo("MSNBC", "US", "broadcaster", "left"),
    "npr.org": OutletInfo("NPR", "US", "broadcaster", "center-left", tier="public"),
    "pbs.org": OutletInfo("PBS NewsHour", "US", "broadcaster", "center", tier="public"),
    "newsmax.com": OutletInfo("Newsmax", "US", "broadcaster", "right", tier="advocacy"),
    "oann.com": OutletInfo("One America News", "US", "broadcaster", "right", tier="advocacy"),
    # ── US — magazines ───────────────────────────────────────────────
    "theatlantic.com": OutletInfo("The Atlantic", "US", "magazine", "left"),
    "newyorker.com": OutletInfo("The New Yorker", "US", "magazine", "left"),
    "time.com": OutletInfo("Time", "US", "magazine", "center-left"),
    "newsweek.com": OutletInfo("Newsweek", "US", "magazine", "center"),
    "forbes.com": OutletInfo("Forbes", "US", "magazine", "center"),
    "nationalreview.com": OutletInfo("National Review", "US", "magazine", "right", tier="advocacy"),
    "motherjones.com": OutletInfo("Mother Jones", "US", "magazine", "left", tier="independent"),
    "thenation.com": OutletInfo("The Nation", "US", "magazine", "left", tier="advocacy"),
    "jacobin.com": OutletInfo("Jacobin", "US", "magazine", "left", tier="advocacy"),
    "newrepublic.com": OutletInfo("The New Republic", "US", "magazine", "left"),
    "reason.com": OutletInfo("Reason", "US", "magazine", "center-right", tier="advocacy"),
    # ── US — digital ─────────────────────────────────────────────────
    "politico.com": OutletInfo("Politico", "US", "digital", "center-left"),
    "axios.com": OutletInfo("Axios", "US", "digital", "center"),
    "vox.com": OutletInfo("Vox", "US", "digital", "left"),
    "thehill.com": OutletInfo("The Hill", "US", "digital", "center"),
    "huffpost.com": OutletInfo("HuffPost", "US", "digital", "left"),
    "businessinsider.com": OutletInfo("Business Insider", "US", "digital", "center-left"),
    "thedailybeast.com": OutletInfo("The Daily Beast", "US", "digital", "left"),
    "slate.com": OutletInfo("Slate", "US", "digital", "left"),
    "salon.com": OutletInfo("Salon", "US", "digital", "left"),
    "forward.com": OutletInfo("The Forward", "US", "magazine", "center-left"),
    "propublica.org": OutletInfo("ProPublica", "US", "digital", "center-left", tier="independent"),
    "theintercept.com": OutletInfo("The Intercept", "US", "digital", "left", tier="independent"),
    "commondreams.org": OutletInfo("Common Dreams", "US", "digital", "left", tier="independent"),
    "truthout.org": OutletInfo("Truthout", "US", "digital", "left", tier="independent"),
    "consortiumnews.com": OutletInfo("Consortium News", "US", "digital", "left", tier="independent"),
    "thegrayzone.com": OutletInfo("The Grayzone", "US", "digital", None, tier="independent"),
    "wsws.org": OutletInfo("World Socialist Web Site", "US", "digital", "left", tier="advocacy"),
    "dailykos.com": OutletInfo("Daily Kos", "US", "digital", "left", tier="advocacy"),
    "thedailywire.com": OutletInfo("The Daily Wire", "US", "digital", "right", tier="advocacy"),
    "breitbart.com": OutletInfo("Breitbart", "US", "digital", "right", tier="advocacy"),
    "thefederalist.com": OutletInfo("The Federalist", "US", "digital", "right", tier="advocacy"),
    "theblaze.com": OutletInfo("The Blaze", "US", "digital", "right", tier="advocacy"),
    # ── US — financial ───────────────────────────────────────────────
    "bloomberg.com": OutletInfo("Bloomberg", "US", "newspaper", "center"),
    # ── UK ───────────────────────────────────────────────────────────
    "huffingtonpost.co.uk": OutletInfo("HuffPost UK", "UK", "digital", "left"),
    "reuters.com": OutletInfo("Reuters", "UK", "wire", "center"),
    "bbc.com": OutletInfo("BBC News", "UK", "broadcaster", "center", tier="public"),
    "bbc.co.uk": OutletInfo("BBC News", "UK", "broadcaster", "center", tier="public"),
    "theguardian.com": OutletInfo("The Guardian", "UK", "newspaper", "center-left"),
    "ft.com": OutletInfo("Financial Times", "UK", "newspaper", "center-right"),
    "thetimes.co.uk": OutletInfo("The Times", "UK", "newspaper", "center-right"),
    "thetimes.com": OutletInfo("The Times", "UK", "newspaper", "center-right"),
    "telegraph.co.uk": OutletInfo("The Telegraph", "UK", "newspaper", "right"),
    "independent.co.uk": OutletInfo("The Independent", "UK", "digital", "center-left"),
    "dailymail.co.uk": OutletInfo("Daily Mail", "UK", "newspaper", "right"),
    "mirror.co.uk": OutletInfo("Daily Mirror", "UK", "newspaper", "left"),
    "express.co.uk": OutletInfo("Daily Express", "UK", "newspaper", "right"),
    "metro.co.uk": OutletInfo("Metro", "UK", "newspaper", "center"),
    "economist.com": OutletInfo("The Economist", "UK", "magazine", "center"),
    "spectator.co.uk": OutletInfo("The Spectator", "UK", "magazine", "right"),
    "newstatesman.com": OutletInfo("New Statesman", "UK", "magazine", "left"),
    "news.sky.com": OutletInfo("Sky News", "UK", "broadcaster", "center"),
    "itv.com": OutletInfo("ITV News", "UK", "broadcaster", "center"),
    "gbnews.com": OutletInfo("GB News", "UK", "broadcaster", "right"),
    "heraldscotland.com": OutletInfo("The Herald", "UK", "newspaper", "center-left"),
    "thenational.scot": OutletInfo("The National", "UK", "newspaper", "left"),
    "morningstaronline.co.uk": OutletInfo("Morning Star", "UK", "newspaper", "left", tier="advocacy"),
    "opendemocracy.net": OutletInfo("openDemocracy", "UK", "digital", "left", tier="independent"),
    "theweek.com": OutletInfo("The Week", "UK", "magazine", "center"),
    "thejc.com": OutletInfo("The Jewish Chronicle", "UK", "newspaper", None),
    "middleeasteye.net": OutletInfo("Middle East Eye", "UK", "digital", None, tier="independent"),
    # ── Europe ───────────────────────────────────────────────────────
    "afp.com": OutletInfo("Agence France-Presse", "FR", "wire", "center"),
    "lemonde.fr": OutletInfo("Le Monde", "FR", "newspaper", "center-left"),
    "lefigaro.fr": OutletInfo("Le Figaro", "FR", "newspaper", "center-right"),
    "liberation.fr": OutletInfo("Libération", "FR", "newspaper", "left"),
    "monde-diplomatique.fr": OutletInfo("Le Monde diplomatique", "FR", "magazine", "left", tier="independent"),
    "france24.com": OutletInfo("France 24", "FR", "broadcaster", "center", tier="public"),
    "spiegel.de": OutletInfo("Der Spiegel", "DE", "magazine", "center-left"),
    "sueddeutsche.de": OutletInfo("Süddeutsche Zeitung", "DE", "newspaper", "center-left"),
    "faz.net": OutletInfo("Frankfurter Allgemeine", "DE", "newspaper", "center-right"),
    "dw.com": OutletInfo("Deutsche Welle", "DE", "broadcaster", "center", tier="public"),
    "elpais.com": OutletInfo("El País", "ES", "newspaper", "center-left"),
    "elmundo.es": OutletInfo("El Mundo", "ES", "newspaper", "center-right"),
    "corriere.it": OutletInfo("Corriere della Sera", "IT", "newspaper", "center"),
    "repubblica.it": OutletInfo("La Repubblica", "IT", "newspaper", "center-left"),
    "nrc.nl": OutletInfo("NRC", "NL", "newspaper", "center"),
    "volkskrant.nl": OutletInfo("de Volkskrant", "NL", "newspaper", "center-left"),
    "euronews.com": OutletInfo("Euronews", "EU", "broadcaster", "center"),
    "politico.eu": OutletInfo("Politico Europe", "EU", "digital", "center"),
    "irishtimes.com": OutletInfo("The Irish Times", "IE", "newspaper", "center-left"),
    "rte.ie": OutletInfo("RTÉ", "IE", "broadcaster", "center", tier="public"),
    # Nordic
    "aftenposten.no": OutletInfo("Aftenposten", "NO", "newspaper", "center-right"),
    "nrk.no": OutletInfo("NRK", "NO", "broadcaster", "center", tier="public"),
    "dn.se": OutletInfo("Dagens Nyheter", "SE", "newspaper", "center"),
    "svt.se": OutletInfo("SVT", "SE", "broadcaster", "center", tier="public"),
    "hs.fi": OutletInfo("Helsingin Sanomat", "FI", "newspaper", "center"),
    "yle.fi": OutletInfo("Yle", "FI", "broadcaster", "center", tier="public"),
    "politiken.dk": OutletInfo("Politiken", "DK", "newspaper", "center-left"),
    # Central / Eastern Europe
    "rtvslo.si": OutletInfo("RTV Slovenija", "SI", "broadcaster", "center", tier="public"),
    "lrytas.lt": OutletInfo("Lrytas", "LT", "digital", "center"),
    "delfi.lt": OutletInfo("Delfi", "LT", "digital", "center"),
    "wyborcza.pl": OutletInfo("Gazeta Wyborcza", "PL", "newspaper", "center-left"),
    "novayagazeta.eu": OutletInfo("Novaya Gazeta Europe", "RU", "digital", "left", tier="independent"),
    "meduza.io": OutletInfo("Meduza", "RU", "digital", "center-left", tier="independent"),
    "theconversation.com": OutletInfo("The Conversation", "AU", "digital", "center", tier="independent"),
    # ── Americas / Oceania ───────────────────────────────────────────
    "globeandmail.com": OutletInfo("The Globe and Mail", "CA", "newspaper", "center"),
    "cbc.ca": OutletInfo("CBC News", "CA", "broadcaster", "center-left", tier="public"),
    "thestar.com": OutletInfo("Toronto Star", "CA", "newspaper", "center-left"),
    "winnipegfreepress.com": OutletInfo("Winnipeg Free Press", "CA", "newspaper", "center"),
    "abc.net.au": OutletInfo("ABC News (Australia)", "AU", "broadcaster", "center-left", tier="public"),
    "smh.com.au": OutletInfo("Sydney Morning Herald", "AU", "newspaper", "center-left"),
    "theaustralian.com.au": OutletInfo("The Australian", "AU", "newspaper", "right"),
    "skynews.com.au": OutletInfo("Sky News Australia", "AU", "broadcaster", "right"),
    "stuff.co.nz": OutletInfo("Stuff", "NZ", "digital", "center"),
    "rnz.co.nz": OutletInfo("RNZ", "NZ", "broadcaster", "center", tier="public"),
    "clarin.com": OutletInfo("Clarín", "AR", "newspaper", "center"),
    "folha.uol.com.br": OutletInfo("Folha de S.Paulo", "BR", "newspaper", "center"),
    "eluniversal.com.mx": OutletInfo("El Universal", "MX", "newspaper", "center"),
    # ── Middle East ──────────────────────────────────────────────────
    "haaretz.com": OutletInfo("Haaretz", "IL", "newspaper", "center-left"),
    "timesofisrael.com": OutletInfo("The Times of Israel", "IL", "digital", "center"),
    "jpost.com": OutletInfo("The Jerusalem Post", "IL", "newspaper", "center-right"),
    "ynetnews.com": OutletInfo("Ynetnews", "IL", "digital", "center-right"),
    "arabnews.com": OutletInfo("Arab News", "SA", "newspaper", None),
    "almanar.com.lb": OutletInfo("Al-Manar", "LB", "broadcaster", None, tier="state"),
    "dailystar.com.lb": OutletInfo("The Daily Star (Lebanon)", "LB", "newspaper", "center"),
    "aa.com.tr": OutletInfo("Anadolu Agency", "TR", "wire", None, tier="state"),
    "trtworld.com": OutletInfo("TRT World", "TR", "broadcaster", None, tier="state"),
    "hurriyetdailynews.com": OutletInfo("Hürriyet Daily News", "TR", "newspaper", "center-right"),
    "milliyet.com.tr": OutletInfo("Milliyet", "TR", "newspaper", "center"),
    "aksam.com.tr": OutletInfo("Akşam", "TR", "newspaper", "center-right"),
    "yeniakit.com.tr": OutletInfo("Yeni Akit", "TR", "newspaper", "right", tier="advocacy"),
    "haberler.com": OutletInfo("Haberler", "TR", "digital", None),
    "haber.mynet.com": OutletInfo("Mynet Haber", "TR", "digital", None),
    "presstv.ir": OutletInfo("Press TV", "IR", "broadcaster", None, tier="state"),
    # ── Asia ─────────────────────────────────────────────────────────
    "japantimes.co.jp": OutletInfo("The Japan Times", "JP", "newspaper", "center"),
    "asahi.com": OutletInfo("Asahi Shimbun", "JP", "newspaper", "center-left"),
    "thehindu.com": OutletInfo("The Hindu", "IN", "newspaper", "center-left"),
    "timesofindia.indiatimes.com": OutletInfo("The Times of India", "IN", "newspaper", "center"),
    "indianexpress.com": OutletInfo("The Indian Express", "IN", "newspaper", "center"),
    "ndtv.com": OutletInfo("NDTV", "IN", "broadcaster", None),
    "thewire.in": OutletInfo("The Wire", "IN", "digital", "left", tier="independent"),
    "straitstimes.com": OutletInfo("The Straits Times", "SG", "newspaper", "center"),
    "channelnewsasia.com": OutletInfo("CNA", "SG", "broadcaster", "center", tier="public"),
    "thestar.com.my": OutletInfo("The Star (Malaysia)", "MY", "newspaper", "center"),
    "vnexpress.net": OutletInfo("VnExpress", "VN", "digital", None, tier="state"),
    "vietnamnews.vn": OutletInfo("Viet Nam News", "VN", "newspaper", None, tier="state"),
    "nhandan.vn": OutletInfo("Nhân Dân", "VN", "newspaper", None, tier="state"),
    # ── Africa ───────────────────────────────────────────────────────
    "mg.co.za": OutletInfo("Mail & Guardian", "ZA", "newspaper", "center-left"),
    "dailymaverick.co.za": OutletInfo("Daily Maverick", "ZA", "digital", "center-left", tier="independent"),
    "newvision.co.ug": OutletInfo("New Vision", "UG", "newspaper", None),
    # ── State-funded / state-controlled ──────────────────────────────
    # Lean is left None: the relevant axis for these is the institutional
    # tier, not left/right framing.
    "aljazeera.com": OutletInfo("Al Jazeera", "QA", "broadcaster", None, tier="state"),
    "scmp.com": OutletInfo("South China Morning Post", "HK", "newspaper", None),
    "rt.com": OutletInfo("RT", "RU", "broadcaster", None, tier="state"),
    "sputniknews.com": OutletInfo("Sputnik", "RU", "digital", None, tier="state"),
    "tass.com": OutletInfo("TASS", "RU", "wire", None, tier="state"),
    "globaltimes.cn": OutletInfo("Global Times", "CN", "newspaper", None, tier="state"),
    "xinhuanet.com": OutletInfo("Xinhua", "CN", "wire", None, tier="state"),
    "cgtn.com": OutletInfo("CGTN", "CN", "broadcaster", None, tier="state"),
    "chinadaily.com.cn": OutletInfo("China Daily", "CN", "newspaper", None, tier="state"),
    # ── archive.org wrapper ──────────────────────────────────────────
    # Articles fetched through the Wayback Machine carry the
    # web.archive.org host. We can't usefully classify the wrapper
    # itself; selectors should treat it as unknown so the underlying
    # outlet (visible in the URL path) is what the reader sees.
    # If you want richer historical analysis, normalise the upstream
    # domain in ingest before this lookup ever sees web.archive.org.
}


# Ownership / parent-company data, applied to _REGISTRY at import time.
#
# Maintained as a sidecar dict rather than baked into each OutletInfo so
# the registry above stays readable and editing one axis (lean / tier /
# owner) doesn't churn unrelated columns.
#
# (owner_label, owner_key) per domain:
#   - owner_label is what the report shows the reader.
#   - owner_key is a short canonical id used to GROUP outlets that share
#     the same ultimate parent, so the ownership-concentration panel can
#     say "5 outlets in this sample are News Corp papers" automatically.
#
# Ownership data is notoriously volatile (buyouts, mergers, founder
# deaths). Treat this list as a snapshot; edit when it falls out of date.
# When unsure, leave the outlet absent rather than guess — the report
# distinguishes "unknown owner" from a confident attribution.
_OWNERSHIP: dict[str, tuple[str, str]] = {
    # ── News Corp / Fox Corp (Murdoch family) ────────────────────────
    "wsj.com": ("News Corp (Murdoch family)", "news_corp"),
    "nypost.com": ("News Corp (Murdoch family)", "news_corp"),
    "thetimes.com": ("News UK / News Corp (Murdoch family)", "news_corp"),
    "thetimes.co.uk": ("News UK / News Corp (Murdoch family)", "news_corp"),
    "foxnews.com": ("Fox Corporation (Murdoch family)", "fox_corp"),
    "theaustralian.com.au": ("News Corp Australia (Murdoch family)", "news_corp"),
    "skynews.com.au": ("News Corp Australia (Murdoch family)", "news_corp"),
    # ── Reach plc ────────────────────────────────────────────────────
    "mirror.co.uk": ("Reach plc (public)", "reach_plc"),
    "express.co.uk": ("Reach plc (public)", "reach_plc"),
    # ── DMGT (Rothermere family) ─────────────────────────────────────
    "dailymail.co.uk": ("DMGT (Rothermere family)", "dmgt"),
    "metro.co.uk": ("DMGT (Rothermere family)", "dmgt"),
    # ── Newsquest (Gannett) ──────────────────────────────────────────
    "heraldscotland.com": ("Newsquest (Gannett, public US)", "gannett"),
    "thenational.scot": ("Newsquest (Gannett, public US)", "gannett"),
    "usatoday.com": ("Gannett (public)", "gannett"),
    # ── Comcast / NBCUniversal ───────────────────────────────────────
    "nbcnews.com": ("NBCUniversal (Comcast, public)", "comcast"),
    "msnbc.com": ("NBCUniversal (Comcast, public)", "comcast"),
    "news.sky.com": ("Sky / Comcast (public)", "comcast"),
    # ── Other US conglomerates ───────────────────────────────────────
    "cnn.com": ("Warner Bros. Discovery (public)", "wbd"),
    "abcnews.go.com": ("Walt Disney Company (public)", "disney"),
    "cbsnews.com": ("Paramount Global (public)", "paramount"),
    "newyorker.com": ("Condé Nast / Advance Publications (Newhouse family)", "advance"),
    # ── US billionaire-owned ─────────────────────────────────────────
    "washingtonpost.com": ("Nash Holdings (Jeff Bezos, private)", "bezos"),
    "latimes.com": ("Patrick Soon-Shiong (private)", "soon_shiong"),
    "theatlantic.com": ("Emerson Collective (Laurene Powell Jobs)", "emerson"),
    "time.com": ("Marc Benioff (private)", "benioff"),
    "bloomberg.com": ("Bloomberg LP (Michael Bloomberg, private)", "bloomberg_lp"),
    # ── US legacy independent ────────────────────────────────────────
    "nytimes.com": ("New York Times Company (Sulzberger family + public)", "nyt_co"),
    "bostonglobe.com": ("Boston Globe Media (John Henry, private)", "henry"),
    # ── US partisan digital ──────────────────────────────────────────
    "thedailywire.com": ("Bentkey Ventures (Boreing & Shapiro, private)", "daily_wire"),
    "breitbart.com": ("Breitbart News Network (private)", "breitbart_priv"),
    "newsmax.com": ("Newsmax Media (Chris Ruddy, private)", "newsmax_priv"),
    "oann.com": ("Herring Networks (Herring family, private)", "herring"),
    "theblaze.com": ("Blaze Media (private)", "blaze_priv"),
    "thefederalist.com": ("FDRLST Media (Ben Domenech, private)", "federalist_priv"),
    "washingtonexaminer.com": ("Clarity Media (Philip Anschutz)", "anschutz"),
    "nationalreview.com": ("National Review Institute (nonprofit)", "nonprofit_us"),
    # ── US/UK digital majors ─────────────────────────────────────────
    "politico.com": ("Axel Springer SE (Friede Springer & KKR)", "axel_springer"),
    "businessinsider.com": ("Axel Springer SE", "axel_springer"),
    "huffpost.com": ("BuzzFeed Inc. (public)", "buzzfeed"),
    "huffingtonpost.co.uk": ("BuzzFeed Inc. (public)", "buzzfeed"),
    "vox.com": ("Vox Media (Penske / private equity)", "vox_media"),
    "thedailybeast.com": ("IAC (Barry Diller, public)", "iac"),
    "axios.com": ("Cox Enterprises (Cox family, private)", "cox"),
    "thehill.com": ("Nexstar Media Group (public)", "nexstar"),
    "newsweek.com": ("Newsweek LLC / IBT Media (private)", "ibt"),
    "forbes.com": ("Integrated Whale Media (private, Asian investors)", "iwm"),
    "slate.com": ("Graham Holdings Company (Graham family, public)", "graham_holdings"),
    "newrepublic.com": ("Win McCormack (private)", "mccormack"),
    # ── US nonprofit / reader-funded independents ────────────────────
    "apnews.com": ("Associated Press (nonprofit cooperative)", "ap_coop"),
    "npr.org": ("National Public Radio (nonprofit; member stations + appropriation)", "npr_nonprofit"),
    "pbs.org": ("Public Broadcasting Service (nonprofit; appropriation)", "pbs_nonprofit"),
    "propublica.org": ("ProPublica (nonprofit; Sandler Foundation & others)", "propublica_nonprofit"),
    "theintercept.com": ("First Look Media (Pierre Omidyar)", "omidyar"),
    "motherjones.com": ("Foundation for National Progress (nonprofit)", "motherjones_nonprofit"),
    "thenation.com": ("The Nation Company (nonprofit)", "thenation_nonprofit"),
    "jacobin.com": ("Jacobin Foundation (independent)", "jacobin_indep"),
    "commondreams.org": ("Common Dreams (nonprofit)", "cd_nonprofit"),
    "truthout.org": ("Truthout (nonprofit)", "truthout_nonprofit"),
    "consortiumnews.com": ("Consortium for Independent Journalism (nonprofit)", "consortium_nonprofit"),
    "forward.com": ("Forward Association (nonprofit)", "forward_nonprofit"),
    "reason.com": ("Reason Foundation (nonprofit)", "reason_nonprofit"),
    "dailykos.com": ("Kos Media (private)", "kos_priv"),
    # ── UK ───────────────────────────────────────────────────────────
    "theguardian.com": ("Guardian Media Group (Scott Trust — independent perpetuity)", "scott_trust"),
    "ft.com": ("Nikkei Inc. (public, Japan)", "nikkei"),
    "telegraph.co.uk": ("Press Holdings — sale pending (Barclay family)", "press_holdings"),
    "spectator.co.uk": ("Press Holdings — sale pending (Barclay family)", "press_holdings"),
    "independent.co.uk": ("Sultan Mohamed Abuljadayel (private)", "abuljadayel"),
    "economist.com": ("The Economist Group (Agnelli/Rothschild/Cadbury & others)", "economist_group"),
    "newstatesman.com": ("New Statesman Media Group (Michael Danson, private)", "danson"),
    "itv.com": ("ITV plc (public)", "itv_plc"),
    "gbnews.com": ("All Perspectives Ltd (Discovery, Legatum, Dubai investors)", "gbnews_consortium"),
    "morningstaronline.co.uk": ("People's Press Printing Society (reader cooperative)", "ppps_coop"),
    "opendemocracy.net": ("openDemocracy Foundation (nonprofit)", "od_nonprofit"),
    "theweek.com": ("Future plc (public)", "future_plc"),
    "thejc.com": ("Jewish Chronicle Media Group (consortium, private)", "jc_consortium"),
    "middleeasteye.net": ("Middle East Eye Ltd (private; ownership disputed)", "mee_priv"),
    "bbc.com": ("British Broadcasting Corporation (Royal Charter; licence fee)", "bbc"),
    "bbc.co.uk": ("British Broadcasting Corporation (Royal Charter; licence fee)", "bbc"),
    # ── France / Germany / Europe ────────────────────────────────────
    "lemonde.fr": ("Le Monde Libre (Bergé / Niel / Pigasse)", "lemonde_consortium"),
    "lefigaro.fr": ("Groupe Dassault (Dassault family)", "dassault"),
    "liberation.fr": ("Presse Indépendante (Patrick Drahi, private)", "drahi"),
    "monde-diplomatique.fr": ("Association Gunter Holzmann (cooperative-style independent)", "mdiplo_indep"),
    "france24.com": ("France Médias Monde (French state)", "fr_state"),
    "afp.com": ("Agence France-Presse (state-mandated wire; AFP charter)", "afp_charter"),
    "spiegel.de": ("SPIEGEL-Verlag (employee partnership)", "spiegel_partnership"),
    "sueddeutsche.de": ("Süddeutsche Zeitung GmbH (SWMH; Friede Springer & others)", "swmh"),
    "faz.net": ("FAZIT-Stiftung (foundation, independent)", "fazit_foundation"),
    "dw.com": ("Deutsche Welle (German state-funded)", "de_state"),
    "elpais.com": ("Grupo PRISA (public, Spain)", "prisa"),
    "elmundo.es": ("Unidad Editorial (RCS MediaGroup, Italy)", "rcs"),
    "corriere.it": ("RCS MediaGroup (public, Italy)", "rcs"),
    "repubblica.it": ("GEDI Gruppo Editoriale (Exor — Agnelli family)", "exor"),
    "irishtimes.com": ("Irish Times Trust (nonprofit, independent)", "irish_times_trust"),
    "rte.ie": ("Raidió Teilifís Éireann (Irish state-funded)", "ie_state"),
    "rtvslo.si": ("RTV Slovenija (Slovenian state-funded)", "si_state"),
    "nrk.no": ("NRK (Norwegian state-funded)", "no_state"),
    "svt.se": ("Sveriges Television (Swedish state-funded)", "se_state"),
    "yle.fi": ("Yleisradio (Finnish state-funded)", "fi_state"),
    "theconversation.com": ("The Conversation Trust (academic consortium, nonprofit)", "conversation_trust"),
    # ── Americas / Oceania ───────────────────────────────────────────
    "globeandmail.com": ("Woodbridge Company (Thomson family, private)", "thomson"),
    "cbc.ca": ("Canadian Broadcasting Corporation (federal state)", "ca_state"),
    "thestar.com": ("NordStar Capital (Bitove & Rivett, private)", "nordstar"),
    "winnipegfreepress.com": ("FP Newspapers / FP Canadian Newspapers Limited Partnership", "fp_news"),
    "abc.net.au": ("Australian Broadcasting Corporation (federal state)", "au_state"),
    "smh.com.au": ("Nine Entertainment Co (public, Australia)", "nine_ent"),
    "rnz.co.nz": ("Radio New Zealand (NZ state-funded)", "nz_state"),
    # ── Middle East ──────────────────────────────────────────────────
    "haaretz.com": ("Haaretz Group (Schocken family, private)", "schocken"),
    "jpost.com": ("Jerusalem Post Group (Eli Azur, private)", "azur"),
    "ynetnews.com": ("Yedioth Media Group (Mozes family, private)", "mozes"),
    "arabnews.com": ("Saudi Research and Media Group (Saudi state-aligned)", "srmg"),
    "almanar.com.lb": ("Lebanese Media Group (Hezbollah-affiliated)", "hezbollah_mg"),
    "aa.com.tr": ("Anadolu Agency (Turkish state-affiliated)", "tr_state"),
    "trtworld.com": ("TRT (Turkish public broadcaster, state-funded)", "tr_state"),
    "presstv.ir": ("IRIB (Iranian state)", "ir_state"),
    "milliyet.com.tr": ("Demirören Holding (private, Turkey)", "demiroren"),
    "hurriyetdailynews.com": ("Demirören Holding (private, Turkey)", "demiroren"),
    "aksam.com.tr": ("Turkuvaz Media Group (Kalyon Group; pro-government)", "turkuvaz"),
    # ── Asia ─────────────────────────────────────────────────────────
    "asahi.com": ("Asahi Shimbun Company (private)", "asahi_priv"),
    "thehindu.com": ("Kasturi & Sons (family)", "kasturi"),
    "timesofindia.indiatimes.com": ("Bennett, Coleman & Co (Jain family)", "bennett_coleman"),
    "indianexpress.com": ("Indian Express Group (Goenka family)", "goenka"),
    "ndtv.com": ("Adani Group (Gautam Adani)", "adani"),
    "thewire.in": ("Foundation for Independent Journalism (nonprofit)", "fij_nonprofit"),
    "straitstimes.com": ("SPH Media Trust (nonprofit; post-2022 restructuring)", "sph_trust"),
    "channelnewsasia.com": ("Mediacorp (Singapore state holding company Temasek)", "mediacorp_temasek"),
    # ── Africa ───────────────────────────────────────────────────────
    "dailymaverick.co.za": ("Daily Maverick (independent, Branko Brkic)", "dm_indep"),
    "newvision.co.ug": ("Vision Group (Ugandan government majority)", "ug_state"),
    # ── Explicitly state-controlled ──────────────────────────────────
    "aljazeera.com": ("Qatar Media Corporation (Qatari state-funded)", "qa_state"),
    "rt.com": ("ANO TV-Novosti (Russian state-funded)", "ru_state"),
    "sputniknews.com": ("Rossiya Segodnya (Russian state)", "ru_state"),
    "tass.com": ("ITAR-TASS (Russian state)", "ru_state"),
    "globaltimes.cn": ("People's Daily (CCP organ)", "cn_state"),
    "xinhuanet.com": ("Xinhua News Agency (CCP)", "cn_state"),
    "cgtn.com": ("China Media Group (CCP)", "cn_state"),
    "chinadaily.com.cn": ("China Daily (CCP)", "cn_state"),
    "scmp.com": ("Alibaba Group (Jack Ma, public China)", "alibaba"),
    "vnexpress.net": ("FPT Corporation (Vietnam, state-influenced)", "vn_corp"),
    "vietnamnews.vn": ("Vietnam News Agency (Vietnamese state)", "vn_state"),
    "nhandan.vn": ("Communist Party of Vietnam (party organ)", "vn_state"),
    # ── Russian independent (in exile) ───────────────────────────────
    "novayagazeta.eu": ("Novaya Gazeta (independent, in exile)", "ng_indep"),
    "meduza.io": ("Meduza Project SIA (independent, in exile in Latvia)", "meduza_indep"),
}

# Merge ownership data onto the registry entries.
for _domain, (_owner, _owner_key) in _OWNERSHIP.items():
    if _domain in _REGISTRY:
        _REGISTRY[_domain] = _REGISTRY[_domain]._replace(
            owner=_owner, owner_key=_owner_key
        )


def lookup(domain: str) -> Optional[OutletInfo]:
    """Return registry info for a domain, or None if unknown."""
    return _REGISTRY.get(domain)


def display_name(domain: str) -> str:
    """Friendly name if known, else the bare domain."""
    info = _REGISTRY.get(domain)
    return info.name if info else domain


def ownership_summary(domains: list[str]) -> dict:
    """Group `domains` by their canonical owner_key.

    Returns a dict with:
      - by_owner_key: {owner_key: {label, domains, n}}
      - n_outlets: total outlets passed in
      - n_owners: distinct owner_keys (unknowns each count as their own)
      - n_unknown: outlets without an owner_key
      - largest_share: count of outlets under the most-concentrated owner
    """
    by_key: dict[str, dict] = {}
    n_unknown = 0
    seen_unknown_keys: set[str] = set()
    for domain in domains:
        info = _REGISTRY.get(domain)
        key = info.owner_key if info and info.owner_key else None
        label = info.owner if info and info.owner else "Unknown owner"
        if key is None:
            n_unknown += 1
            placeholder = f"__unknown__{domain}"
            seen_unknown_keys.add(placeholder)
            by_key[placeholder] = {
                "label": f"Unknown ({domain})",
                "domains": [domain],
                "n": 1,
            }
            continue
        if key not in by_key:
            by_key[key] = {"label": label, "domains": [], "n": 0}
        by_key[key]["domains"].append(domain)
        by_key[key]["n"] += 1

    n_owners = len(by_key)
    largest_share = max((g["n"] for g in by_key.values()), default=0)
    return {
        "by_owner_key": by_key,
        "n_outlets": len(domains),
        "n_owners": n_owners,
        "n_unknown": n_unknown,
        "largest_share": largest_share,
    }
