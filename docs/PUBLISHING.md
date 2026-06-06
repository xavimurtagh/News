# Publishing reports to the public web

This is the from-clean-checkout guide to putting a curated set of News
Lens reports on the internet under your editorial control. The setup
is intentionally minimal: everything is static HTML, hosted on GitHub
Pages, deployed by an Action when you push.

## What you'll end up with

- **`https://<your-github-user>.github.io/<repo-name>/`** — a landing
  page listing every report in `docs/reports/`, newest first, with a
  search box.
- **Each report at `…/reports/<filename>.html`** — the existing
  self-contained HTML, unchanged.
- A clean URL you can share that previews correctly when posted to
  Bluesky, Mastodon, LinkedIn, Slack, etc. (the report carries OG /
  Twitter meta tags).

There is **no automation**. You run the tool locally, look at the
result, decide it's worth sharing, copy it into `docs/reports/`, and
push. The site rebuilds.

## One-time GitHub Pages setup

1. **Enable Pages on the repo.** `Settings` → `Pages`. Under "Source",
   pick **GitHub Actions** (not "Deploy from a branch"). Save.
2. **Confirm Actions permissions allow Pages writes.** `Settings` →
   `Actions` → `General` → "Workflow permissions" → ensure
   "Read and write permissions" is selected (or that the publish
   workflow is allowed under "Workflow permissions"). The workflow file
   already declares `permissions: pages: write`, so this is typically
   already in order.
3. **Push once.** The workflow at
   `.github/workflows/publish.yml` runs automatically on every push
   that touches `docs/`. The first run takes ~30s, builds an empty
   index page, and reports the live URL in the Actions summary.

## Publishing a report

```bash
# 1. Run the tool against a story you care about.
python -m news_lens \
    --search "wes streeting resignation labour" \
    --balance-spectrum --max-sources 10 \
    --ollama --model qwen3:8b --max-concurrency 1 \
    --label "Wes Streeting resignation, May 2026" \
    --html streeting.html

# 2. Inspect streeting.html locally. Does the matrix look right? Are
#    the ownership and voices sections useful?
xdg-open streeting.html  # or `open` on macOS

# 3. If you want to share it, copy into docs/reports/ and push.
cp streeting.html docs/reports/2026-05-streeting-resignation.html
git add docs/reports/2026-05-streeting-resignation.html
git commit -m "Publish: Wes Streeting resignation (May 2026)"
git push
```

The workflow detects the change under `docs/`, rebuilds the index, and
redeploys. Within ~30s the new report is live at
`/reports/2026-05-streeting-resignation.html` and a card appears on
the index page.

### Filename conventions

The index page sorts by the report's *generated* timestamp (embedded in
the HTML), not by filename. But the filename is what appears in the
URL — keep it short, dated, and slugified:

- ✅ `2026-05-streeting-resignation.html`
- ✅ `2026-04-ukraine-ceasefire-week-1.html`
- ❌ `streeting.html` (no date, no story)
- ❌ `report.html` (collides on second use)

### The `--label` flag

The label becomes the page `<title>` *and* the OG / Twitter card title
used by social previews. Set it whenever you run a report you might
publish. Without a label, the report falls back to "News Lens —
Coverage Matrix", which is generic and unhelpful in a share preview.

## Custom domain (optional)

GitHub Pages defaults to `https://<user>.github.io/<repo>/`. To use
your own domain:

1. Add a `CNAME` DNS record at your registrar pointing to
   `<user>.github.io.`
2. Rename `docs/CNAME.example` to `docs/CNAME` and replace its
   contents with your domain (no `https://`, no path).
3. Commit and push. `Settings` → `Pages` will detect the CNAME and
   offer to enforce HTTPS — turn that on.

## Removing a report from the public site

Delete the file from `docs/reports/` and push. The next workflow run
removes the card from the index and the report from the live URL.
Reports stay in git history so you can always recover them later if
needed.

## Opting in to scheduled automation (deferred)

We chose **manual curation** for the initial publish path. If you
later decide a set of queries is worth running on a schedule (e.g. a
weekly Ukraine-coverage report), the path is:

1. Copy `.github/workflows/publish.yml` to
   `.github/workflows/scheduled.yml`.
2. Replace its `on:` block with `schedule: - cron: "0 6 * * 1"`
   (Mondays at 06:00 UTC).
3. Add an `ANTHROPIC_API_KEY` repo secret (Ollama can't run inside
   Actions — you need a hosted LLM). Update the run command to use the
   Claude backend.
4. After the LLM step, write the resulting HTML into
   `docs/reports/<dated-slug>.html` and `git commit` from inside the
   workflow.

This is documented but not shipped because we deliberately want you to
look at every report before it goes public.
