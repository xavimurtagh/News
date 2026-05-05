"""Static lookup of well-known news outlets.

Friendly names, country, and outlet type for the most common sources.
Falls back to the bare domain for unknown outlets — the registry is for
display polish, not gating.

Bias / lean ratings are deliberately omitted: those are real datasets
maintained by AllSides, Ad Fontes, MBFC, and others. Inventing or
approximating them here would launder my own subjective takes as data.
A future integration can plug a real source in via the same lookup
interface.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class OutletInfo(NamedTuple):
    name: str
    country: str
    outlet_type: str  # newspaper | wire | broadcaster | magazine | digital


_REGISTRY: dict[str, OutletInfo] = {
    # US — newspapers
    "nytimes.com": OutletInfo("The New York Times", "US", "newspaper"),
    "wsj.com": OutletInfo("The Wall Street Journal", "US", "newspaper"),
    "washingtonpost.com": OutletInfo("The Washington Post", "US", "newspaper"),
    "usatoday.com": OutletInfo("USA Today", "US", "newspaper"),
    "latimes.com": OutletInfo("Los Angeles Times", "US", "newspaper"),
    "chicagotribune.com": OutletInfo("Chicago Tribune", "US", "newspaper"),
    "bostonglobe.com": OutletInfo("The Boston Globe", "US", "newspaper"),
    "nypost.com": OutletInfo("New York Post", "US", "newspaper"),
    # US — wire services
    "apnews.com": OutletInfo("Associated Press", "US", "wire"),
    # US — broadcasters
    "cnn.com": OutletInfo("CNN", "US", "broadcaster"),
    "foxnews.com": OutletInfo("Fox News", "US", "broadcaster"),
    "abcnews.go.com": OutletInfo("ABC News", "US", "broadcaster"),
    "nbcnews.com": OutletInfo("NBC News", "US", "broadcaster"),
    "cbsnews.com": OutletInfo("CBS News", "US", "broadcaster"),
    "msnbc.com": OutletInfo("MSNBC", "US", "broadcaster"),
    "npr.org": OutletInfo("NPR", "US", "broadcaster"),
    "pbs.org": OutletInfo("PBS NewsHour", "US", "broadcaster"),
    # US — magazines
    "theatlantic.com": OutletInfo("The Atlantic", "US", "magazine"),
    "newyorker.com": OutletInfo("The New Yorker", "US", "magazine"),
    "nationalreview.com": OutletInfo("National Review", "US", "magazine"),
    "motherjones.com": OutletInfo("Mother Jones", "US", "magazine"),
    # US — digital
    "politico.com": OutletInfo("Politico", "US", "digital"),
    "axios.com": OutletInfo("Axios", "US", "digital"),
    "vox.com": OutletInfo("Vox", "US", "digital"),
    "thehill.com": OutletInfo("The Hill", "US", "digital"),
    "huffpost.com": OutletInfo("HuffPost", "US", "digital"),
    "propublica.org": OutletInfo("ProPublica", "US", "digital"),
    "theintercept.com": OutletInfo("The Intercept", "US", "digital"),
    "thedailywire.com": OutletInfo("The Daily Wire", "US", "digital"),
    "breitbart.com": OutletInfo("Breitbart", "US", "digital"),
    # US — financial
    "bloomberg.com": OutletInfo("Bloomberg", "US", "newspaper"),
    # UK
    "reuters.com": OutletInfo("Reuters", "UK", "wire"),
    "bbc.com": OutletInfo("BBC News", "UK", "broadcaster"),
    "bbc.co.uk": OutletInfo("BBC News", "UK", "broadcaster"),
    "theguardian.com": OutletInfo("The Guardian", "UK", "newspaper"),
    "ft.com": OutletInfo("Financial Times", "UK", "newspaper"),
    "thetimes.co.uk": OutletInfo("The Times", "UK", "newspaper"),
    "telegraph.co.uk": OutletInfo("The Telegraph", "UK", "newspaper"),
    "independent.co.uk": OutletInfo("The Independent", "UK", "digital"),
    "dailymail.co.uk": OutletInfo("Daily Mail", "UK", "newspaper"),
    "economist.com": OutletInfo("The Economist", "UK", "magazine"),
    # Other
    "afp.com": OutletInfo("Agence France-Presse", "FR", "wire"),
    "lemonde.fr": OutletInfo("Le Monde", "FR", "newspaper"),
    "spiegel.de": OutletInfo("Der Spiegel", "DE", "magazine"),
    "elpais.com": OutletInfo("El País", "ES", "newspaper"),
    "globeandmail.com": OutletInfo("The Globe and Mail", "CA", "newspaper"),
    "cbc.ca": OutletInfo("CBC News", "CA", "broadcaster"),
    "abc.net.au": OutletInfo("ABC News (Australia)", "AU", "broadcaster"),
    "smh.com.au": OutletInfo("Sydney Morning Herald", "AU", "newspaper"),
    "aljazeera.com": OutletInfo("Al Jazeera", "QA", "broadcaster"),
    "scmp.com": OutletInfo("South China Morning Post", "HK", "newspaper"),
    "japantimes.co.jp": OutletInfo("The Japan Times", "JP", "newspaper"),
    "ndtv.com": OutletInfo("NDTV", "IN", "broadcaster"),
    "thehindu.com": OutletInfo("The Hindu", "IN", "newspaper"),
}


def lookup(domain: str) -> Optional[OutletInfo]:
    """Return registry info for a domain, or None if unknown."""
    return _REGISTRY.get(domain)


def display_name(domain: str) -> str:
    """Friendly name if known, else the bare domain."""
    info = _REGISTRY.get(domain)
    return info.name if info else domain
