# Zontex 功能与工作流 / Features and Workflows

[中文](#中文) · [English](#english) · [返回 README / Back to README](../README.md)

## 中文

Zontex 让 Codex 负责理解任务、检索与规划，让 Zotero Local API 处理常规读写，再由窄权限的 Zontex Bridge 补足原生维护、Reader 和注释能力。

### 功能

#### 文献整理与全库去重

候选文献有 DOI、PMID、ISBN 等唯一标识时，优先使用其中已有的一种精确查找，不额外跨数据库核验；没有标识时由 agent 根据给定来源补齐普通引文字段，再以规范化标题、首位作者和年份辅助全库去重。Zontex 只导入真正缺失的条目并复用已有记录。

```text
@Zontex 把这份引文列表整理进 “SDT Review”：全库去重，保留已有条目，只导入真正缺失的文献，并汇总需要我决定的 metadata 冲突。
```

<sup>*</sup>你可以从`.pdf`,`.bib`……或其它AI研究工具（如Undermind）中获得引文列表，当然也可以让codex自己按主题检索。

#### Metadata 与阅读流程

##### 太长不看版

原生 Zotero 示例：

```text
@Zontex 按 ethereal-default-v2 整理 “SDT Review”。先读取文献库现有九色配置；若调色板需要迁移，
把它作为单独的全库操作列出并等我确认。每篇保留一个 /阅读状态，选择一个主要 Role，按证据添加至多两个
Gap/Signal，使用 1–3 个 #Topic/ 受控主题，并把相关度写成 Extra 中唯一一行 rate: 1–5。
新条目状态用 /To Read，已有手动状态不要覆盖。汇总数量后一次确认、批量写入并回读验证。
```

Ethereal Style 示例：

```text
@Zontex 按 Zontex 的 Ethereal Style 兼容默认方案整理 “SDT Review”。让 /To Read、/Reading、/Done
提供三种可手动切换的状态，但每篇只保存当前一个；从 Role/Core、Role/Method、Role/Context 中选一个主要角色，
有依据时再添加 Role/Gap、Signal/Resource 或 Signal/Validation，Role/Signal 合计 1–3 个；
主题写为 1–3 个 #Topic/<规范名称>，相关度写为 rate: 1–5。不要为 Topic 分配原生颜色。
写入前只给一份汇总；我确认后批量执行并回读检查。
```

这两条 prompt 写入的是同一份 Zotero 数据；区别只在于你主要使用原生界面还是 Ethereal Style 的显示列。可以直接替换默认名称、颜色和词表，而不改变结构：

```text
@Zontex 以上述默认方案为模板，但使用以下自定义：
状态：<状态名称、颜色和顺序>；主要 Role 与可选 Signal：<词表、颜色和含义>；
Topic：<命名空间与受控词表>；rate：<1–5 各自代表什么>。
保持原生彩色标签总数不超过 9。先读取现有标签与颜色，列出冲突和迁移数量，不要立即写入；
等我确认后再迁移调色板，条目 metadata 另行批量写入并验证。
```

> Zotero 本身没有规定标签词表。Zontex 提供的是一套可修改的默认方案；原生颜色属于整个文献库，条目标签则属于单条文献。两者不会因为一次 metadata 写入自动互相改动。

[查看九色表、完整示例、引文标识规则与自定义方法](tag-metadata-conventions.md)

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
候选有 DOI、PMID、ISBN 等唯一标识就优先用已有的一种精确查找，不做跨数据库交叉验证；没有标识时，
根据我提供的来源补齐普通引文字段但不要编造标识，再以标题、首位作者和年份辅助全库去重。
复用已有记录，只导入真正缺失的文献。然后给出一份合并后的决策清单：来源、重复项、缺失字段、
拟导入条目，以及 rate、/状态、Role/Signal 和 #Topic 方案。把所有预计写入数量汇总成一次确认；
我确认后再执行，不要逐条询问。完成后回读 collection，检查条目数、每条一个状态、Role/Signal 范围、Topic、rate 和成员关系，
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

When a candidate has a DOI, PMID, ISBN, or another unique identifier, Zontex uses whichever identifier is available for exact lookup without cross-validating it against another database. Without an identifier, the agent completes ordinary citation fields from the supplied source and uses normalized title, first author, and year as fallback evidence. It searches the complete Zotero library, reuses existing records, and imports only genuinely missing items.

```text
@Zontex Curate this citation list into “SDT Review”. Deduplicate it against my entire Zotero library, retain existing
records, import only genuinely missing literature, and summarize the metadata conflicts that require my decision.
```

<sup>*</sup>You can obtain a citation list from a `.pdf`, `.bib`, or another AI research tool such as Undermind. You can also ask Codex to search for literature by topic.

#### Metadata and reading workflow

##### Short version

Stock Zotero example:

```text
@Zontex Curate “SDT Review” with ethereal-default-v2. Inspect the library's existing nine-color palette first; if it
needs migration, present that as a separate library-wide operation and wait for my confirmation. Keep one reading
status per paper, choose one primary Role, add at most two evidence-supported Gap/Signal tags, assign one to three
controlled #Topic/ tags, and store relevance as the only rate: 1–5 line in Extra. Use /To Read for new items, but do
not overwrite an existing manual status. Confirm once, write as a batch, and verify by reading the items back.
```

Ethereal Style example:

```text
@Zontex Curate “SDT Review” with Zontex's default Ethereal Style-compatible profile. Offer /To Read, /Reading, and
/Done as three manually switchable choices, while storing only the current one on each paper. Choose one of Role/Core,
Role/Method, or Role/Context as the primary role; add Role/Gap, Signal/Resource, or Signal/Validation only when the
paper supports it, for one to three Role/Signal tags in total. Assign one to three #Topic/<CanonicalName> tags and
rate: 1–5, without giving Topic tags native colors. Provide one summary before writing; after I confirm, apply the
batch and verify it by readback.
```

Both prompts write the same Zotero data; only the interface used to view it differs. You can replace the default names, colors, and vocabulary without changing the structure:

```text
@Zontex Use the default profile above as a template, with these customizations:
Statuses: <names, colors, and order>; primary Roles and optional Signals: <vocabulary, colors, and meanings>;
Topics: <namespace and controlled vocabulary>; rate: <what values 1 through 5 mean>. Keep the native colored-tag
total at nine or fewer. Inspect the existing tags and colors first, then list conflicts and migration counts without
writing. Wait for my confirmation before migrating the palette; write and verify item metadata as a separate batch.
```

> Zotero itself does not define a tag vocabulary. Zontex supplies a configurable default. Native colors belong to the library, while tag assignments belong to individual items; an item metadata write does not silently reconfigure the palette.

[See the complete nine-color palette, item example, identifier policy, and customization guidance](tag-metadata-conventions.md#english).

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
collection. If a candidate has a DOI, PMID, ISBN, or another unique identifier, use whichever identifier is present
for exact lookup without cross-validating it against another database. If none is present, complete ordinary citation
fields from my supplied source without inventing an identifier, then use title, first author, and year as fallback
deduplication evidence. Reuse existing records and import only genuinely missing literature. Provide one decision list
covering provenance, duplicates, missing fields, proposed imports, and the rate, /status, Role/Signal, and #Topic plan.
Combine all expected writes into one confirmation. After I confirm, execute the batch without asking item by item.
Read the collection back and verify item count, one status per item, Role/Signal and Topic rules, ratings, and membership.
Report only the changes actually made and any unresolved records.
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
