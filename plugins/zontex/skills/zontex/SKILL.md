---
name: zontex
description: Safely manage a personal Zotero 10 library with local CRUD, structured metadata edits, colored-tag/status/rating conventions, CSL installation, and experimental native PDF annotations through Zontex.
---

# Zontex

Use this skill when a user asks to read or modify a personal Zotero library, apply slash-status/rating conventions, create native PDF annotations, or create and install a CSL citation style. Zontex is an independent open-source project; it is not affiliated with Zotero, OpenAI, or Ethereal Style.

## Authorization and confirmation workflow

1. If a task may write to Zotero, its first Zotero action must be `python scripts/zontex.py status --require-write`. A strictly read-only task may start with `status`, but must pass `status --require-write` before any later mutation. Local project-file inspection does not depend on this Zotero gate.
2. If the local API is unavailable, writes are unsupported, or a cached write authorization is absent, stop immediately. Tell the user what failed. Run `authorize-write` only to obtain the missing key, tell the user to choose **Always Allow** when persistent automation is desired, and rerun `status --require-write` before resuming.
3. After the authorization gate passes, read-only work and small, non-destructive writes do not need another user confirmation. Invoke the relevant command with `--yes`; do not first run its no-`--yes` preview unless the user asked for a preview or per-step audit.
4. Before a multi-item import or metadata/tag/status batch, present one consolidated decision summary with the target collection, candidate and duplicate counts, intended metadata policy, and exact expected item count. Obtain one confirmation for the whole agreed batch, then execute its commands with `--yes` and `--expect-count` without repeated authorization prompts or command-by-command previews.
5. If the requested scope expands materially after that confirmation, treat the added scope as a new batch and ask once more. A user's explicit request for per-step audit overrides the streamlined path.
6. Destructive operations remain exceptions. Prefer Trash for ordinary items, but never send annotations to Trash because Zotero can hide a deleted annotation behind live parent rows. If a `trash-items` target contains annotations, stop before every write and tell the user in their language: “注意：注释删除后无法恢复。如需删除，请回复确认。确认后，其他条目将移入回收站，注释将永久删除。” Omit the last sentence when there are no ordinary items. After the user explicitly confirms, rerun the same exact selection with `--expect-count N --confirm DELETE-PERMANENTLY --yes`; `trash-items` will move ordinary items to Trash and permanently delete only the exact annotation keys. Do not ask the user to type the internal confirmation token. Always honor the exact confirmation required for other permanent item, collection, and status deletions.

The script stores the local write key in the current Windows user's local application-data directory, not in the repository.

## First-install handoff and cleanup

- `status` is also the first-install check. If `zontexBridge.manualInstallRequired` is true, explicitly tell the user that Zotero requires a one-time manual action: open Zotero's Plugins/Add-ons Manager, choose **Install Add-on From File**, select the matching release XPI, restart Zotero, then start a new Codex task and run `status` again. Do not claim that Codex can silently install the XPI or bypass Zotero's confirmation UI.
- The Bridge is optional for basic collection/item CRUD but required for native colored tags/statuses, CSL installation, and active PDF annotations. State this distinction when the Bridge is absent.
- After `status` confirms `zontexBridge.available: true`, clean up installer artifacts that Codex created or downloaded for this first installation: the release ZIP, a downloaded or copied XPI installer, copied checksum/release-note files, and scratch extraction or staging directories. Keep the stable marketplace directory, Git checkouts, backups, Zotero profile files, and all unrelated user files. Never delete a pre-existing user-supplied installer without explicit approval, and report every path removed.

## Data conventions

- A style-compatible status is a native colored Zotero tag whose name starts with `/`. An item should have at most one such status; `set-status` removes its previous slash-prefixed status first.
- A style-compatible rating is the line `rate: N` in the item's Extra field, where N is 1 through 5. Preserve all unrelated Extra lines.
- Ordinary topical tags use a controlled, unprefixed vocabulary. Do not create a `#Topic/...` namespace. The round-dot Tags column displays native Zotero colored tags; assign colors only to a few stable, frequently reused topics and the three workflow statuses.
- Use only `#Role/Core`, `#Role/Method`, and `#Role/Gap` in the visible `#` role namespace, and only where the role is genuinely useful. Do not create one-off role or topic tags.
- Configure `/To Read`, `/Reading`, and `/Done` as the small colored status set. Unless the user supplies reading progress, new curated literature may default to `/To Read`.
- Before creating topical tags, inspect existing tags with `python scripts/zotero.py tags`. Reuse the controlled vocabulary and never generate one unique AI tag per item.
- Do not add journal names, impact factors, journal tiers, or easyScholar metadata unless the user explicitly changes the project scope.

The colored-tag/status, CSL, and active-annotation commands require the separately installed Zontex Bridge XPI. Basic collection/item CRUD uses Zotero 10's stock authorized local API.

