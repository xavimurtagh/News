# Outreach: how to make this known

The tool is worth nothing if the right people don't find it. This is a
curated checklist of where to surface it and how, sequenced from most
likely to land to most ambitious. Everything here assumes you have at
least one *populated* report you're proud of — outreach without a demo
report is a pitch about a tool nobody can see working.

## The launch principle: show one specific finding, not the tool

The tool is the artefact you make; **the report is the artefact you
share**. Posts and pitches that say "I built a thing that compares how
outlets cover stories" perform far worse than "here is what the tool
revealed when I ran it on the Polanski coverage" — because the second
one is news, and journalists / media-watchers respond to news.

Pick one report. Identify one specific finding (e.g. "X of 12 outlets
quoted the same single source; one outlet edited the wire copy to
contradict the others"). Write the pitch around the finding. Link to
the tool second, as the how-it-was-done.

The Polanski sample (16 articles · 13 independent voices · 83
canonical claims, all five tiers populated) is the cleanest current
demonstration; it surfaces real consensus, real disagreement, and the
Forward / Middle East Eye / Haaretz / mainstream UK split.

## Where to post first (low ceremony)

These are individual posts you can do today.

### Bluesky
Where most working journalists migrated. Tag generously; threads
work better than single posts here.

- Suggested handles to tag in a launch post: `@niemanlab.bsky.social`,
  `@poynter.org`, `@pressgazette.bsky.social`, `@fair.org`.
- Use the journalism custom feeds (`#journalism`, `#medianews`,
  `#dataviz`).
- Lead with the finding, post one screenshot, link to the report on
  your published site. **Not** the GitHub repo.

### Mastodon
The `journa.host` instance is where journalism-Mastodon clusters; the
`mastodon.social` instance reaches a broader tech audience.

- Cross-post the same thread shape from Bluesky.
- Tag `#journalism`, `#OpenData`, `#MediaAnalysis`.

### Hacker News (Show HN)
Hits when the finding is unambiguous and the tool is technically
interesting. Manufacturing-Consent-via-LLM-and-embeddings is
technically interesting; an empty-matrix report is not. Submit a
Show HN only once, only when you have a report worth defending in
comments.

- Title pattern: `Show HN: News Lens — see how 16 outlets covered <X>
  side-by-side`.
- Lead with the report URL, then the repo. Be ready to answer
  "isn't this just NewsGuard / AllSides / Ground.News?" — your
  answer is the propaganda-model framing, the verbatim citations, and
  the per-claim provenance / grounding flags.

### Targeted subreddits

- `/r/journalism` — moderate, professional. Lead with the report and
  the finding; mention the tool only as the how.
- `/r/dataisbeautiful` — broad reach. Single-image post of the
  Coverage Matrix screenshot with a clean headline ("Same Polanski
  story, 16 outlets, 83 claims — universal consensus on 3, contradiction
  on 2"); link to the live report in the comments.
- `/r/MediaCritique` — small but exactly aligned. Long-form welcome.

## Where to pitch (higher value, slower)

These need an actual outreach email or DM.

### Journalism / press community
- **Nieman Lab** (`tips@niemanlab.org`) — covers tools, methods, and
  journalism research. Pitch as: "open-source tool produces this
  output for arbitrary stories." Attach the report.
- **Poynter** — similar audience; `feedback@poynter.org` for the news
  tips, or DM specific writers covering AI / journalism tools.
- **Press Gazette** — UK media trade press; particularly interested
  in ownership concentration and wire-syndication stories. The
  Newsquest 14/22 finding from the earlier Corbyn sample would land.
- **Reuters Institute for the Study of Journalism** (Oxford) — they
  publish the Digital News Report. Email
  `info@reutersinstitute.politics.ox.ac.uk` with the report and a
  short note on what's novel about the method.
- **The Conversation** (media desk) — if you're an academic or have
  an academic co-author, this is the highest-ROI venue. Pitch a piece
  around one finding.

### Media-criticism organisations
- **FAIR.org** — Manufacturing-Consent's own NYC home base. The tool's
  framing maps directly to their critique. Email
  `fair@fair.org` with the Polanski (or similar) report.
- **GIJN — Global Investigative Journalism Network**
  (`hello@gijn.org`) — investigative-journalism toolbox; they
  publish guides to tools. Submit via their tool-database form.
- **Bellingcat** — open-source investigation community. They're
  unlikely to publish a piece, but their Discord is where many OSINT
  journalists hang out and will share useful tools.
- **MediaWise / Knight Foundation** — funder-adjacent; if you ever
  want to apply for grant support, having reports in the world is the
  proof.

### Academic / curriculum
- **Columbia Journalism Review** (`cjr@columbia.edu`) — they cover
  journalism methods and tools.
- **City, University of London** journalism department — particularly
  the Centre for Editorial Research. They've used similar
  cross-outlet-comparison work in teaching.
- **Cardiff School of Journalism, Media and Culture** — heavy
  Manufacturing-Consent influence; media studies majors there will
  use this if they know it exists.
- **LSE Media and Communications** — academic; long-cycle but
  reaches researchers who write the textbooks.

A short email to one journalism-school professor saying "I built this;
your media-analysis seminar might find it useful; here's a worked
example" is one of the highest-leverage outreach moves available.

## The hardest sell first

If you have time for exactly one pitch, send it to **FAIR** or
**Press Gazette** with a *specific* run on a *specific* story that
revealed something a reader of those publications would care about.
The tool's value is in the analysis. The pitch should be a
journalism pitch, not a software pitch.

Example pitch shape:

> Subject: Coverage of the Corbyn / Greens by-election clustered around
> Newsquest wire copy — here's the matrix
>
> Hi [editor],
>
> I'm not pitching a feature; I built an open-source tool and want to
> show you what it surfaced on a recent story. Of 22 UK outlets the
> tool sampled covering the Gorton / Denton by-election, 14 were
> running identical Newsquest wire copy — but one of them edited
> their copy to contradict the others on the candidate's stance.
> The tool's matrix makes that visible at a glance.
>
> Report: https://your-site/reports/2026-05-gorton-denton.html
> Methodology: https://github.com/xavimurtagh/news
>
> If any of this is useful for your readers, happy to write the
> methodology up properly or pull the same lens on another story.
>
> [name]

That note is short, names a concrete finding, links to the report
before the repo, and offers to do more work. It is much more likely
to land than a generic "I built a media-analysis tool" note.

## What success looks like

- A single mention in Nieman Lab, Press Gazette, or The Conversation
  is more valuable than 1,000 GitHub stars. Optimise for one of those.
- A long-form thread on Bluesky with 10-50 reposts from journalism
  accounts is the next tier and is achievable from a single good
  report.
- A subreddit post that hits the front page of `/r/journalism` reaches
  the same audience as the press venues but without editorial
  legitimation.

## What to *not* do

- Don't post the bare GitHub URL with no demo report. The tool only
  makes sense once a reader sees the output.
- Don't claim the tool "detects misinformation" or "fact-checks". It
  doesn't. It makes the structure of coverage legible. Overclaiming
  burns credibility with the audiences that matter most.
- Don't run a single report on a contested story (Israel-Palestine,
  US elections, Ukraine) without being prepared to defend the source
  selection. Sample-shape is the first thing critics will attack;
  the sample banner is the answer to that, but be ready to explain it.
