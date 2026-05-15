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
    "france24.com": OutletInfo("France 24", "FR", "broadcaster", "center", tier="public"),
    "spiegel.de": OutletInfo("Der Spiegel", "DE", "magazine", "center-left"),
    "dw.com": OutletInfo("Deutsche Welle", "DE", "broadcaster", "center", tier="public"),
    "elpais.com": OutletInfo("El País", "ES", "newspaper", "center-left"),
    "euronews.com": OutletInfo("Euronews", "EU", "broadcaster", "center"),
    "irishtimes.com": OutletInfo("The Irish Times", "IE", "newspaper", "center-left"),
    "rte.ie": OutletInfo("RTÉ", "IE", "broadcaster", "center", tier="public"),
    "theconversation.com": OutletInfo("The Conversation", "AU", "digital", "center", tier="independent"),
    # ── Americas / Oceania ───────────────────────────────────────────
    "globeandmail.com": OutletInfo("The Globe and Mail", "CA", "newspaper", "center"),
    "cbc.ca": OutletInfo("CBC News", "CA", "broadcaster", "center-left", tier="public"),
    "abc.net.au": OutletInfo("ABC News (Australia)", "AU", "broadcaster", "center-left", tier="public"),
    "smh.com.au": OutletInfo("Sydney Morning Herald", "AU", "newspaper", "center-left"),
    # ── Middle East ──────────────────────────────────────────────────
    "haaretz.com": OutletInfo("Haaretz", "IL", "newspaper", "center-left"),
    "timesofisrael.com": OutletInfo("The Times of Israel", "IL", "digital", "center"),
    "jpost.com": OutletInfo("The Jerusalem Post", "IL", "newspaper", "center-right"),
    # ── Asia ─────────────────────────────────────────────────────────
    "japantimes.co.jp": OutletInfo("The Japan Times", "JP", "newspaper", "center"),
    "thehindu.com": OutletInfo("The Hindu", "IN", "newspaper", "center-left"),
    "timesofindia.indiatimes.com": OutletInfo("The Times of India", "IN", "newspaper", "center"),
    "ndtv.com": OutletInfo("NDTV", "IN", "broadcaster", None),
    "straitstimes.com": OutletInfo("The Straits Times", "SG", "newspaper", "center"),
    # ── State-funded / state-controlled ──────────────────────────────
    # Lean is left None: the relevant axis for these is the institutional
    # tier, not left/right framing.
    "aljazeera.com": OutletInfo("Al Jazeera", "QA", "broadcaster", None, tier="state"),
    "scmp.com": OutletInfo("South China Morning Post", "HK", "newspaper", None),
    "rt.com": OutletInfo("RT", "RU", "broadcaster", None, tier="state"),
    "globaltimes.cn": OutletInfo("Global Times", "CN", "newspaper", None, tier="state"),
    "xinhuanet.com": OutletInfo("Xinhua", "CN", "wire", None, tier="state"),
}


def lookup(domain: str) -> Optional[OutletInfo]:
    """Return registry info for a domain, or None if unknown."""
    return _REGISTRY.get(domain)


def display_name(domain: str) -> str:
    """Friendly name if known, else the bare domain."""
    info = _REGISTRY.get(domain)
    return info.name if info else domain