## Zontex Bridge

- Resolve any current/selected/open Zotero referent with `context` first; do not infer it from conversation history. It reports library-tab selection separately from the active Reader.
- Active PDF annotation is experimental. The current Zotero 10.0.1 implementation uses feature-detected private Reader mapper/manager methods and may break after a Zotero update.
- Surface every entry in `zontexBridge.compatibility.warnings` returned by the required `status` gate. Before `create-annotation`, call `context`, report any `reader.capabilities.annotation.warnings`, and require the requested `highlight`/`underline` capability plus a non-empty annotation backend; otherwise stop without attempting the write. Version or newly available standard-API warnings are advisory when the effective backend remains compatible and do not require another confirmation.
- `render` is a read-only native Zotero CSL preview. Use it after `install-csl` when iterating on citation or bibliography output.
- `navigate` is a non-persistent UI side effect for revealing an item or opening an attachment/annotation. It must use explicit keys and does not claim visual readback beyond the requested target.
- `rename-tag` and `merge-tags` are library-wide, high-impact writes. Present one consolidated summary of source/target names, expected affected-item counts, and native colors; run with `--yes` only after that explicit confirmation. The Bridge rechecks every count immediately before mutation and preserves the target color.
- `merge-items` is a high-impact native merge. Present one consolidated preview with the explicit master, other items, titles, item types, and exact object versions; run with `--yes` only after confirmation. Only top-level regular items are accepted, and the Bridge verifies every version immediately before calling Zotero's native merge module.
- The Bridge remains a thin privileged layer: ordinary item/collection/tag/note CRUD stays on the stock Local API, and no generic execution endpoint or Reader UI hook is allowed.
- `document-segments` reads active PDF SDT leaf blocks as lossless, exact-offset segments. Its default output omits internal spans; use `--verbose` only when those locators are actually needed. Use `segmentId` with a UTF-16 `[start,end)` range; never retry a stale locator after `412 document-changed`.
- `create-annotation` is limited to active PDF Reader + native SDT + highlight/underline. Always pass the exact selected text with `--expected-text`; a mismatch stops before the write. Use it directly for one or two explicitly requested annotations.
- `annotations-to-note` uses Zotero's native annotation-to-note path. Validate that all annotations belong to the requested parent item; classification and prose remain outside the Bridge.

### Fast annotation workflow

Use this path for three or more annotations on one unchanged active PDF. It removes repeated tool work; it does not lower the evidence or safety standard.

1. Pass the status gate once, resolve the active attachment with `context`, surface compatibility warnings, and require the requested annotation capability/backend.
2. Read `document-segments` once. Freeze its attachment key and `sourceHash`; do not repeatedly refetch unchanged text.
3. Build one manifest with unique `clientId` and target ranges plus exact `expectedText`, type, color, comment, and tags. Offsets are JavaScript UTF-16 code units. Analyze disjoint sections in parallel only when that genuinely saves time.
4. Present one consolidated summary and obtain one confirmation for the complete batch. If user waiting may have changed the UI, call `context` once more and require the same attachment and backend.
5. Run one `create-annotations --file ... --expect-count N --yes` command. It validates the whole manifest first, then calls the existing single-annotation route sequentially in one process and performs one consolidated Local API readback.
6. On `412`, Reader/attachment change, uncertain transport outcome, partial completion, or failed readback, stop and report created, duplicate, failed, and not-attempted client IDs. Never replay the whole manifest, reuse stale locators, or automatically delete created annotations.

Use the single command or a per-step audit when there are only one or two targets, the passages remain ambiguous, or the user explicitly requests independent review.

## Release updates

- When a user asks to check for updates, run `python scripts/update_release.py` and report its JSON preview. It must not change files.
- If it reports `update_available`, summarize the installed/latest versions, release page, and checksum source. Wait for explicit approval before applying it.
- After approval, run `python scripts/update_release.py --apply --yes --reinstall-codex`. It verifies the marketplace ZIP against the published `checksums.json`, stages it on the same volume, retains a timestamped backup, and requests a Codex reinstall. Tell the user to start a new task and report the helper's backup/log paths.
- The updater intentionally refuses to replace a Git checkout. Explain that the user must resolve local changes and use `git pull --ff-only`; never overwrite a checkout or delete its backup.
- The Bridge itself uses Zotero's native add-on updater when its XPI contains a release `update_url`. It requires the update manifest and XPI to be anonymously reachable over HTTPS; do not claim that a private GitHub Release will update automatically.

## Fast item workflow

