# Zotero 标签与 metadata 约定 / Zotero Tag and Metadata Conventions

[中文](#中文) · [English](#english) · [返回工作流 / Back to workflows](workflows.md)

## 中文

| 名称 | 实际写入 Zotero 的内容 | 原生 Zotero 中的表现 | Ethereal Style 中的表现 |
| --- | --- | --- | --- |
| 普通标签 | `StructuralDamage`、`VibrationAnalysis`、`SensorFusion` 等标签 | 显示在标签面板中，可用于筛选 | 仍是普通标签；默认不会出现在只匹配 `#` 的 `#Tags` 列中 |
| 彩色标签 | 普通标签外加文献库级的原生颜色与位置，例如 `/To Read` + 蓝色 | 标题旁显示彩色色块，并可用数字键切换 | `Tags` 列可将它显示为紧凑的颜色标记 |
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

在原生 Zotero 中，这四项都是可搜索的标签，`/Done` 若已分配颜色，会在标题旁显示色块；在 Ethereal Style 中，同一份数据可表现为 `Tags` 列中的 `/Done` 颜色标记、`#Tags` 列中的 `Role/Core` 文字和 Rating 中的 5 分。`StructuralDamage` 与 `SensorFusion` 仍保留为普通主题标签。若希望普通主题标签也显示在 Ethereal Style 的文字标签列中，可以按其 [`#Tags` 列规则](https://github.com/MuiseDestiny/zotero-style#tags-1)把 `Prefix` 改为 `~~/`，显示所有不以 `/` 开头的标签；不必为此把全部主题标签改成 `#` 标签。

## English

| Name | What is actually written to Zotero | Appearance in stock Zotero | Appearance in Ethereal Style |
| --- | --- | --- | --- |
| Ordinary tag | Tags such as `StructuralDamage`, `VibrationAnalysis`, and `SensorFusion` | Appears in the Tags pane and can be used for filtering | Remains an ordinary tag; by default it does not appear in a `#Tags` column configured to match only `#` |
| Colored tag | An ordinary tag plus a library-level native color and position, such as `/To Read` + blue | Appears as a colored mark beside the title and can be toggled with a number key | The `Tags` column can render it as a compact colored marker |
| `#` tag | An ordinary tag whose name starts with `#`, such as `#Role/Method` | Appears under its literal name; `#` has no special meaning | The `#Tags` column displays it as text without the leading `#` by default and can use `/` as a hierarchy separator |
| Rating | One line from `rate: 1` through `rate: 5` in `Extra` | Stored as ordinary `Extra` metadata | Can be read and edited through the Rating interface |

Color and prefix are independent. `#Role/Method` does not receive a color merely because it starts with `#`, and `/To Read` appears as a colored marker only after a native Zotero color has been assigned. A `#` tag can also receive a color, but the default profile avoids that because the same tag could then appear both in `Tags` and in `#Tags`. Zotero allows [up to nine colored tags per library](https://www.zotero.org/support/collections_and_tags#colored_tags), so colors should be reserved for tags that need to be recognized at a glance or toggled by keyboard.

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

In stock Zotero, all four entries under `Tags` are searchable tags, and `/Done` appears as a colored mark beside the title if a color has been assigned. In Ethereal Style, the same data can appear as a `/Done` colored marker in `Tags`, `Role/Core` text in `#Tags`, and a rating of 5 in Rating. `StructuralDamage` and `SensorFusion` remain ordinary topical tags. To show ordinary topical tags in Ethereal Style's text-tag column, follow its [`#Tags` column rules](https://github.com/MuiseDestiny/zotero-style#tags-1) and set `Prefix` to `~~/`, which displays every tag that does not start with `/`. There is no need to rename every topical tag with a `#` prefix.
