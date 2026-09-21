# NOTES.md

## What this is

A Spectora → Hive Inspect template importer: upload a Spectora "Export to
spreadsheet → Export HTML Text" `.xls` file, get a structured, editable
template (`Template → Section → Item → Comment`) stored in a real backend,
with copy/duplicate support and nothing silently dropped during import.

## Supported input

- Spectora `.xls` exports produced via **Templates → Export to spreadsheet
  → Export HTML Text** specifically — not the plain-text export, which
  strips the HTML formatting the assignment asks us to preserve.
- All 43 columns present in that export format are read and mapped to
  real, typed model fields — not flattened into a JSON blob. This
  includes the long tail: `Locked`, `Simple Format`, `Disable Photos`,
  `Default Estimate Min/Max`, and all 10 `Default Photo N` / `Default
  Photo N Caption` pairs.
- The parser reads columns **by header name**, not position, so a
  differently-ordered or slightly different version of the same export
  format still works — this was tested against a second, hand-built
  export with a reordered column and an intentionally invalid `Comment
  Type` value (see "How I checked my work" below).
- HTML entities (`&amp;` etc.) are unescaped across every text column,
  not just Comment Text — they show up in Item/Section names too in the
  real InterNACHI export.

## What I cut, and why

- **Scheduling, inspections booking, calendar, contacts, teams,
  automations, messages, business tools, metrics, earnings.** The
  assignment explicitly lists scheduling and payments as out of scope.
  Hive's own product conflates "Inspections" (booking) with template
  content in its nav; I kept my own nav to just Templates, and left the
  rest of Hive's sidebar items present but inert, purely as a visual
  reference to the real product's shell.
- **Section Description, Private Notes, and the "visible in report"
  toggle** on the Section Details panel. These are visible in Hive's own
  UI and I matched them visually, but they have no corresponding column
  in the Spectora export — there's no import data to preserve here, so
  wiring real persistence for them felt like scope creep relative to
  "faithful import" and "sound decisions about where to spend time."
  They're clearly marked as not-saved in the UI itself rather than
  silently pretending to work.
- **Fetching/storing the actual image files** behind the 10 "Default
  Photo" columns per comment. The URL and caption text are captured and
  stored faithfully (nothing about them is dropped), but the importer
  does not download and re-host the images themselves — flagged as an
  info-level entry in the import issue log whenever a comment references
  one, so it's visible rather than silently absent.
- **Template-level settings** (Ratings toggle, Customer Viewing Name,
  Report Introduction/Summary text, Template Documents upload) — same
  reasoning as Section Description above: no source data, not core to
  faithful import/edit/copy, deliberately left out of the build.

## The one improvement I made

An **import issue log**: every row/column the parser couldn't cleanly
map — a `Comment Type` value outside `info/limit/defect`, a missing
expected column, a referenced-but-unfetched default photo — gets
recorded with the row number, column, severity, and a plain-language
message, and is visible from the template's Overview page. This is the
"skipped or unsupported content is visible, not silently dropped"
requirement made concrete and inspectable rather than just a design
claim. It's also what makes the importer safe to point at a *different*
Spectora export later: unexpected values degrade to a logged, blank
field instead of crashing the import.

## Known limitations

- Section/Item/Comment editing covers name, comment text, type, and
  category with real persistence; the remaining ~35 columns per comment
  are shown read-only in an "Advanced / all fields" panel rather than
  each getting a dedicated input widget — editable in the database and
  visible in the UI, just not individually form-editable yet.
- No authentication/multi-user support — single shared dataset, as
  fits a 2-day internal review tool rather than a production multi-tenant
  product.
- No delete-confirmation trail/undo — deleting a template is immediate
  once confirmed via the browser `confirm()` dialog.
- Tested against the InterNACHI Residential export and a small
  hand-built synthetic export; not tested against every possible
  Spectora template variant that exists in the wild.

## How I checked my work

- **Unit-level**: wrote a small synthetic `.xls` file with known
  section/item/comment values, including one deliberately invalid
  `Comment Type` and one deliberately invalid `Category` value, and
  asserted the parser produced the exact expected section/item/comment
  tree, correctly blanked the two bad values, and logged both as
  `ImportIssue` rows with the right row number and message — this is
  the failure case shown in the walkthrough.
- **Real-data check**: imported the actual InterNACHI Residential export
  and confirmed the resulting Sections/Subsections/Fields counts (12 /
  63 / 366) matched exactly what Spectora's own template editor reports
  for the same template — used as the correctness baseline for "did the
  customer's content survive."
- **Independence check**: duplicated an imported template, edited a
  field in the copy, and confirmed the original's corresponding row was
  unchanged in the database.
- **End-to-end**: manually exercised every view (list, import, editor
  overview, section drill-down, subsection drill-down, comment save,
  duplicate, delete) against both local SQLite and the deployed Supabase
  Postgres instance.
- **Performance**: the first working version of the importer wrote one
  row at a time (~370 individual INSERTs for the real export), which
  took close to two minutes end-to-end against a remote database.
  Rewrote it to batch all Section/Item/Comment writes with Django's
  `bulk_create` inside a single transaction, cutting it to a few
  seconds — verified the batched version produces identical output to
  the original row-by-row version against the same test file before and
  after the change.

## Stack and what I built on

- Django 5 (models/views/templates), Tailwind (CDN) for styling,
  `openpyxl` for reading the `.xls` export, `psycopg2` + `dj-database-url`
  for Postgres/Supabase, `gunicorn` + `whitenoise` for the Cloud Run
  deployment.
- No template/starter kit or scaffolding tool was used to generate the
  Django project — it's a standard `django-admin startproject` layout
  with one custom app (`templates_app`).
- The visual design (sidebar shell, template list, template editor,
  three-pane Sections/Items/Comments layout) is modeled directly on
  Hive Inspect's own product UI, referenced from screenshots of the live
  Hive dashboard taken during the trial-account exploration step, not
  copied from any third-party template or starter.

## AI tool use

Built with Claude (Anthropic) as a coding/pairing assistant throughout —
planning the data model, writing the Spectora parser and its
graceful-failure handling, the Django views/templates, and diagnosing the
Cloud Run + Supabase deployment issues (pooled vs. direct connections,
`.gcloudignore`, `collectstatic` misconfiguration, the batching
performance fix). All generated code was reviewed, tested against real
and synthetic data, and iterated on by me before being treated as final;
the "how I checked my work" section above is the concrete evidence of
that review, not just AI output taken as-is.

## Approximate time spent

- Product exploration (Hive trial, Spectora export, InterNACHI template
  research): ~1.5 hrs
- Data model + parser design and implementation: ~2.5 hrs
- Django views/URLs/forms: ~1.5 hrs
- Frontend (list, import, editor, matching Hive's UI): ~3 hrs
- Deployment (Docker, Cloud Run, Supabase, connection pooling,
  performance fix): ~2.5 hrs
- Debugging/iteration across the above: ~2 hrs
- **Total: ~13 hours**, across the two-day window.