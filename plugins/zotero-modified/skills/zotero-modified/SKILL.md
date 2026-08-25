---
name: zotero-modified
description: Safely manage a personal Zotero 10 library with local CRUD, structured metadata edits, colored-tag/status/rating conventions, and CSL installation. Unofficial and private-use only.
---

# Zotero Modified

Use this skill when a user asks to read or modify a personal Zotero library, apply slash-status/rating conventions, or create and install a CSL citation style. This is an unofficial, private-use adaptation; it is not affiliated with Zotero or Ethereal Style.

## Safety workflow

1. Run `python scripts/zotero_modified.py status` before a write. Zotero Desktop must be running and its local API enabled.
2. If write authorization is missing, run `authorize-write` and tell the user to choose **Always Allow** in Zotero when persistent automation is desired.
3. Run every mutation once without `--yes`. Present the JSON preview and verify selectors, counts, before/after values, and exact destructive confirmation values.
4. Repeat with `--yes` only after the requested target is unambiguous. Use `--expect-count` for batch operations.
5. Prefer moving items to trash over permanent deletion. Permanent item deletion and collection/status deletion require the command's exact confirmation argument.

The script stores the local write key in the current Windows user's local application-data directory, not in the repository.

## Data conventions

- A style-compatible status is a native colored Zotero tag whose name starts with `/`. An item should have at most one such status; `set-status` removes its previous slash-prefixed status first.
- A style-compatible rating is the line `rate: N` in the item's Extra field, where N is 1 through 5. Preserve all unrelated Extra lines.
- The round-dot Tags column displays native Zotero colored tags. Keep these few and stable. Ordinary subject or workflow tags do not need colors.
- Before creating topical tags, inspect existing tags with `python scripts/zotero.py tags`. Reuse the controlled vocabulary and never generate one unique AI tag per item.
- Do not add journal names, impact factors, journal tiers, or easyScholar metadata unless the user explicitly changes the project scope.

The colored-tag/status and CSL commands require the separately installed Zotero Modified Bridge XPI. Basic collection/item CRUD uses Zotero 10's stock authorized local API.

## Release updates

- When a user asks to check for updates, run `python scripts/update_release.py` and report its JSON preview. It must not change files.
- If it reports `update_available`, summarize the installed/latest versions, release page, and checksum source. Wait for explicit approval before applying it.
- After approval, run `python scripts/update_release.py --apply --yes --reinstall-codex`. It verifies the marketplace ZIP against the published `checksums.json`, stages it on the same volume, retains a timestamped backup, and requests a Codex reinstall. Tell the user to start a new task and report the helper's backup/log paths.
- The updater intentionally refuses to replace a Git checkout. Explain that the user must resolve local changes and use `git pull --ff-only`; never overwrite a checkout or delete its backup.
- The Bridge itself uses Zotero's native add-on updater when its XPI contains a release `update_url`. It requires the update manifest and XPI to be anonymously reachable over HTTPS; do not claim that a private GitHub Release will update automatically.

## Integrated curation protocol

When the user asks to create a collection, reconcile a bibliography or PDF reference list, assess papers, and write metadata, follow this sequence:

1. Run `status`, then inspect existing collections, tags, and relevant local records with `scripts/zotero.py`. Do not write yet.
2. Create or resolve the target collection. Read any user-provided BibTeX/RIS file or accessible PDF reference list. Normalize candidate DOI, PMID, title, first author, and year.
3. Compare every candidate against the target collection and the whole local library. Report exact duplicates, likely duplicates, missing fields, and proposed imports. Use any web or academic-search tool only if it is available in the current task; this plugin is not a search engine.
4. Ask for confirmation before importing records or changing Zotero. After confirmation, import only missing BibTeX/RIS records, then add the retained records to the target collection.
5. Rate relevance to the user's stated project from 1 to 5, explaining the rationale from topical fit, reusable method/data, and value to the argument. Write the result as `rate: N` in Extra. Never infer a rating from journal metrics.
6. Reuse the existing controlled vocabulary for ordinary topic tags. Assign at most one colored `/To Read`, `/Reading`, or `/Done` status. Use `#Core`, `#Method`, or `#Gap` only when a visible text label is genuinely useful. Never create a tag unique to one item.
7. Preview every metadata mutation, obtain explicit confirmation, then write. Finish with a change log, unresolved records, a `backup-collection` JSON snapshot, and BibTeX export when requested. Validate and preview any CSL before installing it.

## Common commands

```powershell
python scripts/zotero_modified.py collections
python scripts/zotero_modified.py backup-collection --collection-name BN5001 --file .\BN5001-backup.json
python scripts/zotero_modified.py rename-collection --current-name BN5001 --name "BN5001 Review"
python scripts/zotero_modified.py batch-update-items --collection-name BN5001 --expect-count 37 --set language=en
python scripts/zotero_modified.py create-status --name reading --color "#4C9AFF"
python scripts/zotero_modified.py set-status --collection-name BN5001 --expect-count 37 --name /reading
python scripts/zotero_modified.py set-rating --item-key ABCD2345 --value 5
python scripts/zotero_modified.py colored-tags
python scripts/zotero_modified.py install-csl --file .\my-style.csl
python scripts/update_release.py
python scripts/update_release.py --apply --yes --reinstall-codex
```

Append `--yes` only after reviewing the preview. For route coverage and read-only examples from the official OpenAI plugin, consult `references/upstream-local-api-routes.md` and `scripts/zotero.py`.
