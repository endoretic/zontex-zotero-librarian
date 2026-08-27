---
name: zotero-modified
description: Safely manage a personal Zotero 10 library with local CRUD, structured metadata edits, colored-tag/status/rating conventions, and CSL installation. Unofficial and private-use only.
---

# Zotero Modified

Use this skill when a user asks to read or modify a personal Zotero library, apply slash-status/rating conventions, or create and install a CSL citation style. This is an unofficial, private-use adaptation; it is not affiliated with Zotero or Ethereal Style.

## Authorization and confirmation workflow

1. The first Zotero action in every task must be `python scripts/zotero_modified.py status --require-write`. Do not inspect collections, search the library, parse project sources, or continue other project work before this gate passes.
2. If the local API is unavailable, writes are unsupported, or a cached write authorization is absent, stop immediately. Tell the user what failed. Run `authorize-write` only to obtain the missing key, tell the user to choose **Always Allow** when persistent automation is desired, and rerun `status --require-write` before resuming.
3. After the authorization gate passes, read-only work and small, non-destructive writes do not need another user confirmation. Invoke the relevant command with `--yes`; do not first run its no-`--yes` preview unless the user asked for a preview or per-step audit.
4. Before a multi-item import or metadata/tag/status batch, present one consolidated decision summary with the target collection, candidate and duplicate counts, intended metadata policy, and exact expected item count. Obtain one confirmation for the whole agreed batch, then execute its commands with `--yes` and `--expect-count` without repeated authorization prompts or command-by-command previews.
5. If the requested scope expands materially after that confirmation, treat the added scope as a new batch and ask once more. A user's explicit request for per-step audit overrides the streamlined path.
6. Destructive operations remain exceptions: prefer trash over permanent deletion, and always honor the exact confirmation required for permanent item deletion and collection/status deletion.

The script stores the local write key in the current Windows user's local application-data directory, not in the repository.

## First-install handoff and cleanup

- `status` is also the first-install check. If `modifiedBridge.manualInstallRequired` is true, explicitly tell the user that Zotero requires a one-time manual action: open Zotero's Plugins/Add-ons Manager, choose **Install Add-on From File**, select the matching release XPI, restart Zotero, then start a new Codex task and run `status` again. Do not claim that Codex can silently install the XPI or bypass Zotero's confirmation UI.
- The Bridge is optional for basic collection/item CRUD but required for native colored tags/statuses and CSL installation. State this distinction when the Bridge is absent.
- After `status` confirms `modifiedBridge.available: true`, clean up installer artifacts that Codex created or downloaded for this first installation: the release ZIP, a downloaded or copied XPI installer, copied checksum/release-note files, and scratch extraction or staging directories. Keep the stable marketplace directory, Git checkouts, backups, Zotero profile files, and all unrelated user files. Never delete a pre-existing user-supplied installer without explicit approval, and report every path removed.

## Data conventions

- A style-compatible status is a native colored Zotero tag whose name starts with `/`. An item should have at most one such status; `set-status` removes its previous slash-prefixed status first.
- A style-compatible rating is the line `rate: N` in the item's Extra field, where N is 1 through 5. Preserve all unrelated Extra lines.
- Ordinary topical tags use a controlled, unprefixed vocabulary. Do not create a `#Topic/...` namespace. The round-dot Tags column displays native Zotero colored tags; assign colors only to a few stable, frequently reused topics and the three workflow statuses.
- Use only `#Role/Core`, `#Role/Method`, and `#Role/Gap` in the visible `#` role namespace, and only where the role is genuinely useful. Do not create one-off role or topic tags.
- Configure `/To Read`, `/Reading`, and `/Done` as the small colored status set. Unless the user supplies reading progress, new curated literature may default to `/To Read`.
- Before creating topical tags, inspect existing tags with `python scripts/zotero.py tags`. Reuse the controlled vocabulary and never generate one unique AI tag per item.
- Do not add journal names, impact factors, journal tiers, or easyScholar metadata unless the user explicitly changes the project scope.

The colored-tag/status and CSL commands require the separately installed Zotero Modified Bridge XPI. Basic collection/item CRUD uses Zotero 10's stock authorized local API.

## Zotero Modified Bridge vNext

- Resolve any current/selected/open Zotero referent with `context` first; do not infer it from conversation history. It reports library-tab selection separately from the active Reader.
- `render` is a read-only native Zotero CSL preview. Use it after `install-csl` when iterating on citation or bibliography output.
- `navigate` is a non-persistent UI side effect for revealing an item or opening an attachment/annotation. It must use explicit keys and does not claim visual readback beyond the requested target.
- `merge-items` is a high-impact native merge. Present one consolidated preview with the explicit master, other items, titles, item types, and exact object versions; run with `--yes` only after confirmation. Only top-level regular items are accepted, and the Bridge verifies every version immediately before calling Zotero's native merge module.
- The Bridge remains a thin privileged layer: ordinary item/collection/tag/note CRUD stays on the stock Local API, and no generic execution endpoint or Reader UI hook is allowed.

## Release updates

- When a user asks to check for updates, run `python scripts/update_release.py` and report its JSON preview. It must not change files.
- If it reports `update_available`, summarize the installed/latest versions, release page, and checksum source. Wait for explicit approval before applying it.
- After approval, run `python scripts/update_release.py --apply --yes --reinstall-codex`. It verifies the marketplace ZIP against the published `checksums.json`, stages it on the same volume, retains a timestamped backup, and requests a Codex reinstall. Tell the user to start a new task and report the helper's backup/log paths.
- The updater intentionally refuses to replace a Git checkout. Explain that the user must resolve local changes and use `git pull --ff-only`; never overwrite a checkout or delete its backup.
- The Bridge itself uses Zotero's native add-on updater when its XPI contains a release `update_url`. It requires the update manifest and XPI to be anonymously reachable over HTTPS; do not claim that a private GitHub Release will update automatically.

## Literature-list curation protocol

Use this sequence when the user wants a collection built from a literature list. The completed collection should follow the same structural model as BN5001 while adapting the topical vocabulary to the new research theme.

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
python scripts/zotero_modified.py status --require-write
python scripts/zotero_modified.py authorize-write
python scripts/zotero_modified.py collections
python scripts/zotero_modified.py backup-collection --collection-name BN5001 --file .\BN5001-backup.json
python scripts/zotero_modified.py rename-collection --current-name BN5001 --name "BN5001 Review" --yes
python scripts/zotero_modified.py batch-update-items --collection-name BN5001 --expect-count 37 --set language=en --yes
python scripts/zotero_modified.py create-status --name reading --color "#4C9AFF" --yes
python scripts/zotero_modified.py set-status --collection-name BN5001 --expect-count 37 --name /reading --yes
python scripts/zotero_modified.py set-rating --item-key ABCD2345 --value 5 --yes
python scripts/zotero_modified.py colored-tags
python scripts/zotero_modified.py merge-items --master ABCD2345 --other EFGH6789 --expected-version ABCD2345=8 --expected-version EFGH6789=3
python scripts/zotero_modified.py install-csl --file .\my-style.csl
python scripts/update_release.py
python scripts/update_release.py --apply --yes --reinstall-codex
```

Omit `--yes` only when the user explicitly requests a dry-run preview or per-step audit. Destructive commands still require their exact confirmation values. For route coverage and read-only examples from the official OpenAI plugin, consult `references/upstream-local-api-routes.md` and `scripts/zotero.py`.
