# Zontex 功能与工作流 / Features and Workflows

[中文](#中文) · [English](#english) · [返回 README / Back to README](../README.md)

## 中文

Zontex 让 Codex 负责理解任务、检索与规划，让 Zotero Local API 处理常规读写，再由窄权限的 Zontex Bridge 补足原生维护、Reader 和注释能力。

### 功能

#### 文献整理与全库去重

通过 DOI、PMID 和标题，结合首位作者与年份归一化候选文献，先查完整 Zotero 文献库，再只导入缺失条目并复用已有记录。

```text
@Zontex 把这份引文列表整理进 “SDT Review”：全库去重，保留已有条目，只导入真正缺失的文献，并汇总需要我决定的 metadata 冲突。
```

<sup>*</sup>你可以从`.pdf`,`.bib`……或其它AI研究工具（如Undermind）中获得引文列表，当然也可以让codex自己按主题检索。

#### Metadata 与阅读流程

##### 太长不看版

原生 Zotero 示例：

```text
@Zontex 按 Zontex 的无插件默认方案整理 “SDT Review”。先读取并复用现有标签、颜色和同义词：
用 StructuralDamage、VibrationAnalysis、SensorFusion、FieldValidation 等普通标签描述主题与方法；用彩色 /To Read、/Reading、/Done
表示阅读状态，每篇最多一个；把当前课题相关度 1–5 写入 Extra 的 rate: N。本次不创建 #Role 标签。
写入前列出将复用、新建和分配颜色的标签及预计影响数量；我确认后批量写入，再回读检查状态和评级。
```

Ethereal Style 示例：

```text
@Zontex 按 Zontex 的 Ethereal Style 兼容方案整理 “SDT Review”。先读取并复用现有标签和颜色：
主题用不带前缀的普通标签；阅读状态只用彩色 /To Read、/Reading、/Done，每篇最多一个；
相关度写入 Extra 的 rate: 1–5；只有真正承担核心证据、方法来源或研究缺口作用的文献，才分别添加
#Role/Core、#Role/Method 或 #Role/Gap，并且不给这些 #Role 标签分配颜色。写入前汇总预计数量；我确认后再执行并回读验证。
```

你可以直接替换默认名称、颜色和角色词表，而不改变这套结构：

```text
@Zontex 以上述默认方案为模板，但使用以下自定义：
状态：<状态名称、颜色和顺序>；彩色主题：<允许分配颜色的少量主题>；
# 标签：<允许的命名空间和词表>；rate：<1–5 各自代表什么>。
先读取现有标签与颜色，列出可复用项、命名冲突和迁移数量，不要立即写入；等我确认后再迁移并验证。
```

> 注意：Zotero 本身没有规定标签词表，所以上述“原生方案”是本工作流提供的一套无插件默认方案。条目中实际写入的都是 Zotero 标签；“普通标签”“彩色标签”和“`#` 标签”，并不是互不兼容的数据。

| 名称 | 实际写入 Zotero 的内容 | 原生 Zotero 中的表现 | Ethereal Style 中的表现 |
| --- | --- | --- | --- |
| 普通标签 | `StructuralDamage`、`VibrationAnalysis`、`SensorFusion` 等标签 | 显示在标签面板中，可用于筛选 | 仍是普通标签；默认不会出现在只匹配 `#` 的 `#Tags` 列中 |
| 彩色标签 | 普通标签外加文献库级的原生颜色与位置，例如 `/To Read` + 蓝色 | 标题旁显示彩色色块，并可用数字键切换 | `Tags` 列可将它显示为彩色小圆点或标记 |
| 彩色小圆点 | 不产生新数据 | 没有独立对应项 | 只是彩色标签的界面效果；不能直接“写入一个圆点” |
| `#` 标签 | 名称以 `#` 开头的普通标签，例如 `#Role/Method` | 按原名显示，`#` 没有特殊含义 | `#Tags` 列默认以文字显示并隐藏开头的 `#`，也可按 `/` 展示层级 |
| 评级 | `Extra` 中的一行 `rate: 1` 至 `rate: 5` | 作为普通 `Extra` metadata 保存 | 可由 Rating 界面读取和修改 |

颜色与前缀彼此独立：`#Role/Method` 不会因为有 `#` 自动带颜色，`/To Read` 也只有在分配 Zotero 原生颜色后才会显示为彩色标记。一个 `#` 标签也可以另行分配颜色，但默认不这样做，以免它同时在 `Tags` 和 `#Tags` 两列重复出现。Zotero 每个文献库[最多可配置 9 个彩色标签](https://www.zotero.org/support/collections_and_tags#colored_tags)，因此颜色应留给少量需要一眼识别或用快捷键切换的标签。

Zontex 的默认方案如下：

- 主题、方法和数据特征使用不带前缀的普通标签，例如 `StructuralDamage`、`VibrationAnalysis`、`SensorFusion` 和 `FieldValidation`。它们可以按研究需要保持细致；默认不分配颜色。
- 阅读状态使用 `/To Read`、`/Reading`、`/Done`；每篇文献最多一个，并在用户同意后分配原生颜色。
- 当前课题相关度写入 `Extra` 的 `rate: N`，含义是“对这个课题有多重要”，不是论文质量或期刊等级。
- 文献在研究中的特殊作用可选用 `#Role/Core`、`#Role/Method`、`#Role/Gap`；默认不分配颜色，也不要求每篇都有。
- 少量长期复用的主题可以由用户提升为彩色标签；Zontex 先读取已有颜色和位置，不覆盖用户现有配置。

一篇文献的完整 metadata 可以是：

```text
Tags: StructuralDamage, SensorFusion, /Done, #Role/Core
Extra: rate: 5
```

在原生 Zotero 中，这四项都是可搜索的标签，`/Done` 若已分配颜色，会在标题旁显示色块；在 Ethereal Style 中，同一份数据可表现为 `Tags` 列中的状态圆点、`#Tags` 列中的 `Role/Core` 文字和 Rating 中的 5 分。`StructuralDamage` 与 `SensorFusion` 仍保留为普通主题标签。若希望普通主题标签也显示在 Ethereal Style 的文字标签列中，可以按其 [`#Tags` 列规则](https://github.com/MuiseDestiny/zotero-style#tags-1)把 `Prefix` 改为 `~~/`，显示所有不以 `/` 开头的标签；不必为此把全部主题标签改成 `#` 标签。

#### 全库标签维护

通过精确计数、写入前复核和原生颜色保留完成标签改名或合并，避免并发修改扩大影响范围。

```text
@Zontex 预览把全库的 “Structural Damage Detection” 和 “damage detection” 合并到 “Damage Detection”；列出数量与颜色，等我确认后执行。
```

#### 原生条目合并

通过显式主条目和对象版本调用 Zotero 原生 merge 模块合并重复记录，附件、笔记及关联数据一并保留。

```text
@Zontex 找出这两个 DOI 重复条目，比较 metadata 和附件，选择信息最完整的作为主条目；先给我合并预览。
```

#### Reader 上下文、引用渲染与导航

Zontex 能识别你当前选中的条目或正在阅读的 PDF，按指定样式生成引文和参考文献，也能直接打开对应的条目、附件或注释。

```text
@Zontex 告诉我现在打开的是哪篇论文，用 APA 生成它的文内引用和参考文献，在 Zotero 中定位当前collection已有的，最重要的那一篇。
```

#### PDF 注释与笔记

通过当前 PDF 的结构化文本段、精确偏移和源文档 hash 创建原生 highlight/underline，再用 Zotero 原生路径汇总为笔记。

```text
@Zontex 在当前 PDF 中高亮包含 “stochastic damage tracking” 的完整句子，加上 Method 标签，再把这篇论文的注释汇总成一条笔记。
```

主动创建 PDF 注释目前是实验性功能。Zotero 10.0.1 尚无公开的桌面写入接口，当前主路径会先做能力探测，再使用 Reader 私有 mapper 与 annotation manager；版本或接口变化可能使其失效。`status` 与 `context` 会返回兼容性提醒，未来公开接口出现后应改为主路径，现有实现只保留为 fallback。

删除注释是回收站策略的例外。删除目标中包含注释时，Zontex 会先停止操作并提示：“注意：注释删除后无法恢复。如需删除，请回复确认。确认后，其他条目将移入回收站，注释将永久删除。”用户确认后，同一批普通条目进入回收站，注释则按精确 key 永久删除；如果普通条目移入回收站失败，Zontex 不会继续删除注释。直接删除论文或 PDF 仍使用 Zotero 原生回收站及其父子级联逻辑。

#### CSL 管理

通过 Bridge 调用 Zotero 样式管理器安装 CSL，并用原生渲染结果验证 citation 与 bibliography 输出。

```text
@Zontex 提取当前论文中的 citation 与 bibliography 格式，生成并安装对应的 CSL；如果结果不符合示例，帮我修改后重新验证。
```

### 用一条指令串起工作流

下面的 prompt 把候选文献与去重、metadata 规划和一次确认串起来，随后批量写入并回读验证：

```text
@Zontex 先运行 status --require-write。读取我提供的引文列表，为 “SDT Review” 建立或复用 collection；
按 DOI、PMID、标题、首位作者和年份与完整 Zotero 文献库去重，复用已有记录，只导入真正缺失的文献。
然后给出一份合并后的决策清单：来源、重复项、metadata 冲突、缺失字段、拟导入条目，以及 rate、/状态、
受控主题标签和必要的 #Role 标签方案。把所有预计写入数量汇总成一次确认；我确认后再执行，不要逐条询问。
完成后回读 collection，检查条目数、每条至多一个 /状态、角色标签范围、rate 和 collection 成员关系，
最后只报告实际改动与仍未解决的记录。
```

也可以把维护任务压成一条指令：

```text
@Zontex 检查全库重复条目与近义标签。先输出候选组、主条目、对象版本、影响数量和颜色策略；
把条目合并与标签合并分别汇总确认，确认后执行并回读验证。
```

或把一次阅读任务串起来：

```text
@Zontex 解析当前 Reader 文献，列出带精确定位的关键方法与结论段。等我选定后创建 highlight，
为注释添加少量受控标签，再用 Zotero 原生路径生成结构化笔记并定位回父条目。
```

## English

Zontex lets Codex interpret requests, retrieve literature, and plan operations. Zotero Local API handles routine reads and writes, while the narrowly scoped Zontex Bridge supplies native maintenance, Reader, and annotation capabilities that the Local API does not expose.

### Features

#### Literature curation and library-wide deduplication

Zontex normalizes candidate literature by DOI, PMID, and title, with first author and year as supporting evidence. It searches the complete Zotero library before importing anything, reuses existing records, and imports only genuinely missing items.

```text
@Zontex Curate this citation list into “SDT Review”. Deduplicate it against my entire Zotero library, retain existing
records, import only genuinely missing literature, and summarize the metadata conflicts that require my decision.
```

<sup>*</sup>You can obtain a citation list from a `.pdf`, `.bib`, or another AI research tool such as Undermind. You can also ask Codex to search for literature by topic.

#### Metadata and reading workflow

##### Short version

Stock Zotero example:

```text
@Zontex Curate “SDT Review” using Zontex's default no-plugin profile. First inspect and reuse existing tags, colors,
and synonyms. Use StructuralDamage, VibrationAnalysis, SensorFusion, and FieldValidation as ordinary tags for topics
and methods. Use the colored /To Read, /Reading, and /Done tags for reading status, with at most one per item. Write
relevance to the current project as rate: N, from 1 to 5, in Extra. Do not create #Role tags in this run. Before
writing, list the tags to reuse, create, or assign colors to, together with the expected affected-item count. Wait for
my confirmation, apply the changes as one batch, and then read the items back to verify status and rating.
```

Ethereal Style example:

```text
@Zontex Curate “SDT Review” using Zontex's Ethereal Style-compatible profile. First inspect and reuse existing tags
and colors. Keep topical tags unprefixed. Use only the colored /To Read, /Reading, and /Done tags for reading status,
with at most one per item. Write relevance as rate: 1–5 in Extra. Add #Role/Core, #Role/Method, or #Role/Gap only
when a paper genuinely serves as core evidence, a method source, or evidence of a research gap, and do not assign
colors to these #Role tags. Before writing, provide one consolidated expected-count summary. Wait for my confirmation,
then apply the batch and read it back for verification.
```

You can replace the default names, colors, and role vocabulary without changing the structure:

```text
@Zontex Use the default profile above as a template, with these customizations:
Statuses: <status names, colors, and order>; colored topics: <the small set of topics allowed to receive colors>;
# tags: <allowed namespaces and vocabulary>; rate: <what each value from 1 to 5 means>.
First inspect the existing tags and colors. List reusable entries, naming conflicts, and migration counts without
writing anything. Wait for my confirmation before migrating and verifying the metadata.
```

> Note: Zotero does not define a tag vocabulary. The “stock profile” above is a no-plugin default supplied by this workflow. Ordinary tags, colored tags, and `#`-prefixed tags are not mutually incompatible data types; they are different uses or presentations of Zotero tags.

| Name | What is actually written to Zotero | Appearance in stock Zotero | Appearance in Ethereal Style |
| --- | --- | --- | --- |
| Ordinary tag | Tags such as `StructuralDamage`, `VibrationAnalysis`, and `SensorFusion` | Appears in the Tags pane and can be used for filtering | Remains an ordinary tag; by default it does not appear in a `#Tags` column configured to match only `#` |
| Colored tag | An ordinary tag plus a library-level native color and position, such as `/To Read` + blue | Appears as a colored mark beside the title and can be toggled with a number key | The `Tags` column can render it as a compact colored marker |
| Colored marker | No additional data | Has no independent stored counterpart | A visual rendering of a colored tag, not something that can be written separately |
| `#` tag | An ordinary tag whose name starts with `#`, such as `#Role/Method` | Appears under its literal name; `#` has no special meaning | The `#Tags` column displays it as text without the leading `#` by default and can use `/` as a hierarchy separator |
| Rating | One line from `rate: 1` through `rate: 5` in `Extra` | Stored as ordinary `Extra` metadata | Can be read and edited through the Rating interface |

Color and prefix are independent. `#Role/Method` does not receive a color merely because it starts with `#`, and `/To Read` appears as a colored marker only after a native Zotero color has been assigned. A `#` tag can also receive a color, but the default profile avoids that because the same tag could then appear both as a marker in `Tags` and as text in `#Tags`. Zotero allows [up to nine colored tags per library](https://www.zotero.org/support/collections_and_tags#colored_tags), so colors should be reserved for tags that need to be recognized at a glance or toggled by keyboard.

The default Zontex profile is:

- Use unprefixed ordinary tags for topics, methods, and data characteristics, such as `StructuralDamage`, `VibrationAnalysis`, `SensorFusion`, and `FieldValidation`. These tags may remain as detailed as the research requires; they are uncolored by default.
- Use `/To Read`, `/Reading`, and `/Done` for reading status. Assign native colors after the user agrees, and keep at most one status per item.
- Store relevance to the current project as `rate: N` in `Extra`. It does not represent paper quality or venue ranking.
- Optionally use `#Role/Core`, `#Role/Method`, and `#Role/Gap` for a paper's specific role in the research. These tags are uncolored by default, and not every paper needs one.
- The user can promote a few stable, frequently reused topics to colored tags. Zontex reads the existing color assignments and positions first and does not overwrite the user's configuration.

A complete metadata example for one paper is:

```text
Tags: StructuralDamage, SensorFusion, /Done, #Role/Core
Extra: rate: 5
```

In stock Zotero, all four entries under `Tags` are searchable tags, and `/Done` appears as a colored mark beside the title if a color has been assigned. In Ethereal Style, the same data can appear as a `/Done` status marker in `Tags`, `Role/Core` text in `#Tags`, and a rating of 5 in Rating. `StructuralDamage` and `SensorFusion` remain ordinary topical tags. To show ordinary topical tags in Ethereal Style's text-tag column, follow its [`#Tags` column rules](https://github.com/MuiseDestiny/zotero-style#tags-1) and set `Prefix` to `~~/`, which displays every tag that does not start with `/`. There is no need to rename every topical tag with a `#` prefix.

#### Library-wide tag maintenance

Zontex renames or merges tags with exact impact counts, an immediate pre-write recheck, and preservation of the target tag's native color so that concurrent changes cannot silently expand the operation.

```text
@Zontex Preview merging the library-wide tags “Structural Damage Detection” and “damage detection” into
“Damage Detection”. Show the count for each source tag and the resulting color, then wait for my confirmation.
```

#### Native item merging

Zontex calls Zotero's native merge module with an explicit master item and exact object versions. Attachments, notes, and related data are retained with the merged record.

```text
@Zontex Determine whether these two DOI records are duplicates. Compare their metadata and attachments, choose the
most complete record as the master item, and show me the merge plan before doing anything.
```

#### Reader context, citation rendering, and navigation

Zontex can identify the currently selected item or the PDF open in the Reader, generate citations and bibliography entries in a requested style, and open the corresponding item, attachment, or annotation.

```text
@Zontex Tell me which paper is currently open and generate its in-text citation and bibliography entry in APA.
Then locate the most important paper already present in the current collection in Zotero.
```

#### PDF annotations and notes

Zontex uses structured text blocks from the active PDF, exact offsets, and the source-document hash to create native highlights or underlines. It then uses Zotero's native path to assemble annotations into a note.

```text
@Zontex In the active PDF, highlight the complete sentence containing “stochastic damage tracking”, add the Method
tag, and then collect this paper's annotations into a single note.
```

Creating PDF annotations is currently experimental. Zotero 10.0.1 does not expose a public desktop write API for this operation, so the primary path first detects capabilities and then uses private Reader mapper and annotation-manager APIs. Zotero or private-API changes may break this path. `status` and `context` return compatibility warnings. Once a public API becomes available, it should become the primary path and the current implementation should remain only as a fallback.

Annotation deletion is the exception to the normal Trash policy. When a deletion target contains annotations, Zontex stops before making changes and warns that annotations cannot be restored. After the user confirms, ordinary items in the same batch go to Trash, while only the exact annotation keys are permanently deleted. If moving an ordinary item to Trash fails, Zontex does not proceed with annotation deletion. Deleting a paper or PDF directly continues to use Zotero's native Trash and parent-child cascade behavior.

#### CSL management

The Bridge uses Zotero's style manager to install CSL and validates citation and bibliography output with Zotero's native renderer.

```text
@Zontex Extract the citation and bibliography formats used by the current paper, generate and install a matching CSL
style, and compare the rendered output with the examples. If it does not match, revise the CSL and validate it again.
```

### One prompt, end-to-end

The following prompt combines candidate literature, deduplication, metadata planning, one consolidated confirmation, batch writing, and readback verification:

```text
@Zontex First run status --require-write. Read the citation list I provide and create or reuse the “SDT Review”
collection. Deduplicate every candidate against the complete Zotero library by DOI, PMID, title, first author, and
year. Reuse existing records and import only genuinely missing literature. Then provide one consolidated decision
list covering provenance, duplicates, metadata conflicts, missing fields, proposed imports, and the proposed rate,
/status, controlled topical tags, and necessary #Role tags. Combine all expected write counts into one confirmation.
After I confirm, execute the batch without asking item by item. Read the collection back and verify its item count,
at most one /status per item, the allowed role-tag vocabulary, rate values, and collection membership. Report only
the changes actually made and any unresolved records.
```

A maintenance task can also be expressed in one prompt:

```text
@Zontex Check the entire library for duplicate items and synonymous tags. First show candidate groups, proposed master
items, object versions, affected counts, and the color policy. Consolidate item merges and tag merges into separate
confirmations. After confirmation, execute each batch and verify it by reading the affected records back.
```

Or combine a reading task into one prompt:

```text
@Zontex Resolve the paper open in the Reader and list its key method and conclusion passages with exact locations.
After I choose the passages, create the highlights, add a small set of controlled tags, use Zotero's native path to
create a structured note, and navigate back to the parent item.
```
