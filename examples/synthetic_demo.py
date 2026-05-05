"""Build a synthetic CoverageMatrix and render JSON + HTML.

No API key required. Useful for previewing the end-to-end output without
running the live pipeline. Regenerates examples/coverage.json and
examples/coverage.html each time.

    python examples/synthetic_demo.py

The matrix imitates four outlets covering the same fictional executive
order. It exercises every tier (universal / majority / disputed /
attributed-only / single-sourced), three of the four cell statuses,
loaded vocabulary with verbatim citations, and per-outlet position
emphasis so the renderer can be evaluated end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from news_lens.models import (
    Article,
    ArticleLens,
    ConsensusTier,
    CoverageMatrix,
    CoverageStatus,
    HeadlineFraming,
    LensSignals,
    LoadedTerm,
    OutletCoverage,
    TieredClaim,
)
from news_lens.render import render_html


PUB_DATE = datetime(2026, 5, 4, 16, 30, tzinfo=timezone.utc)


def _article(
    aid: str, outlet: str, title: str, paragraph_count: int, body: str = "(synthetic body)"
) -> Article:
    return Article(
        id=aid,
        url=f"https://{outlet}/2026/05/04/border-order",
        outlet_domain=outlet,
        title=title,
        byline="Reporter Name",
        published_at=PUB_DATE,
        fetched_at=PUB_DATE,
        body=body,
        paragraph_count=paragraph_count,
    )


def _cov(
    domain: str,
    aid: str,
    status: CoverageStatus,
    quote: str | None = None,
    attr: str | None = None,
    position: int | None = None,
) -> OutletCoverage:
    return OutletCoverage(
        outlet_domain=domain,
        article_id=aid,
        status=status,
        source_quote=quote,
        attributed_to=attr,
        position=position,
    )


ARTICLES = [
    _article("nyt", "nytimes.com", "President Signs Sweeping Order on Border Policy", 18),
    _article("wsj", "wsj.com", "Border Executive Order Takes Effect; Markets Mixed", 14),
    _article("reut", "reuters.com", "U.S. President Signs Border Executive Order", 9),
    _article("fox", "foxnews.com", "President Acts to Secure the Border with Bold Executive Order", 16),
]


CLAIMS = [
    TieredClaim(
        canonical_text="The U.S. President signed an executive order on border policy on May 4, 2026.",
        tier=ConsensusTier.UNIVERSAL,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "The President signed Executive Order 14123 at a Rose Garden ceremony on Saturday.",
                 position=1),
            _cov("wsj.com", "wsj", CoverageStatus.ASSERTED,
                 "President signed an executive order Saturday at the White House, taking effect immediately.",
                 position=1),
            _cov("reuters.com", "reut", CoverageStatus.ASSERTED,
                 "U.S. President signed an executive order on border policy on Saturday, the White House said.",
                 position=1),
            _cov("foxnews.com", "fox", CoverageStatus.ASSERTED,
                 "The President took bold action Saturday, signing a new executive order to secure the southern border.",
                 position=1),
        ],
    ),
    TieredClaim(
        canonical_text="The order takes effect immediately upon signing.",
        tier=ConsensusTier.MAJORITY,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "The order is effective immediately, according to the text released by the White House counsel's office.",
                 position=3),
            _cov("wsj.com", "wsj", CoverageStatus.ASSERTED,
                 "President signed an executive order Saturday at the White House, taking effect immediately.",
                 position=1),
            _cov("foxnews.com", "fox", CoverageStatus.ASSERTED,
                 "The order takes effect immediately, the White House said.",
                 position=2),
            _cov("reuters.com", "reut", CoverageStatus.OMITTED),
        ],
    ),
    TieredClaim(
        canonical_text="An estimated number of people will be affected by the order.",
        tier=ConsensusTier.DISPUTED,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "An estimated 5 million people are expected to be affected by the new policy.",
                 position=4),
            _cov("wsj.com", "wsj", CoverageStatus.CONTRADICTED,
                 "Administration officials said the policy would directly affect roughly 1.2 million people.",
                 position=5),
            _cov("reuters.com", "reut", CoverageStatus.ATTRIBUTED,
                 "A senior administration official said the policy could affect up to 5 million people.",
                 attr="senior administration official",
                 position=4),
            _cov("foxnews.com", "fox", CoverageStatus.OMITTED),
        ],
    ),
    TieredClaim(
        canonical_text="Critics say the order is unconstitutional.",
        tier=ConsensusTier.ATTRIBUTED_ONLY,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ATTRIBUTED,
                 "Several legal scholars said the order exceeded the executive branch's authority and was likely to face immediate legal challenge.",
                 attr="legal scholars",
                 position=6),
            _cov("reuters.com", "reut", CoverageStatus.ATTRIBUTED,
                 "The American Civil Liberties Union called the order unconstitutional in a statement on Saturday.",
                 attr="American Civil Liberties Union",
                 position=6),
            _cov("wsj.com", "wsj", CoverageStatus.ATTRIBUTED,
                 "Democratic lawmakers vowed to challenge the order in court, calling it an unconstitutional overreach.",
                 attr="Democratic lawmakers",
                 position=11),
            _cov("foxnews.com", "fox", CoverageStatus.OMITTED),
        ],
    ),
    TieredClaim(
        canonical_text="A senior aide resigned in protest of the order.",
        tier=ConsensusTier.SINGLE_SOURCED,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "A senior aide to the president resigned Saturday afternoon in protest of the order, according to two people familiar with the matter.",
                 position=14),
            _cov("wsj.com", "wsj", CoverageStatus.OMITTED),
            _cov("reuters.com", "reut", CoverageStatus.OMITTED),
            _cov("foxnews.com", "fox", CoverageStatus.OMITTED),
        ],
    ),
]


LENSES = [
    ArticleLens(
        article_id="nyt",
        outlet_domain="nytimes.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.NEGATIVE,
            stance_summary="Treats the order as a controversial executive overreach, centering critic voices and legal challenges.",
            loaded_terms=[
                LoadedTerm(
                    term="sweeping",
                    neutral_alternative="broad",
                    in_sentence="The President signed Executive Order 14123 at a Rose Garden ceremony on Saturday.",
                ),
            ],
            sources_quoted=["legal scholars", "ACLU", "two people familiar with the matter", "White House counsel's office"],
        ),
    ),
    ArticleLens(
        article_id="wsj",
        outlet_domain="wsj.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.MIXED,
            stance_summary="Frames the news through a market-reaction lens; emphasizes economic implications over policy substance.",
            loaded_terms=[],
            sources_quoted=["Wall Street analysts", "Democratic lawmakers", "Administration officials"],
        ),
    ),
    ArticleLens(
        article_id="reut",
        outlet_domain="reuters.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.NEUTRAL,
            stance_summary="Wire-style summary attributing every statement to its source; minimal characterization.",
            loaded_terms=[],
            sources_quoted=["White House", "senior administration official", "American Civil Liberties Union"],
        ),
    ),
    ArticleLens(
        article_id="fox",
        outlet_domain="foxnews.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.POSITIVE,
            stance_summary="Frames the order favorably as decisive border-security action; omits critic perspectives.",
            loaded_terms=[
                LoadedTerm(
                    term="bold action",
                    neutral_alternative="action",
                    in_sentence="The President took bold action Saturday, signing a new executive order to secure the southern border.",
                ),
                LoadedTerm(
                    term="secure",
                    neutral_alternative="restrict crossing into",
                    in_sentence="The President took bold action Saturday, signing a new executive order to secure the southern border.",
                ),
            ],
            sources_quoted=["White House", "border patrol union"],
        ),
    ),
]


def main() -> None:
    matrix = CoverageMatrix(articles=ARTICLES, claims=CLAIMS, lenses=LENSES)
    out_dir = Path(__file__).parent
    (out_dir / "coverage.json").write_text(matrix.model_dump_json(indent=2))
    (out_dir / "coverage.html").write_text(render_html(matrix))
    print(f"Wrote {out_dir / 'coverage.json'}")
    print(f"Wrote {out_dir / 'coverage.html'}")


if __name__ == "__main__":
    main()
