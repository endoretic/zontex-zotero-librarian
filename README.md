# Zotero Modified for Codex

> **Private-use and unofficial.** This repository is an independent personal workflow adaptation. It is not developed by, endorsed by, or affiliated with Zotero, the Zotero project, or Ethereal Style and its author.

[中文](#中文) · [English](#english)

## 中文

### 这是什么

Zotero Modified 是一个面向 Zotero 10 的私人本地工作流工具。它以 [OpenAI 官方 Zotero 插件](https://github.com/openai/plugins/tree/main/plugins/zotero) 的检索、BibTeX、引用与导入能力为基础，增加“先预览、后写入”的文献整理能力，并采用与常见 Zotero 表格工作流兼容的 `/状态`、`rate: N` 和 `#标签`约定。

它不是 Ethereal Style 的分支、扩展或配套产品；“兼容”只表示写入的 Zotero metadata 能被采用相同约定的界面或工作流识别。

### 相比官方插件增加了什么

| 官方 Zotero 插件侧重 | Zotero Modified 的私人特化 |
| --- | --- |
| 搜索本地 Zotero、导出 BibTeX、插入文内引用、读取已索引附件文本、导入 BibTeX/RIS | 对 collection 与条目执行 preview-first CRUD：创建、重命名、回收站/删除、JSON metadata snapshot |
| 单条检索和引用工作流 | 批量修改字段、条目类型、tags、collection membership，以及 creators/relations 等结构化 metadata |
| Zotero 10 本地 API 的原生范围 | 通过可选的 Zotero Modified Bridge 管理原生彩色标签、彩色 `/状态` 与 CSL 安装/卸载 |
| 通用引用库操作 | 受控标签词表、1–5 重要性评分（`Extra` 中的 `rate: N`）、去重前预览与严格确认 |
| 无特定文献整理模型 | 将“检索 → 引文清单合并 → 去重 → 评级 → 写入 metadata → 导出/备份”串为可复核的研究工作流 |

### 标签与 metadata 约定

- `/To Read`、`/Reading`、`/Done`：少量彩色 slash status；每条目至多一个。
- `rate: 1` 至 `rate: 5`：写入 Extra，表示对当前课题的重要性，不代表期刊或作者质量。
- `Topic A`、`Method`、`Dataset`：普通主题标签，不必着色。
- `#Core`、`#Method`、`#Gap`：少量需要在 `#Tags` 列直接显示的文字标签。
- 彩色小圆点仅用于原生“已分配颜色”的标签；`#` 或 `/` 前缀本身不会赋予颜色。

### 安装

构建本地发布包：

```powershell
python .\scripts\build_release.py --clean
python -m unittest discover -s .\plugins\zotero-modified\tests -v
```

1. 在 Zotero 的“附加组件管理器”安装 `dist\zotero-modified-bridge-<VERSION>.xpi`，然后重启 Zotero。该 XPI 仅补足彩色标签与 CSL 管理；基础 CRUD 不依赖它。
2. 将本仓库作为 Codex 的本地 marketplace：

```powershell
codex plugin marketplace add "G:\Groceries\zotero-modified-for-codex"
codex plugin add zotero-modified@zotero-modified-private
```

3. 新建 Codex 任务，并先运行 `status`。首次写入时，在 Zotero 的授权弹窗中选择 **Always Allow**。

### 从 GitHub Release 安装、升级与卸载

每个 Release 都附带：完整本地 marketplace 的 `zotero-modified-*.zip`、匹配的
`zotero-modified-bridge-*.xpi`、`SHA256SUMS.txt`、`checksums.json` 和 `RELEASE_NOTES.md`。
ZIP 与 XPI 必须使用完全相同的版本；Bridge 兼容 Zotero 10.0--10.x。

首次安装时，将 ZIP 解压到一个稳定位置（不要只移动其中的 `plugins` 文件夹），将该目录作为
Codex 本地 marketplace 添加，再在 Zotero 的“附加组件管理器”中安装同版本 XPI 并重启 Zotero。

可直接把下面的提示词交给 Codex；将路径和版本替换为实际值：

```text
我已下载 Zotero Modified v<VERSION> 的 GitHub Release，并将
zotero-modified-<VERSION>.zip 解压到 <EXTRACTED_BUNDLE_DIR>；匹配的
zotero-modified-bridge-<VERSION>.xpi 位于 <XPI_PATH>，并将 Release 中的
RELEASE_NOTES.md 保存为 <RELEASE_NOTES_PATH>。

请先读取 <RELEASE_NOTES_PATH> 与 <EXTRACTED_BUNDLE_DIR>\INSTALL.md，并核对
Release 中的 SHA256SUMS.txt / checksums.json。确认 ZIP 与 XPI 版本一致、Zotero 为 10.x 后：
1. 将 <EXTRACTED_BUNDLE_DIR> 添加为 Codex 本地 marketplace；
2. 安装 Zotero Modified；
3. 指导我在 Zotero 的“附加组件管理器”从 <XPI_PATH> 安装 Zotero Modified Bridge，并提醒我重启 Zotero；
4. 重启后创建新任务，运行 @Zotero Modified status，报告本地 API、Bridge 和写入授权状态。

不要绕过 Zotero 的授权弹窗；任何写入前先展示 preview 并等待我的确认。
```

### 安装后的更新

发布版 Bridge 在首次安装后，会通过 Zotero 原生附加组件更新机制检查 GitHub Release：在 Zotero 的
“附加组件管理器”齿轮菜单中保持 **自动更新附加组件** 启用，或按需选择 **检查更新**。更新清单包含
XPI 的 SHA-256 与 Zotero 10.x 兼容范围。

Codex 插件没有常驻后台进程，因此使用已安装包内的校验更新器。让 Codex 每周运行一次以下检查；它只报告
版本、Release 链接和待下载的文件，不会写入或替换任何内容：

```powershell
python .\plugins\zotero-modified\scripts\update_release.py
```

若报告 `update_available`，先审阅结果与 Release Notes；在你明确同意后再运行：

```powershell
python .\plugins\zotero-modified\scripts\update_release.py --apply --yes --reinstall-codex
```

它会下载 ZIP、用 Release 的 `checksums.json` 核对 SHA-256、解压到同盘 staging 目录，再由独立 helper
将旧包移动为带时间戳的备份并替换。随后会尝试重新安装 Codex 插件；无论成功与否，都应新建 Codex 任务。
若当前安装目录是 Git checkout，更新器会拒绝覆盖，以保护本地改动；请先处理改动并使用 `git pull --ff-only`。

可直接使用这条定期检查提示词：

```text
每周检查一次当前安装的 Zotero Modified GitHub Release：运行 update_release.py，不要自动更新。
若有新版本，报告版本差异、Release Notes、SHA-256 校验来源和预计影响，等待我的确认。只有我明确同意后，
才运行 update_release.py --apply --yes --reinstall-codex，并报告生成的备份与日志路径；完成后提醒我新建 Codex 任务。
```

原生 Bridge 更新依赖可匿名访问的 HTTPS `updates.json`。因此若 GitHub 仓库或 Release 为私有，Zotero 无法
携带凭据查询更新；应将更新清单和 XPI 放在可公开访问的受控下载端点，或继续手动安装已验证的 XPI。

卸载时先在 Codex 的 Plugins 视图移除 **Zotero Modified**，再在 Zotero 的“附加组件管理器”移除
**Zotero Modified Bridge** 并重启；最后才删除解压目录。

### 一套 prompt 工作流

安装完成后，以下一条指令会串联本项目的主要功能。将 `A`、研究主题和文件路径替换为实际值：

```text
@Zotero Modified

为“ A ”创建一个 collection，并完成一次可审计的文献整理：

1. 先检查 Zotero 本地 API、companion 和写入授权状态；所有修改必须先给出 preview，未经我明确确认不得写入。
2. 在本地 Zotero 搜索“研究主题”；若本任务提供了网页/学术检索工具，也检索外部候选文献，并标明每条候选的来源。
3. 读取 `C:\path\seed.bib`，并从 `C:\path\review.pdf` 的参考文献中提取候选条目。用 DOI、PMID、规范化标题和第一作者/年份与 collection A 及整个库逐项比对；先给出重复、冲突、缺失 metadata 和拟导入条目的清单。
4. 只在我确认后导入确实缺失的 BibTeX/RIS 条目，并将保留条目加入 collection A。
5. 按与“研究主题”的直接相关性、方法/数据可复用性和综述论证价值，给每条条目 1–5 星的重要性评级；在 Extra 中写入或更新 `rate: N`，并说明评分理由。不要使用期刊影响因子或分区评分。
6. 使用受控词表写入普通主题标签；只对少量 `/To Read`、`/Reading`、`/Done` 状态分配颜色；仅在必要时写入 #Core、#Method 或 #Gap。不要为单篇文献创造唯一标签。
7. 输出最终变更表、重复处理记录和未解决项；确认后为 collection A 创建 JSON metadata 备份，并按需要导出更新后的 BibTeX。若提供了 CSL 文件，先校验并预览，再经我确认安装。
```

该流程中的外部网页检索、PDF 引文抽取取决于当前 Codex 任务可用的工具与用户提供的文件；本插件本身不是学术搜索引擎。BibTeX/RIS 导入、条目/collection 写入和 CSL 安装均保留确认边界。

### 常用示例

```text
@Zotero Modified 在 Selected Collection 中找出与 Theme A 相关的条目，先报告现有 tags 和重复风险，不修改任何数据。
```

```text
@Zotero Modified 为 Selected Collection 建立 /To Read、/Reading、/Done 三个彩色状态。
```

```text
@Zotero Modified 将Paper A采用的引文格式保存为Template_A.csl；先展示差异，再等待确认安装。
```

### 自动化发布规则

- 首个 GitHub Release 保留清单中的当前版本；此后运行时代码、Bridge 的 `bootstrap.js`、技能指令或发布构建脚本合并到 `main`，会自动将 Codex 插件与 Zotero Bridge 一起升一个 patch 版本，随后测试、构建并发布。
- README、测试、CI、图标和仅影响展示的 metadata 改动不会产生版本或 Release；它们只更新仓库源码。
- 每周上游同步会创建 PR。若 PR 包含运行时代码或技能指令变更，合并后自动发布 patch；若仅同步文档或图标，则不发布。上游版本只记录在 `upstream.json`，不会覆盖本项目版本。
- 如确有必要，可从 Actions 手动运行发布工作流，并选择 `force_patch` 强制发布一个 patch 版本。

## English

### What it is

Zotero Modified is a private local workflow layer for Zotero 10. It retains the search, BibTeX, citation, indexed-attachment, and BibTeX/RIS import capabilities from the [official OpenAI Zotero plugin](https://github.com/openai/plugins/tree/main/plugins/zotero), then adds preview-first curation and metadata conventions such as `/status`, `rate: N`, and `#tags`.

It is not a fork, extension, or companion product of Ethereal Style. “Compatible” only means that its Zotero metadata follows conventions that may be recognized by a similarly configured table view or workflow.

### What is added beyond the upstream plugin

- Preview-first collection and item CRUD, plus portable JSON metadata snapshots.
- Batch edits for fields, item types, tags, collection membership, creators, and relations.
- Optional local XPI endpoints for native colored tags, colored slash statuses, and CSL style management.
- A controlled-vocabulary policy, project relevance ratings in `Extra` as `rate: 1`–`rate: 5`, and explicit deduplication/confirmation boundaries.
- An auditable curation sequence: discover → reconcile reference lists → deduplicate → assess → annotate → back up/export.

### Tag and metadata conventions

- `/To Read`, `/Reading`, and `/Done`: a small set of coloured slash-prefixed statuses; each item has at most one.
- `rate: 1` through `rate: 5`: stored in `Extra` to indicate relevance to the current project, not journal or author quality.
- `Topic A`, `Method`, and `Dataset`: ordinary topical tags that do not need colours.
- `#Core`, `#Method`, and `#Gap`: a small set of text tags intended to appear directly in a `#Tags` column.
- Coloured dots indicate only Zotero tags with an assigned native colour; neither the `#` nor `/` prefix assigns a colour by itself.

### Install

Build locally, install `dist\zotero-modified-bridge-<VERSION>.xpi` through Zotero’s Add-ons Manager, restart Zotero, then run:

```powershell
codex plugin marketplace add "G:\Groceries\zotero-modified-for-codex"
codex plugin add zotero-modified@zotero-modified-private
```

Start a new Codex task after installation. The XPI is only needed for colored tags/statuses and CSL operations; the standard Zotero 10 local API handles basic CRUD.

### GitHub Release install, upgrade, and removal

Each Release contains a self-contained local marketplace bundle (`zotero-modified-*.zip`), its
matching companion (`zotero-modified-bridge-*.xpi`), `SHA256SUMS.txt`, `checksums.json`, and
`RELEASE_NOTES.md`. The ZIP and XPI must use the exact same version; the Bridge supports Zotero
10.0--10.x.

For a first installation, extract the ZIP to a stable folder without moving its `plugins` folder
away from `.agents/plugins/marketplace.json`. Add the extracted folder as a Codex local marketplace,
then install the matching XPI in Zotero’s Add-ons Manager and restart Zotero.

The following prompt can be given directly to Codex. Replace the placeholders with real paths and
the release version:

```text
I downloaded Zotero Modified v<VERSION> from GitHub Releases, extracted
zotero-modified-<VERSION>.zip to <EXTRACTED_BUNDLE_DIR>, and saved the matching
zotero-modified-bridge-<VERSION>.xpi at <XPI_PATH>. I also saved the release's
RELEASE_NOTES.md at <RELEASE_NOTES_PATH>.

First read <RELEASE_NOTES_PATH> and <EXTRACTED_BUNDLE_DIR>\INSTALL.md, then verify the release's
SHA256SUMS.txt / checksums.json. After confirming that both artifacts have the same version and Zotero is 10.x:
1. add <EXTRACTED_BUNDLE_DIR> as a Codex local marketplace;
2. install Zotero Modified;
3. guide me to install Zotero Modified Bridge from <XPI_PATH> in Zotero’s Add-ons Manager and
   remind me to restart Zotero;
4. after restart, open a new task, run @Zotero Modified status, and report the local API, Bridge,
   and write-authorisation status.

Do not bypass Zotero’s authorisation dialog. Before every write, show a preview and wait for my
confirmation.
```

### Post-install updates

After its first installation, the published Bridge uses Zotero’s native add-on update mechanism to
check GitHub Releases. Keep **Update Add-ons Automatically** enabled in the gear menu of Zotero’s
Add-ons Manager, or choose **Check for Updates** when needed. Its update manifest supplies the XPI
SHA-256 and Zotero 10.x compatibility range.

The Codex plugin has no resident background process, so its installed bundle includes a verified
release updater. Ask Codex to run this command weekly; it only reports the installed/latest version,
Release page, and pending assets and does not modify files:

```powershell
python .\plugins\zotero-modified\scripts\update_release.py
```

When it reports `update_available`, review the preview and the Release Notes. Only after explicit
approval run:

```powershell
python .\plugins\zotero-modified\scripts\update_release.py --apply --yes --reinstall-codex
```

The updater downloads the ZIP, verifies it against the release `checksums.json`, extracts it into a
same-volume staging directory, and launches a separate helper to retain a timestamped backup before
replacement. It then attempts a Codex reinstall. Start a new Codex task afterwards even if that
reload succeeds. Git checkouts are deliberately not replaced: resolve local changes and use
`git pull --ff-only` instead.

Suggested recurring prompt:

```text
Each week, check the GitHub Release for my installed Zotero Modified bundle by running
update_release.py. Do not update automatically. If one is available, report the version change,
Release Notes, checksum source, and expected impact, then wait for my approval. Only after I
explicitly approve, run update_release.py --apply --yes --reinstall-codex, report the backup and
log paths, and remind me to start a new Codex task.
```

Native Bridge updates require an anonymously reachable HTTPS `updates.json`. Zotero cannot provide
GitHub credentials to a private repository or Release; host the update manifest and XPI at a
controlled public endpoint, or install a verified XPI manually.

To remove it, first remove **Zotero Modified** from Codex’s Plugins view, then remove **Zotero
Modified Bridge** from Zotero’s Add-ons Manager and restart Zotero; delete the extracted directory
last.

### End-to-end prompt

```text
@Zotero Modified

Create collection “A” and complete one auditable literature-curation pass:

1. Check the Zotero local API, companion, and write-authorisation status first. Show a preview for every change and do not write until I explicitly confirm.
2. Search the local Zotero library for “TOPIC”. If web or scholarly-search tools are available in this task, also collect external candidates and record their provenance.
3. Read `C:\path\seed.bib` and extract candidate records from the references in `C:\path\review.pdf`. Compare each candidate with collection A and the complete library using DOI, PMID, normalised title, and first-author/year matching. First report duplicates, conflicts, missing metadata, and proposed imports.
4. Only after I confirm, import genuinely missing BibTeX/RIS records and add retained records to collection A.
5. Rate each record from one to five stars according to its direct relevance to “TOPIC”, the reusability of its methods or data, and its value to the review argument. Write or update `rate: N` in Extra and explain every rating. Do not use journal impact factors or rankings.
6. Apply ordinary topic tags from a controlled vocabulary. Assign colours only to the small `/To Read`, `/Reading`, and `/Done` status set, and use `#Core`, `#Method`, or `#Gap` only when needed. Do not create tags unique to a single item.
7. Produce a final change table, duplicate-resolution record, and unresolved-item list. After confirmation, create a JSON metadata backup of collection A and export updated BibTeX if needed. If a CSL file is provided, validate and preview it before asking for confirmation to install it.
```

External discovery and PDF-reference extraction depend on the tools and files available in the current Codex task. All imports and writes remain previewed and require confirmation.

### Common examples

```text
@Zotero Modified find entries related to Theme A in Selected Collection. First report existing tags and duplicate risk; do not modify any data.
```

```text
@Zotero Modified create the coloured /To Read, /Reading, and /Done statuses for Selected Collection.
```

```text
@Zotero Modified save the citation style used by Paper A as Template_A.csl. Show the differences first, then wait for confirmation before installing it.
```

### Release automation policy

- The first GitHub Release keeps the version already in the manifests. Thereafter, when runtime code, the Bridge `bootstrap.js`, skill instructions, or the release-build script are merged into `main`, automation bumps both the Codex plugin and Zotero Bridge by one patch version, then tests, builds, and publishes a Release.
- README, tests, CI, icons, and presentation-only metadata do not create a version or Release; they update only the repository source.
- The weekly upstream check opens a PR. If the PR changes runtime code or skill instructions, merging it publishes a patch; documentation- or icon-only updates do not. The upstream version is recorded in `upstream.json` and never replaces this project's version.
- When necessary, run the publishing workflow manually from Actions and choose `force_patch` to publish a patch release explicitly.
