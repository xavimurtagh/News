"""Build a synthetic CoverageMatrix and render JSON + HTML.

No API key required. Useful for previewing the end-to-end output without
running the live pipeline. Regenerates examples/coverage.json and
examples/coverage.html each time.

    python examples/synthetic_demo.py

Five fictional outlets cover the same fictional executive order. The matrix
exercises every tier (universal / majority / disputed / attributed-only /
single-sourced), all four cell statuses, loaded vocabulary with verbatim
citations, per-outlet position emphasis, and one wire-syndication pair
(reuters.com + abcnews.go.com share most sentences).
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
    SyndicationGroup,
    TieredClaim,
)
from news_lens.render import render_html
from news_lens.syndication import detect_syndication


PUB_DATE = datetime(2026, 5, 4, 16, 30, tzinfo=timezone.utc)


NYT_BODY = """The President signed Executive Order 14123 at a Rose Garden ceremony on Saturday afternoon, capping months of internal debate over the legal scope of executive authority on border policy.

The order takes effect immediately and directs federal agencies to expedite removal proceedings while expanding asylum-screening criteria, according to the text released by the White House counsel's office.

An estimated 5 million people are expected to be affected by the new policy, administration officials said.

Several legal scholars said the order exceeded the executive branch's authority and was likely to face immediate legal challenge in the courts.

"This is an unconstitutional overreach by an executive branch operating without congressional authority," the American Civil Liberties Union said in a statement released hours after the signing.

The order's sweeping language drew sharp pushback from immigration advocates and from members of the President's own party.

A senior aide to the president resigned Saturday afternoon in protest of the order, according to two people familiar with the matter who spoke on condition of anonymity.

The resignation, which had not been previously reported, marked the first public break within the administration over the policy.

Lawmakers on both sides of the aisle said they expected the order to be challenged in federal court within days.""".strip()


WSJ_BODY = """The President signed an executive order Saturday at the White House, taking effect immediately and reshaping how federal agencies process border claims.

Markets reacted with a muted decline, as analysts focused on the order's labor-market implications and the short-term costs to companies in agriculture and construction.

Administration officials said the policy would directly affect roughly 1.2 million people, a figure significantly lower than estimates circulated by some advocacy groups.

Wall Street analysts noted that the order's enforcement provisions could affect quarterly hiring patterns in low-wage industries.

Democratic lawmakers vowed to challenge the order in court, calling it an unconstitutional overreach.

A senior Republican on the Judiciary Committee said the order was a long-overdue corrective and predicted it would survive legal challenges.

The S&P 500 closed down 0.4 percent, with construction and agricultural-services stocks leading the decline.""".strip()


REUTERS_BODY = """U.S. President signed an executive order on border policy on Saturday, the White House said in a statement.

The order takes effect immediately, the White House said.

A senior administration official, speaking on condition of anonymity, said the policy could affect up to 5 million people.

The official did not provide a precise estimate, citing the difficulty of projecting how the new screening criteria would apply.

The American Civil Liberties Union called the order unconstitutional in a statement on Saturday, vowing to file suit in federal court next week.

The order is the latest in a series of executive actions on immigration policy issued by the administration this year.""".strip()


ABC_VIA_REUTERS_BODY = """ABC News is running the following report from the Reuters wire on the executive order.

U.S. President signed an executive order on border policy on Saturday, the White House said in a statement.

The order takes effect immediately, the White House said.

A senior administration official, speaking on condition of anonymity, said the policy could affect up to 5 million people.

The official did not provide a precise estimate, citing the difficulty of projecting how the new screening criteria would apply.

The American Civil Liberties Union called the order unconstitutional in a statement on Saturday, vowing to file suit in federal court next week.

The order is the latest in a series of executive actions on immigration policy issued by the administration this year.""".strip()


FOX_BODY = """The President took bold action Saturday, signing a new executive order to secure the southern border and crack down on illegal crossings.

The order takes effect immediately, the White House said, and is the most sweeping border-enforcement directive in years.

The President was joined by Border Patrol union leaders at the signing ceremony.

The new directive prioritizes detention capacity for repeat crossers and authorizes additional detention facilities along the southern border.

A Border Patrol union official praised the order as a long-needed restoration of the rule of law.

