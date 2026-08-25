# Zotero Modified for Codex

> **Private-use and unofficial.** This repository is an independent personal workflow adaptation. It is not developed by, endorsed by, or affiliated with Zotero, the Zotero project, or Ethereal Style and its author.

[中文](#中文) · [English](#english)

## 中文

### 这是什么

Zotero Modified 是一个面向 Zotero 10 的本地工作流工具。它以 [OpenAI 官方 Zotero 插件](https://github.com/openai/plugins/tree/main/plugins/zotero) 的检索、BibTeX、引用与导入能力为基础，增强文献整理能力，并采用与 Ethereal Style 工作流兼容的<sup>*</sup> `/状态`、`rate: N` 和 `#标签`约定。用户要求时可执行逐步审计，并生成写入前 preview 或快照。

<sup>*</sup> 本项目不是 Ethereal Style 的分支、扩展或配套产品；“兼容”只表示写入的 Zotero metadata 能被采用相同约定的界面或工作流识别。

### 与官方插件有什么不同

| 官方 Zotero 插件侧重 | Zotero Modified 的特化功能 |
| --- | --- |
| 搜索本地 Zotero、导出 BibTeX、插入文内引用、读取已索引附件文本、导入 BibTeX/RIS | 支持 collection 修改与条目 CRUD |
| 单条检索和引用工作流 | 批量修改字段、条目类型、tags 等结构化 metadata |
| Zotero 10 本地 API 的原生范围 | 通过可选的 Zotero Modified Bridge 管理原生彩色标签、彩色 `/状态` 与 CSL 安装/卸载 |
| 通用引用库操作 | 受控标签词表、1–5 重要性评分（`Extra` 中的 `rate: N`）、全库去重与批次级确认 |
| 无特定文献整理模型 | 将“创建 collection → 获得文献列表 → 全库去重 → 一次确认 → Ethereal-compatible metadata 写入”串成完整工作流 |

### 标签与 metadata 约定

- `/To Read`、`/Reading`、`/Done`：少量彩色 slash status；每个条目至多一个。
- `rate: 1` 至 `rate: 5`：写入 `Extra`，表示对当前课题的重要性，不代表期刊或作者质量。
- `Topic A`、`Method`、`Dataset`：不带 `#Topic/` 前缀的普通主题标签；只给少量稳定且高频的主题分配原生颜色。
- `#Role/Core`、`#Role/Method`、`#Role/Gap`：`#Tags` 列允许保留的三种角色标签，仅在必要时使用。
- 彩色小圆点仅用于原生“已分配颜色”的标签；`#` 或 `/` 前缀本身不会赋予颜色。

### 安装

构建本地发布包：

```powershell
python .\scripts\build_release.py --clean
python -m unittest discover -s .\plugins\zotero-modified\tests -v
```

1. 将本仓库作为 Codex 的本地 marketplace：

```powershell
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zotero-modified@zotero-modified-private
```

2. 新建 Codex 任务并首先运行 `@Zotero Modified status --require-write`。若本地 API 或写入授权不可用，任务必须停在这里，不能先继续检索、去重或解析项目文件。运行 `authorize-write` 并在 Zotero 中选择 **Always Allow** 后，再次运行授权门槛。首次使用若 Bridge 尚未安装，Codex 会提醒你在 Zotero 的“插件/附加组件管理器”中手动安装匹配的 `dist\zotero-modified-bridge-<VERSION>.xpi`；该确认不能静默代办。
3. Bridge 仅补足彩色标签、状态与 CSL 管理；基础 CRUD 不依赖它。授权门槛通过后，单个 collection、单条记录等非破坏性小写入不再单独询问。涉及多条文献的导入或 metadata 批次只汇总确认一次；删除仍遵守命令要求的精确确认。

### 从 GitHub Release 安装、升级与卸载

每个 Release 都附带：完整本地 marketplace 的 `zotero-modified-*.zip`、匹配的
`zotero-modified-bridge-*.xpi`、`SHA256SUMS.txt`、`checksums.json` 和 `RELEASE_NOTES.md`。
ZIP 与 XPI 必须使用完全相同的版本；Bridge 兼容 Zotero 10.0–10.x。

首次安装时，将 ZIP 解压到一个稳定位置（不要只移动其中的 `plugins` 文件夹），将该目录作为
Codex 本地 marketplace 添加，再在 Zotero 的“附加组件管理器”中安装同版本 XPI 并重启 Zotero。
这一步需要用户在 Zotero 中手动确认。`status` 确认 Bridge 可用后，Codex 应清理本次安装由它下载或
复制的 ZIP、XPI 安装副本、校验/说明文件和临时解压目录，但必须保留稳定安装目录、Git checkout、
备份、Zotero 配置和其它用户文件。

可直接把下面的提示词交给 Codex；将路径和版本替换为实际值：

```text
请安装 <DOWNLOAD_DIR> 中的 Zotero Modified v<VERSION>：核对 checksums.json，将 ZIP 解压到稳定的
<INSTALL_DIR>，添加为 Codex 本地 marketplace 并安装插件。首次使用时提醒我在 Zotero 中手动安装
同版本 XPI、重启并再次运行 @Zotero Modified status；不要绕过我的确认。状态通过后，只清理本次安装
由你创建或下载的 ZIP、XPI 副本、校验/说明文件和临时目录，保留 <INSTALL_DIR>、Git checkout、备份及
其它用户文件，并报告清理路径。每个任务先通过 status --require-write；多条目写入只做一次汇总确认，
除非我明确要求逐步审计，否则不要生成写入前 preview 或快照。
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

### 文献列表端到端 prompt

替换尖括号中的 collection 名称、研究主题和候选来源即可使用。

```text
@Zotero Modified

从零创建 collection “<COLLECTION_NAME>”，围绕“<RESEARCH_TOPIC>”整理文献。候选来源为 <WORKSPACE_OR_CONNECTOR_LIST>、<BIBTEX_OR_RIS_FILES>、<PDF_REFERENCE_LISTS> 及本任务可用的学术检索工具。

1. 第一项 Zotero 动作运行 `status --require-write`；若 API 或写入授权失败，立即停住，只处理授权并重新检查。
2. 授权通过后创建或定位 collection，读取现有受控词表和彩色标签；从所有来源获取候选，并保留每条来源。
3. 规范化 DOI、标题、第一作者和年份，依次按 DOI、规范化标题、第一作者/年份先匹配全库、再匹配目标 collection。列出重复、疑似重复、冲突、缺失 metadata、复用条目和拟导入条目；全库已有条目只加入 collection，不重复导入。
4. 多条目写入前给出 `来源 | 标识/标题 | 匹配 | 决定 | 缺失/冲突` 决策表及导入、复用、更新数量，只请求一次批量确认。除非我要求逐步审计，不生成逐命令 preview、snapshot 或审计文件。
5. 我确认后用精确 selector 和 `--expect-count` 完成批次：只导入确实缺失的条目，并用已核实来源补全 metadata；在 Extra 写入基于课题相关性、方法/数据复用性和综述价值的 `rate: 1–5`，保留其它行且不用期刊指标评分；每篇恰好一个原生彩色状态（`/To Read` `#6196BC`、`/Reading` `#F2A65A`、`/Done` `#59A14F`，位置 0–2），无进度信息时默认 `/To Read`；`#` 标签只允许少量 `#Role/Core`、`#Role/Method`、`#Role/Gap`；主题使用无 `#Topic/` 前缀的受控普通标签，复用并合并同义词，不创建单篇唯一标签，最多给 6 个稳定高频主题分配位置 3–8 的颜色。
6. 回读验证 collection membership、去重、每篇唯一状态和有效评分、角色命名空间及彩色主题数量；报告导入/复用/更新、状态/评分分布、词表和未解决项。
```

外部检索和 PDF 引文抽取取决于当前任务可用的工具与文件；删除操作仍保留精确确认。

### 常用示例

```text
@Zotero Modified create and curate a collection with a preview before every write
```

```text
@Zotero Modified write statuses, ratings, roles, and controlled topical metadata following Ethereal Style conventions
```

```text
@Zotero Modified write and install a CSL template for Zotero Word integration
```

### 自动化发布规则

- 首个 GitHub Release 保留清单中的当前版本；此后运行时代码、Bridge 的 `bootstrap.js`、技能指令或发布构建脚本合并到 `main`，会自动将 Codex 插件与 Zotero Bridge 一起升一个 patch 版本，随后测试、构建并发布。
- README、测试、CI、图标和仅影响展示的 metadata 改动不会产生版本或 Release；它们只更新仓库源码。
- 每周上游同步会创建 PR。若 PR 包含运行时代码或技能指令变更，合并后自动发布 patch；若仅同步文档或图标，则不发布。上游版本只记录在 `upstream.json`，不会覆盖本项目版本。
- 如确有必要，可从 Actions 手动运行发布工作流，并选择 `force_patch` 强制发布一个 patch 版本。

## English

### What it is

Zotero Modified is a local workflow tool for Zotero 10. It builds on the search, BibTeX, citation, and import capabilities of the [official OpenAI Zotero plugin](https://github.com/openai/plugins/tree/main/plugins/zotero), enhances literature curation, and uses `/status`, `rate: N`, and `#tags` conventions compatible with Ethereal Style workflows.<sup>*</sup> On request, it can perform step-by-step auditing and generate pre-write previews or snapshots.

<sup>*</sup> This project is not a fork, extension, or companion product of Ethereal Style. “Compatible” only means that its Zotero metadata can be recognized by interfaces or workflows using the same conventions.

### How it differs from the official plugin

| Official Zotero plugin focus | Zotero Modified specialization |
| --- | --- |
| Search local Zotero, export BibTeX, insert inline citations, read indexed attachment text, and import BibTeX/RIS | Collection changes and item CRUD |
| Single-item search and citation workflows | Batch edits to fields, item types, tags, and other structured metadata |
| Native Zotero 10 local API scope | Optional Zotero Modified Bridge for native colored tags, colored `/statuses`, and CSL installation/removal |
| General reference-library operations | Controlled tag vocabularies, 1–5 importance ratings (`rate: N` in `Extra`), full-library deduplication, and batch-scoped confirmation |
| No dedicated literature-curation model | An end-to-end workflow: create collection → obtain literature list → deduplicate against the full library → confirm once → write Ethereal-compatible metadata |

### Tag and metadata conventions

- `/To Read`, `/Reading`, and `/Done`: a small set of colored slash-prefixed statuses; each item has at most one.
- `rate: 1` through `rate: 5`: stored in `Extra` to indicate relevance to the current project, not journal or author quality.
- `Topic A`, `Method`, and `Dataset`: ordinary unprefixed topical tags; assign native colors only to a few stable, frequently reused topics.
- `#Role/Core`, `#Role/Method`, and `#Role/Gap`: the only role tags allowed in the visible `#Tags` namespace, and only when useful.
- Colored dots indicate only Zotero tags with an assigned native color; neither the `#` nor `/` prefix assigns a color by itself.

### Install

Build the local release bundle:

```powershell
python .\scripts\build_release.py --clean
python -m unittest discover -s .\plugins\zotero-modified\tests -v
```

1. Add this repository as a Codex local marketplace:

```powershell
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zotero-modified@zotero-modified-private
```

2. Start a new Codex task and run `@Zotero Modified status --require-write` as its first action. If the
local API or cached write authorization is unavailable, the task must stop before inspecting the
library or processing project sources. Run `authorize-write`, approve **Always Allow** in Zotero,
and rerun the gate. On first use, if the Bridge is not installed, Codex must remind you to manually
install the matching `dist\zotero-modified-bridge-<VERSION>.xpi` through Zotero’s Plugins/Add-ons
Manager; it cannot silently perform that confirmation.

3. The Bridge is needed only for colored tags/statuses and CSL operations; the standard Zotero 10
local API handles basic CRUD. After the gate passes, small non-destructive writes proceed directly;
multi-item imports or metadata batches receive one consolidated confirmation, while deletion keeps
its exact confirmation requirements.

### GitHub Release install, upgrade, and removal

Each Release contains a self-contained local marketplace bundle (`zotero-modified-*.zip`), its
matching companion (`zotero-modified-bridge-*.xpi`), `SHA256SUMS.txt`, `checksums.json`, and
`RELEASE_NOTES.md`. The ZIP and XPI must use the exact same version; the Bridge supports Zotero
10.0–10.x.

For a first installation, extract the ZIP to a stable folder without moving its `plugins` folder
away from `.agents/plugins/marketplace.json`. Add the extracted folder as a Codex local marketplace,
then install the matching XPI in Zotero’s Add-ons Manager and restart Zotero.
The XPI step requires manual user confirmation. After `status` confirms that the Bridge is
available, Codex should remove only the ZIP, XPI installer copy, checksum/release-note copies, and
temporary extraction directories it created or downloaded for this installation. It must keep the
stable install folder, Git checkouts, backups, Zotero profile data, and unrelated user files.

The following prompt can be given directly to Codex. Replace the placeholders with real paths and
the release version:

```text
Install Zotero Modified v<VERSION> from <DOWNLOAD_DIR>: verify checksums.json, extract the ZIP to the
stable <INSTALL_DIR>, add it as a Codex local marketplace, and install the plugin. On first use,
remind me to install the same-version XPI manually in Zotero, restart, and run @Zotero Modified
status again; do not bypass my confirmation. After status succeeds, remove only the ZIP, XPI copy,
checksum/release-note files, and temporary directories you created or downloaded for this install.
Keep <INSTALL_DIR>, Git checkouts, backups, and all other user files, and report removed paths.
Start every task with status --require-write. Ask once before a multi-item write; unless I explicitly
request a per-step audit, do not generate pre-write previews or snapshots.
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

### End-to-end literature-list prompt

Replace the collection name, research topic, and candidate-source placeholders before use.

```text
@Zotero Modified

Create collection “<COLLECTION_NAME>” from scratch and curate literature for “<RESEARCH_TOPIC>”. Candidate sources are <WORKSPACE_OR_CONNECTOR_LIST>, <BIBTEX_OR_RIS_FILES>, <PDF_REFERENCE_LISTS>, and scholarly-search tools available in this task.

1. Run `status --require-write` as the first Zotero action. If the API or write authorization fails, stop, address only authorization, and rerun the gate.
2. After the gate passes, create or resolve the collection, read the controlled vocabulary and colored-tag registry, obtain candidates from every source, and retain each record's provenance.
3. Normalize DOI, title, first author, and year. Match the full library first and the target collection second by DOI, normalized title, then first-author/year. List exact/likely duplicates, conflicts, missing metadata, reused records, and proposed imports; add existing library items to the collection instead of reimporting them.
4. Before a multi-item write, provide a `source | identifier/title | match | decision | missing/conflict` table and import/reuse/update counts, then ask once for batch confirmation. Unless I request per-step auditing, create no command-by-command previews, snapshots, or audit files.
5. After confirmation, use exact selectors and `--expect-count` to complete the batch: import only missing records and fill metadata from verified sources; write `rate: 1–5` in Extra based on topic relevance, method/data reuse, and review value while preserving other lines and ignoring journal metrics; give every item exactly one native colored status (`/To Read` `#6196BC`, `/Reading` `#F2A65A`, `/Done` `#59A14F`, positions 0–2), defaulting unknown progress to `/To Read`; allow only sparing `#Role/Core`, `#Role/Method`, and `#Role/Gap` tags in the `#` namespace; use controlled ordinary topics without `#Topic/`, reuse/merge synonyms, avoid one-paper-only tags, and color at most six stable high-frequency topics at positions 3–8.
6. Read back and verify collection membership, deduplication, one valid status and rating per item, the role namespace, and the colored-topic limit. Report import/reuse/update counts, status/rating distributions, vocabulary, and unresolved records.
```

External discovery and PDF-reference extraction depend on the tools and files available in the current task; destructive commands retain their exact confirmation requirements.

### Common examples

```text
@Zotero Modified create and curate a collection with a preview before every write
```

```text
@Zotero Modified write statuses, ratings, roles, and controlled topical metadata following Ethereal Style conventions
```

```text
@Zotero Modified write and install a CSL template for Zotero Word integration
```

### Release automation policy

- The first GitHub Release keeps the version already in the manifests. Thereafter, when runtime code, the Bridge `bootstrap.js`, skill instructions, or the release-build script are merged into `main`, automation bumps both the Codex plugin and Zotero Bridge by one patch version, then tests, builds, and publishes a Release.
- README, tests, CI, icons, and presentation-only metadata do not create a version or Release; they update only the repository source.
- The weekly upstream check opens a PR. If the PR changes runtime code or skill instructions, merging it publishes a patch; documentation- or icon-only updates do not. The upstream version is recorded in `upstream.json` and never replaces this project's version.
- When necessary, run the publishing workflow manually from Actions and choose `force_patch` to publish a patch release explicitly.
