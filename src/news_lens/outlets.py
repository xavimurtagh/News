"""Static lookup of well-known news outlets.

Friendly names, country, outlet type, and a publicly-sourced political-lean
rating for the most common sources. Falls back to the bare domain (and no
lean) for unknown outlets — the registry is for display polish and
spectrum-balanced selection, not gating.

Lean ratings — sources and methodology
--------------------------------------

Lean ratings here are sourced primarily from **AllSides Media Bias Ratings**
(allsides.com/media-bias/ratings), with **Ad Fontes Media** as a
cross-reference for contested cases. AllSides uses a five-point scale —
Left, Lean Left, Center, Lean Right, Right — derived from blind bias
surveys, third-party research, editorial reviews, independent reviews,
and community feedback. Their published methodology is at
allsides.com/media-bias/media-bias-rating-methods.

Important caveats:
- Ratings reflect **news content** as judged by AllSides, not editorial
  pages. The WSJ news desk is rated Center; its op-ed page is Right.
- "Center" does NOT mean "neutral truth." It means the outlet's framing
  on average lands roughly between left- and right-leaning peers.
  A Center outlet still has framing patterns this pipeline will surface.
- For UK/non-US outlets AllSides has gaps; secondary sources include the
  Reuters Institute Digital News Report's perceived-bias surveys and
  Ad Fontes Media. Where sources disagree noticeably the lean is left
  None and the outlet is selected on relevance only.
- Ratings are inherently subjective. Edit this file to override any
  individual call you disagree with — the rest of the pipeline reads
  whatever you set here.

Lean values used here:
    "left", "center-left", "center", "center-right", "right", or None.

The five-bucket scale maps cleanly to AllSides' Left / Lean Left /
Center / Lean Right / Right.

Bias ratings deliberately do NOT include factual-reliability,
trustworthiness, or quality scores. Those exist (Ad Fontes publishes a
quality axis; MBFC publishes "factual reporting" tiers) but mixing
them with bias here would conflate two distinct concerns. The pipeline
displays bias as one dimension; quality assessment is the reader's
call.
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


class OutletInfo(NamedTuple):
    name: str
    country: str
    outlet_type: str  # newspaper | wire | broadcaster | magazine | digital
    lean: Optional[str] = None  # one of SPECTRUM_ORDER, or None


_REGISTRY: dict[str, OutletInfo] = {
    # US — newspapers
    "nytimes.com": OutletInfo("The New York Times", "US", "newspaper", "center-left"),
    "wsj.com": OutletInfo("The Wall Street Journal", "US", "newspaper", "center"),
    "washingtonpost.com": OutletInfo("The Washington Post", "US", "newspaper", "center-left"),
    "usatoday.com": OutletInfo("USA Today", "US", "newspaper", "center-left"),
    "latimes.com": OutletInfo("Los Angeles Times", "US", "newspaper", "center-left"),
    "chicagotribune.com": OutletInfo("Chicago Tribune", "US", "newspaper", "center"),
    "bostonglobe.com": OutletInfo("The Boston Globe", "US", "newspaper", "center-left"),
    "nypost.com": OutletInfo("New York Post", "US", "newspaper", "center-right"),
    # US — wire services
    "apnews.com": OutletInfo("Associated Press", "US", "wire", "center"),
    # US — broadcasters
    "cnn.com": OutletInfo("CNN", "US", "broadcaster", "center-left"),
    "foxnews.com": OutletInfo("Fox News", "US", "broadcaster", "right"),
    "abcnews.go.com": OutletInfo("ABC News", "US", "broadcaster", "center-left"),
    "nbcnews.com": OutletInfo("NBC News", "US", "broadcaster", "center-left"),
    "cbsnews.com": OutletInfo("CBS News", "US", "broadcaster", "center-left"),
    "msnbc.com": OutletInfo("MSNBC", "US", "broadcaster", "left"),
    "npr.org": OutletInfo("NPR", "US", "broadcaster", "center-left"),
    "pbs.org": OutletInfo("PBS NewsHour", "US", "broadcaster", "center"),
    # US — magazines
    "theatlantic.com": OutletInfo("The Atlantic", "US", "magazine", "left"),
    "newyorker.com": OutletInfo("The New Yorker", "US", "magazine", "left"),
    "nationalreview.com": OutletInfo("National Review", "US", "magazine", "right"),
    "motherjones.com": OutletInfo("Mother Jones", "US", "magazine", "left"),
    # US — digital
    "politico.com": OutletInfo("Politico", "US", "digital", "center-left"),
    "axios.com": OutletInfo("Axios", "US", "digital", "center"),
    "vox.com": OutletInfo("Vox", "US", "digital", "left"),
    "thehill.com": OutletInfo("The Hill", "US", "digital", "center"),
    "huffpost.com": OutletInfo("HuffPost", "US", "digital", "left"),
    "propublica.org": OutletInfo("ProPublica", "US", "digital", "center-left"),
    "theintercept.com": OutletInfo("The Intercept", "US", "digital", "left"),
    "thedailywire.com": OutletInfo("The Daily Wire", "US", "digital", "right"),
    "breitbart.com": OutletInfo("Breitbart", "US", "digital", "right"),
    # US — financial
    "bloomberg.com": OutletInfo("Bloomberg", "US", "newspaper", "center"),
    # UK
    "reuters.com": OutletInfo("Reuters", "UK", "wire", "center"),
    "bbc.com": OutletInfo("BBC News", "UK", "broadcaster", "center"),
    "bbc.co.uk": OutletInfo("BBC News", "UK", "broadcaster", "center"),
    "theguardian.com": OutletInfo("The Guardian", "UK", "newspaper", "center-left"),
    "ft.com": OutletInfo("Financial Times", "UK", "newspaper", "center-right"),
    "thetimes.co.uk": OutletInfo("The Times", "UK", "newspaper", "center-right"),
    "telegraph.co.uk": OutletInfo("The Telegraph", "UK", "newspaper", "right"),
    "independent.co.uk": OutletInfo("The Independent", "UK", "digital", "center-left"),
    "dailymail.co.uk": OutletInfo("Daily Mail", "UK", "newspaper", "right"),
    "economist.com": OutletInfo("The Economist", "UK", "magazine", "center"),
    "gbnews.com": OutletInfo("GB News", "UK", "broadcaster", "right"),
    # Other — international
    "afp.com": OutletInfo("Agence France-Presse", "FR", "wire", "center"),
    "lemonde.fr": OutletInfo("Le Monde", "FR", "newspaper", "center-left"),
    "spiegel.de": OutletInfo("Der Spiegel", "DE", "magazine", "center-left"),
    "elpais.com": OutletInfo("El País", "ES", "newspaper", "center-left"),
    "globeandmail.com": OutletInfo("The Globe and Mail", "CA", "newspaper", "center"),
    "cbc.ca": OutletInfo("CBC News", "CA", "broadcaster", "center-left"),
    "abc.net.au": OutletInfo("ABC News (Australia)", "AU", "broadcaster", "center-left"),
    "smh.com.au": OutletInfo("Sydney Morning Herald", "AU", "newspaper", "center-left"),
    # No clear consensus — left as None on purpose:
    "aljazeera.com": OutletInfo("Al Jazeera", "QA", "broadcaster"),
    "scmp.com": OutletInfo("South China Morning Post", "HK", "newspaper"),
    "japantimes.co.jp": OutletInfo("The Japan Times", "JP", "newspaper", "center"),
    "ndtv.com": OutletInfo("NDTV", "IN", "broadcaster"),
    "thehindu.com": OutletInfo("The Hindu", "IN", "newspaper", "center-left"),
}


def lookup(domain: str) -> Optional[OutletInfo]:
    """Return registry info for a domain, or None if unknown."""
    return _REGISTRY.get(domain)


def display_name(domain: str) -> str:
    """Friendly name if known, else the bare domain."""
    info = _REGISTRY.get(domain)
    return info.name if info else domain