- For three or more literature candidates, read the relevant Zotero scope once with `inventory`. It follows pagination and returns only matching fields. Build a temporary in-memory lookup; do not repeat one search or GET per candidate and do not create a persistent cache.
- Use any reliable DOI, PMID, ISBN, or other identifier already present for exact local matching without mandatory cross-validation. Only candidates without identifiers fall back to normalized title, first author, and year.
- After deduplication and one consolidated confirmation, put every genuinely missing item in one `create-items` manifest with a unique `clientId`. Use `--expect-count N --yes`; the CLI splits batches at 50 and performs one consolidated readback.
- If `create-items` reports a failed or not-attempted record, stop. Report its `clientId` and preserve every successful result. Never replay the full manifest or automatically delete created items; corrected remaining records form a newly confirmed batch.
- Prefer one explicit-key bulk selection for later updates. The CLI chunks keys internally and preserves requested order, so do not loop over per-item commands.

## Literature-list curation protocol

Use this sequence when the user wants a collection built from a literature list. The completed collection should follow the default Zontex metadata structure while adapting the topical vocabulary to the user's research theme.

1. Pass `status --require-write` before doing anything else. If it fails, stop at the authorization problem.
2. Create or resolve the target collection. Creating one empty collection is a small write and does not require a separate confirmation after the gate passes.
3. Obtain candidates from the sources the user placed in scope: an existing workspace or connector list, local Zotero results, BibTeX/RIS, an accessible PDF reference list, or available scholarly-search tools. Record the source of every candidate; this plugin itself is not a search engine.
4. Normalize DOI, PMID, title, first author, and year. Compare each candidate first against the complete Zotero library and then against the target collection. Classify exact duplicates, likely duplicates, metadata conflicts, missing fields, retained existing records, and genuinely missing imports.
5. Present one literature decision list and one consolidated write summary. This is not a command-by-command mutation preview. Include candidate provenance, duplicate resolution, unresolved metadata, proposed imports, retained records, the Ethereal-compatible metadata policy, and the expected number of affected items. Ask once for confirmation of the multi-item write.
6. After confirmation, import only genuinely missing records, add retained records to the collection, and write the agreed metadata without more previews or confirmations:
   - `rate: N` in Extra, based on direct relevance, reusable methods/data, and value to the review argument—not journal metrics;
   - at most one `/To Read`, `/Reading`, or `/Done` status;
   - ordinary unprefixed controlled topical tags, with native colors assigned only to a few stable, high-frequency topics;
   - only necessary `#Role/Core`, `#Role/Method`, or `#Role/Gap` role tags.
7. Read back the target collection and verify counts, one-status-per-item, allowed role tags, ratings, and expected membership. Report a concise final change summary and unresolved records. Do not generate a pre-write preview file, audit log, JSON snapshot, or BibTeX export unless the user requested it.

## Common commands

```powershell
python scripts/zontex.py status --require-write
python scripts/zontex.py authorize-write
python scripts/zontex.py inventory --all
python scripts/zontex.py create-items --json-file .\items.json --expect-count 35 --yes
python scripts/zontex.py collections
python scripts/zontex.py backup-collection --collection-name "SDT Review" --file .\sdt-review-backup.json
python scripts/zontex.py rename-collection --current-name "SDT Review" --name "SDT Methods Review" --yes
python scripts/zontex.py batch-update-items --collection-name "SDT Review" --expect-count 24 --set language=en --yes
python scripts/zontex.py create-status --name reading --color "#4C9AFF" --yes
python scripts/zontex.py set-status --collection-name "SDT Review" --expect-count 24 --name /reading --yes
python scripts/zontex.py set-rating --item-key ABCD2345 --value 5 --yes
python scripts/zontex.py trash-items --item-key PAPER123 --item-key ANN12345 --expect-count 2 --confirm DELETE-PERMANENTLY --yes
python scripts/zontex.py colored-tags
python scripts/zontex.py rename-tag --from "Old tag" --to "New tag" --expect-count 12
python scripts/zontex.py merge-tags --source "Old tag=12" --source "Legacy=3" --into "New tag"
python scripts/zontex.py merge-items --master ABCD2345 --other EFGH6789 --expected-version ABCD2345=8 --expected-version EFGH6789=3
python scripts/zontex.py install-csl --file .\my-style.csl
python scripts/zontex.py context
python scripts/zontex.py document-segments --attachment-key ABCD2345
python scripts/zontex.py create-annotation --attachment-key ABCD2345 --source-hash "SOURCE_HASH_FROM_DOCUMENT_SEGMENTS" --segment-id block:5 --start 0 --end 18 --expected-text "Exact quoted text" --type highlight --yes
python scripts/zontex.py create-annotations --file .\annotations.json --expect-count 12 --yes
python scripts/zontex.py annotations-to-note --parent-item-key ABCD2345 --annotation-key EFGH6789 --order document --yes
python scripts/update_release.py
python scripts/update_release.py --apply --yes --reinstall-codex
```

Omit `--yes` only when the user explicitly requests a dry-run preview or per-step audit. Destructive commands still require their exact confirmation values. For route coverage and read-only examples from the official OpenAI plugin, consult `references/upstream-local-api-routes.md` and `scripts/zotero.py`.
