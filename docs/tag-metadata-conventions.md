# Zotero 标签与 metadata 约定 / Zotero Tag and Metadata Conventions

[中文](#中文) · [English](#english) · [返回工作流 / Back to workflows](workflows.md)

## 中文

Zotero 实际保存的是标签和 `Extra` 字段。颜色不是另一类条目数据，而是一套由整个文献库共用的“标签名称 → 颜色与位置”配置。同一条目无论出现在哪些 collection 中，都只有一份标签与评级。

| 名称 | 实际写入 Zotero 的内容 | 原生 Zotero 中的表现 | Ethereal Style 中的表现 |
| --- | --- | --- | --- |
| 普通标签 | 任意 Zotero 标签，例如 `#Topic/SignalProcessing` | 显示在标签面板中，可搜索和筛选 | 是否显示及如何显示取决于对应列的前缀规则 |
| 原生彩色标签 | 普通标签外加文献库级的颜色与位置，例如 `/To Read` + 蓝色 | 标题旁显示颜色标记，并可用数字键切换 | `Tags` 列可显示为紧凑的彩色标记 |
| 阅读状态 | `/To Read`、`/Reading` 或 `/Done` | 三个普通标签，配置颜色后可快速识别和切换 | 菜单提供三个状态选项；单条文献只保存当前一个 |
| Role / Signal | `Role/Core`、`Role/Method` 等原生彩色标签 | 可搜索，并以固定颜色表示文献的长期用途 | 与状态一起显示为彩色标记；不依赖 `#` 前缀 |
| Topic | 以 `#Topic/` 开头的普通标签，例如 `#Topic/Benchmarking` | 按完整名称显示，`#` 没有特殊含义 | `#Tags` 列可显示为 `Topic/Benchmarking` 等文字层级 |
| 评级 | `Extra` 中恰好一行 `rate: 1` 至 `rate: 5` | 作为普通 `Extra` metadata 保存 | 可由 Rating 界面读取和修改 |

`#`、`/` 与颜色彼此独立。标签不会因为带前缀自动获得颜色；只有文献库的原生颜色配置会产生彩色显示。

### 默认九色配置

Zotero 每个文献库[最多可配置 9 个彩色标签](https://www.zotero.org/support/collections_and_tags#colored_tags)。Zontex 的 `ethereal-default-v2` 把这九个位置固定给三个阅读状态与六个跨领域 Role / Signal：

| 位置 | 标签 | 颜色 | 含义 |
| ---: | --- | --- | --- |
| 0 | `/To Read` | `#6196BC` | 尚未开始阅读 |
| 1 | `/Reading` | `#F2A65A` | 正在阅读 |
| 2 | `/Done` | `#59A14F` | 已完成当前阅读 |
| 3 | `Role/Core` | `#E15759` | 核心证据或核心论证 |
| 4 | `Role/Method` | `#B07AA1` | 方法、算法、协议或实现路线 |
| 5 | `Role/Gap` | `#EDC948` | 直接相关的研究缺口或局限 |
| 6 | `Role/Context` | `#9C755F` | 背景、机制或必要语境 |
| 7 | `Signal/Resource` | `#76B7B2` | 可复用的数据、代码、协议或其他资源 |
| 8 | `Signal/Validation` | `#FF9DA7` | benchmark、外部验证、复现或稳健性证据 |

这套词表全库稳定，不随 collection 临时变化。这样既不会让相同标签在不同批次中变色，也能保证每篇按默认规则整理的文献至少带有状态色和一个 Role 色。给文献分配标签不会改动调色板；首次配置或迁移调色板时，Zontex 应先读取现有九色并单独汇总冲突，得到确认后再替换。

### 每篇文献如何写

- 阅读状态：三选一。菜单里有三个选项，不代表每篇同时拥有三个状态；新导入且没有已知进度时可用 `/To Read`。
- 主要角色：从 `Role/Core`、`Role/Method`、`Role/Context` 中选一个。角色描述文献在整个研究资料库中的长期用途，不按 collection 重复定义。
- 可选信息：只有确实有依据时才加 `Role/Gap`、`Signal/Resource` 或 `Signal/Validation`；主要角色与这些可选标签合计 1–3 个。
- 主题：使用 1–3 个受控的 `#Topic/<CanonicalName>` 标签。复用已有规范名称，避免为每篇文献生成一次性标签；Topic 不占九色位置。
- 评级：在 `Extra` 中维护且只维护一行 `rate: N`。它表示对当前研究工作的相关度或优先级，不表示论文质量、期刊等级或作者水平。

一篇完整示例可以是：

```text
Tags: /Reading, Role/Method, Signal/Validation, #Topic/SignalProcessing, #Topic/Benchmarking
Extra: rate: 4
```

原生 Zotero 会把这些内容都作为可搜索标签保存，并用预设颜色显示前三个彩色标签。Ethereal Style 可以把阅读状态和 Role / Signal 显示为彩色标记，把两个 Topic 显示在 `#Tags` 文字列中，并从 `Extra` 读取 4 星评级。

批量写入时，agent 可以把不同条目的决定放进同一份 manifest：

```json
{
  "profile": "ethereal-default-v2",
  "items": [
    {
      "key": "ABCD2345",
      "expectedVersion": 4,
      "primaryRole": "Role/Method",
      "secondary": ["Signal/Validation"],
      "topics": ["#Topic/SignalProcessing", "#Topic/Benchmarking"],
      "rating": 4
    }
  ]
}
```

省略 `status` 表示保留现有手动状态；显式写入 `"status": "/Reading"` 才会修改它。`curate-metadata` 会先验证整份 manifest，再分批写入并统一回读。

### 引文标识与补全

候选文献有 DOI、PMID、ISBN 或其他可靠唯一标识时，优先使用其中已有的一种做精确查找和去重，不要求再去其他数据库交叉验证。没有唯一标识时，由 agent 根据用户提供的 PDF、引文列表或其他来源补齐标题、作者、年份、期刊等普通引文字段；不得编造 DOI、PMID 或 ISBN。本地去重在无标识时退回规范化标题、首位作者与年份。

### 如何修改这套方案

可以替换状态名称、颜色、Role / Signal 词表、Topic 命名和评级含义，但建议保留“少量稳定彩色维度 + 可扩展无色 Topic”的结构。若需要更多主题，不要突破九色限制；继续增加受控的 `#Topic/...` 即可。任何全库调色板迁移都应与条目 metadata 写入分开预览和确认。

## English

Zotero stores tags and the `Extra` field. Color is not a separate kind of item data; it is a library-wide mapping from a tag name to a native color and position. An item therefore has the same tags and rating in every collection that contains it.

| Name | What is actually written to Zotero | Appearance in stock Zotero | Appearance in Ethereal Style |
| --- | --- | --- | --- |
| Ordinary tag | Any Zotero tag, such as `#Topic/SignalProcessing` | Appears in the Tags pane and can be searched or filtered | Its visibility and rendering depend on the column's prefix rules |
| Native colored tag | An ordinary tag plus a library-level color and position, such as `/To Read` + blue | Appears as a colored mark beside the title and can be toggled with a number key | The `Tags` column can render it as a compact colored marker |
| Reading status | `/To Read`, `/Reading`, or `/Done` | Three ordinary tags that become easy to scan and toggle when colored | The menu offers three choices; an individual paper stores only its current one |
| Role / Signal | Native colored tags such as `Role/Core` and `Role/Method` | Searchable tags whose stable colors describe a paper's durable use | Rendered as colored markers alongside status; no `#` prefix is required |
| Topic | An ordinary tag starting with `#Topic/`, such as `#Topic/Benchmarking` | Appears under its full literal name; `#` has no special meaning | The `#Tags` column can show text such as `Topic/Benchmarking` as a hierarchy |
| Rating | Exactly one line from `rate: 1` through `rate: 5` in `Extra` | Stored as ordinary `Extra` metadata | Can be read and edited through the Rating interface |

Prefixes and color are independent. A tag does not become colored because it starts with `#` or `/`; only Zotero's native library palette controls colored rendering.

### Default nine-color palette

Zotero allows [up to nine colored tags per library](https://www.zotero.org/support/collections_and_tags#colored_tags). Zontex's `ethereal-default-v2` reserves all nine positions for three reading statuses and six cross-domain Role / Signal tags:

| Position | Tag | Color | Meaning |
| ---: | --- | --- | --- |
| 0 | `/To Read` | `#6196BC` | Reading has not started |
| 1 | `/Reading` | `#F2A65A` | Currently being read |
| 2 | `/Done` | `#59A14F` | Current reading is complete |
| 3 | `Role/Core` | `#E15759` | Core evidence or argument |
| 4 | `Role/Method` | `#B07AA1` | Method, algorithm, protocol, or implementation path |
| 5 | `Role/Gap` | `#EDC948` | A directly relevant research gap or limitation |
| 6 | `Role/Context` | `#9C755F` | Background, mechanism, or necessary context |
| 7 | `Signal/Resource` | `#76B7B2` | Reusable data, code, protocol, or another resource |
| 8 | `Signal/Validation` | `#FF9DA7` | Benchmark, external validation, replication, or robustness evidence |

This vocabulary is stable across the library rather than changing by collection. The same tag therefore keeps the same meaning and color across batches, while every paper curated under the default profile receives at least a status color and one Role color. Assigning tags to items does not change the palette. Before first-time setup or migration, Zontex should inspect the existing nine positions, summarize conflicts separately, and replace them only after confirmation.

### Per-paper assignments

- Reading status: choose one of the three. Three menu choices do not mean three simultaneous statuses; `/To Read` may be used for a new import when no reading progress is known.
- Primary role: choose exactly one of `Role/Core`, `Role/Method`, or `Role/Context`. This describes the paper's durable use across the research library, not a collection-specific role.
- Optional information: add `Role/Gap`, `Signal/Resource`, or `Signal/Validation` only when supported by the paper. Keep the primary role plus these optional tags to a total of one to three.
- Topics: assign one to three controlled `#Topic/<CanonicalName>` tags. Reuse canonical names instead of creating a one-off tag for every paper; Topic tags consume no native color positions.
- Rating: maintain exactly one `rate: N` line in `Extra`. It represents relevance or priority for the current research work, not paper quality, venue ranking, or author quality.

A complete item can look like this:

```text
Tags: /Reading, Role/Method, Signal/Validation, #Topic/SignalProcessing, #Topic/Benchmarking
Extra: rate: 4
```

Stock Zotero stores every entry as a searchable tag and uses the configured colors for the first three colored tags. Ethereal Style can render status and Role / Signal as colored markers, show the two Topic tags in its textual `#Tags` column, and read the four-star rating from `Extra`.

For batch writes, the agent can place heterogeneous per-item decisions in one manifest:

```json
{
  "profile": "ethereal-default-v2",
  "items": [
    {
      "key": "ABCD2345",
      "expectedVersion": 4,
      "primaryRole": "Role/Method",
      "secondary": ["Signal/Validation"],
      "topics": ["#Topic/SignalProcessing", "#Topic/Benchmarking"],
      "rating": 4
    }
  ]
}
```

Omitting `status` preserves the existing manual status; only an explicit value such as `"status": "/Reading"` changes it. `curate-metadata` validates the complete manifest before writing, then batches the updates and performs one consolidated readback.

### Citation identifiers and completion

When a candidate has a DOI, PMID, ISBN, or another reliable unique identifier, Zontex uses whichever identifier is available for exact lookup and deduplication without requiring cross-validation against another database. When no unique identifier is present, the agent completes ordinary citation fields—such as title, authors, year, and venue—from the PDF, citation list, or other source supplied by the user. It must never invent a DOI, PMID, or ISBN. Local deduplication falls back to normalized title, first author, and year when no identifier exists.

### Adapting the profile

You may replace status names, colors, the Role / Signal vocabulary, Topic names, or rating meanings, but the useful structure is “a small stable colored vocabulary plus extensible uncolored Topics.” To add more subject detail, extend the controlled `#Topic/...` vocabulary instead of exceeding the nine-color limit. Preview and confirm any library-wide palette migration separately from item metadata writes.