The order delivers on a campaign promise to take decisive action on what the President has called a national-security emergency at the border.""".strip()


ARTICLES = [
    Article(
        id="nyt", url="https://nytimes.com/2026/05/04/border-order",
        outlet_domain="nytimes.com",
        title="President Signs Sweeping Order on Border Policy",
        byline="Reporter Name",
        published_at=PUB_DATE, fetched_at=PUB_DATE,
        body=NYT_BODY, paragraph_count=9,
    ),
    Article(
        id="wsj", url="https://wsj.com/articles/border-order",
        outlet_domain="wsj.com",
        title="Border Executive Order Takes Effect; Markets Mixed",
        byline="Reporter Name",
        published_at=PUB_DATE, fetched_at=PUB_DATE,
        body=WSJ_BODY, paragraph_count=7,
    ),
    Article(
        id="reut", url="https://reuters.com/world/us/border-order",
        outlet_domain="reuters.com",
        title="U.S. President Signs Border Executive Order",
        byline="Reuters Staff",
        published_at=PUB_DATE, fetched_at=PUB_DATE,
        body=REUTERS_BODY, paragraph_count=6,
    ),
    Article(
        id="abc", url="https://abcnews.go.com/politics/border-order",
        outlet_domain="abcnews.go.com",
        title="U.S. President Signs Border Order, White House Says",
        byline="ABC News",
        published_at=PUB_DATE, fetched_at=PUB_DATE,
        body=ABC_VIA_REUTERS_BODY, paragraph_count=7,
    ),
    Article(
        id="fox", url="https://foxnews.com/politics/border-order",
        outlet_domain="foxnews.com",
        title="President Acts to Secure the Border with Bold Executive Order",
        byline="Reporter Name",
        published_at=PUB_DATE, fetched_at=PUB_DATE,
        body=FOX_BODY, paragraph_count=6,
    ),
]


def _cov(domain, aid, status, quote=None, attr=None, position=None):
    return OutletCoverage(
        outlet_domain=domain, article_id=aid, status=status,
        source_quote=quote, attributed_to=attr, position=position,
    )


CLAIMS = [
    TieredClaim(
        canonical_text="The U.S. President signed an executive order on border policy on May 4, 2026.",
        tier=ConsensusTier.UNIVERSAL,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "The President signed Executive Order 14123 at a Rose Garden ceremony on Saturday afternoon, capping months of internal debate over the legal scope of executive authority on border policy.",
                 position=1),
            _cov("wsj.com", "wsj", CoverageStatus.ASSERTED,
                 "The President signed an executive order Saturday at the White House, taking effect immediately and reshaping how federal agencies process border claims.",
                 position=1),
            _cov("reuters.com", "reut", CoverageStatus.ASSERTED,
                 "U.S. President signed an executive order on border policy on Saturday, the White House said in a statement.",
                 position=1),
            _cov("abcnews.go.com", "abc", CoverageStatus.ASSERTED,
                 "U.S. President signed an executive order on border policy on Saturday, the White House said in a statement.",
                 position=2),
            _cov("foxnews.com", "fox", CoverageStatus.ASSERTED,
                 "The President took bold action Saturday, signing a new executive order to secure the southern border and crack down on illegal crossings.",
                 position=1),
        ],
    ),
    TieredClaim(
        canonical_text="The order takes effect immediately upon signing.",
        tier=ConsensusTier.MAJORITY,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "The order takes effect immediately and directs federal agencies to expedite removal proceedings while expanding asylum-screening criteria, according to the text released by the White House counsel's office.",
                 position=2),
            _cov("wsj.com", "wsj", CoverageStatus.ASSERTED,
                 "The President signed an executive order Saturday at the White House, taking effect immediately and reshaping how federal agencies process border claims.",
                 position=1),
            _cov("reuters.com", "reut", CoverageStatus.ASSERTED,
                 "The order takes effect immediately, the White House said.",
                 position=2),
            _cov("abcnews.go.com", "abc", CoverageStatus.ASSERTED,
                 "The order takes effect immediately, the White House said.",
                 position=3),
            _cov("foxnews.com", "fox", CoverageStatus.ASSERTED,
                 "The order takes effect immediately, the White House said, and is the most sweeping border-enforcement directive in years.",
                 position=2),
        ],
    ),
    TieredClaim(
        canonical_text="An estimated number of people will be affected by the order.",
        tier=ConsensusTier.DISPUTED,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "An estimated 5 million people are expected to be affected by the new policy, administration officials said.",
                 position=3),
            _cov("wsj.com", "wsj", CoverageStatus.CONTRADICTED,
                 "Administration officials said the policy would directly affect roughly 1.2 million people, a figure significantly lower than estimates circulated by some advocacy groups.",
                 position=3),
            _cov("reuters.com", "reut", CoverageStatus.ATTRIBUTED,
                 "A senior administration official, speaking on condition of anonymity, said the policy could affect up to 5 million people.",
                 attr="senior administration official", position=3),
            _cov("abcnews.go.com", "abc", CoverageStatus.ATTRIBUTED,
                 "A senior administration official, speaking on condition of anonymity, said the policy could affect up to 5 million people.",
                 attr="senior administration official", position=4),
            _cov("foxnews.com", "fox", CoverageStatus.OMITTED),
        ],
    ),
    TieredClaim(
        canonical_text="Critics say the order is unconstitutional.",
        tier=ConsensusTier.ATTRIBUTED_ONLY,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ATTRIBUTED,
                 "\"This is an unconstitutional overreach by an executive branch operating without congressional authority,\" the American Civil Liberties Union said in a statement released hours after the signing.",
                 attr="American Civil Liberties Union", position=5),
            _cov("wsj.com", "wsj", CoverageStatus.ATTRIBUTED,
                 "Democratic lawmakers vowed to challenge the order in court, calling it an unconstitutional overreach.",
                 attr="Democratic lawmakers", position=5),
            _cov("reuters.com", "reut", CoverageStatus.ATTRIBUTED,
                 "The American Civil Liberties Union called the order unconstitutional in a statement on Saturday, vowing to file suit in federal court next week.",
                 attr="American Civil Liberties Union", position=5),
            _cov("abcnews.go.com", "abc", CoverageStatus.ATTRIBUTED,
                 "The American Civil Liberties Union called the order unconstitutional in a statement on Saturday, vowing to file suit in federal court next week.",
                 attr="American Civil Liberties Union", position=6),
            _cov("foxnews.com", "fox", CoverageStatus.OMITTED),
        ],
    ),
    TieredClaim(
        canonical_text="A senior aide resigned in protest of the order.",
        tier=ConsensusTier.SINGLE_SOURCED,
        outlets=[
            _cov("nytimes.com", "nyt", CoverageStatus.ASSERTED,
                 "A senior aide to the president resigned Saturday afternoon in protest of the order, according to two people familiar with the matter who spoke on condition of anonymity.",
                 position=7),
            _cov("wsj.com", "wsj", CoverageStatus.OMITTED),
            _cov("reuters.com", "reut", CoverageStatus.OMITTED),
            _cov("abcnews.go.com", "abc", CoverageStatus.OMITTED),
            _cov("foxnews.com", "fox", CoverageStatus.OMITTED),
        ],
    ),
]


LENSES = [
    ArticleLens(
        article_id="nyt", outlet_domain="nytimes.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.NEGATIVE,
            stance_summary="Treats the order as a controversial executive overreach, centering critic voices and surfacing internal dissent.",
            loaded_terms=[
                LoadedTerm(
                    term="sweeping",
                    neutral_alternative="broad",
                    in_sentence="The order's sweeping language drew sharp pushback from immigration advocates and from members of the President's own party.",
                ),
            ],
            sources_quoted=["legal scholars", "American Civil Liberties Union", "two people familiar with the matter", "White House counsel's office"],
        ),
    ),
    ArticleLens(
        article_id="wsj", outlet_domain="wsj.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.MIXED,
            stance_summary="Frames the news through a market-reaction lens; emphasizes economic implications over policy substance.",
            loaded_terms=[],
            sources_quoted=["Wall Street analysts", "Democratic lawmakers", "Administration officials", "senior Republican on the Judiciary Committee"],
        ),
    ),
    ArticleLens(
        article_id="reut", outlet_domain="reuters.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.NEUTRAL,
            stance_summary="Wire-style summary attributing every statement to its source; minimal characterization.",
            loaded_terms=[],
            sources_quoted=["White House", "senior administration official", "American Civil Liberties Union"],
        ),
    ),
    ArticleLens(
        article_id="abc", outlet_domain="abcnews.go.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.NEUTRAL,
            stance_summary="Reposts the Reuters wire under an ABC News byline with a one-line attribution intro.",
            loaded_terms=[],
            sources_quoted=["White House", "senior administration official", "American Civil Liberties Union"],
        ),
    ),
    ArticleLens(
        article_id="fox", outlet_domain="foxnews.com",
        signals=LensSignals(
            headline_framing=HeadlineFraming.POSITIVE,
            stance_summary="Frames the order favorably as decisive border-security action; omits critic perspectives and centers supportive voices.",
            loaded_terms=[
                LoadedTerm(
                    term="bold action",
                    neutral_alternative="action",
                    in_sentence="The President took bold action Saturday, signing a new executive order to secure the southern border and crack down on illegal crossings.",
                ),
                LoadedTerm(
                    term="crack down on illegal crossings",
                    neutral_alternative="enforce border laws",
                    in_sentence="The President took bold action Saturday, signing a new executive order to secure the southern border and crack down on illegal crossings.",
                ),
                LoadedTerm(
                    term="rule of law",
                    neutral_alternative="immigration enforcement",
                    in_sentence="A Border Patrol union official praised the order as a long-needed restoration of the rule of law.",
                ),
            ],
            sources_quoted=["White House", "Border Patrol union leaders", "Border Patrol union official"],
        ),
    ),
]


def main() -> None:
    syndication_groups = detect_syndication(ARTICLES)
    matrix = CoverageMatrix(
        articles=ARTICLES,
        claims=CLAIMS,
        lenses=LENSES,
        syndication_groups=syndication_groups,
    )
    out_dir = Path(__file__).parent
    (out_dir / "coverage.json").write_text(matrix.model_dump_json(indent=2))
    (out_dir / "coverage.html").write_text(render_html(matrix))
    print(f"Wrote {out_dir / 'coverage.json'}")
    print(f"Wrote {out_dir / 'coverage.html'}")
    if syndication_groups:
        for g in syndication_groups:
            print(
                f"  syndication: {g.article_ids} (similarity {g.similarity:.2f})"
            )


if __name__ == "__main__":
    main()
