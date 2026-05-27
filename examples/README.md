# Example queries

This directory holds reproducible inputs for the kind of cross-outlet
comparison the tool is built for, plus notes on the scope limits you
need to know about before running them.

## What the GDELT path can and cannot do

`--search` goes through GDELT, whose article archive starts **February
2015**. Anything older than that is invisible to GDELT regardless of
how wide a `--days` window you pass. In practice:

- Events 2015 → today: GDELT works. Use `--days N` to pick a window
  (default 14; pass `--days 0` to disable the window for a topic that
  has been running for years).
- Events before 2015 (Vietnam War, Pentagon Papers, Iraq War, 2008
  financial crisis, Charlie Hebdo, etc.): GDELT will not return
  anything useful. Use the **curated-URLs path** below.

## Curated URLs for historical case studies

`--urls-file path/to/file.urls` makes the tool analyze a list of URLs
you supply directly, with no GDELT lookup. Lines starting with `#` are
ignored. This is how you do a Manufacturing-Consent-style historical
case study:

1. Pick the event and the dates of interest.
2. For each outlet you want to represent, find the original article
   on the public web. If the publisher's archive is paywalled or has
   moved, use the Internet Archive's Wayback Machine
   (`https://web.archive.org/web/<timestamp>/<original-url>`); the
   page-extractor `trafilatura` reads Wayback snapshots fine.
3. Put one URL per line in a `.urls` file. Add a `# title — outlet —
   date` comment above each URL so the file documents itself.
4. Run:
   ```
   python -m news_lens \
       --urls-file examples/your_case.urls \
       --ollama --model qwen3:8b --max-concurrency 1 \
       --html your_case.html
   ```
   You don't pass `--days` or `--search` on a curated-URLs run.

## Files in this directory

- **`vietnam_gulf_of_tonkin.urls`** — template for the canonical
  Manufacturing-Consent case study (Gulf of Tonkin, August 1964). The
  file is a template: it contains commented placeholder lines naming
  the articles a real comparison would include (NYT lead editorials,
  AP wire copy, *Le Monde*, North Vietnamese state press, etc.) but no
  URLs that I have verified. Before running, replace each placeholder
  with a Wayback Machine URL pointing to that article, then drop the
  comments-only file through the curated-URLs workflow above.
- **`ukraine_feb_2022.urls`** — a workable post-2015 alternative for
  testing cross-outlet framing divergence today. State-affiliated
  (RT/Sputnik via Wayback), Western mainstream, and Russian
  independent (Meduza, Novaya Gazeta) covering the same first week.
  Replace any link rot you find with a Wayback snapshot.

## When the comparison is meaningful

For any of these to produce a useful matrix:

- ≥ 4 outlets in the sample (one outlet means no comparison; the
  sample banner now warns about this loudly).
- The outlets actually cover the same event (the date-filter and
  title-cosine clustering on the GDELT path enforce this; on the
  curated path it is on you).
- The model can keep up. Qwen3:8B on CPU with `--max-concurrency 1`
  is the conservative baseline; GPU offloading is dramatically faster
  and more reliable.

## What the report can and cannot tell you

The matrix surfaces what each outlet *said*, what each *omitted*, and
how each *framed* what it said. It cannot tell you what is true.
Manufacturing Consent's deeper move — comparing wartime framing
against later-declassified record — requires data the tool does not
ingest. That comparison is on the reader; the tool's job is to make
the wartime framing legible, not to adjudicate it.
