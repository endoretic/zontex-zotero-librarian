# Research library workflows for Codex and Zotero

这是一套面向 Zotero 10 的本地研究资料工作流，由 Codex 插件和轻量 Zotero Bridge 组成。Codex 负责理解任务、整理候选和执行安全策略；Bridge 只补足 Zotero Local API 没有开放的原生能力。Zotero 本体保持不变。

项目改编自 [OpenAI 官方 Zotero 插件](https://github.com/openai/plugins/tree/main/plugins/zotero)，扩展了文献整理与结构化 metadata，还加入 Reader 操作和 PDF 注释。项目与 Zotero、OpenAI 及 Ethereal Style 均无隶属关系。

## 架构

| 组件 | 职责 |
| --- | --- |
| Codex 插件 | 从任务理解到写入计划；负责检索、去重与确认策略，并封装命令 |
| Zotero 授权 Local API | 文献库读取及 collection/条目 CRUD；附件文本和 BibTeX/RIS |
| Zotero Modified Bridge | 彩色标签与 CSL；Reader 上下文及原生渲染/导航；高影响维护和实验性 PDF 注释 |

Bridge 是窄权限层，不提供任意代码执行端点，也不接管普通条目 CRUD。

## 功能

### 文献库整理

通过 Zotero 授权 Local API 完成搜索、导入和 collection 管理，并按 DOI、规范化标题及作者/年份匹配全库，避免重复导入。

> Prompt：从这份参考文献列表创建 collection“单细胞去卷积”，先与整个 Zotero 文献库去重，列出复用和新增条目；我确认一次后再写入。

### Metadata 与阅读流程

通过 Local API 修改字段、collection membership 和 Extra，配合 Bridge 写入 Zotero 原生彩色标签；状态使用 /To Read、/Reading、/Done，相关度使用 rate: 1–5。

> Prompt：把这个 collection 的文献按课题相关度写入 rate: 1–5，每篇只保留一个阅读状态，并复用现有主题标签。

### 全库标签维护

通过 Zotero.Tags.rename 原生重命名或合并标签；写入前后都核对受影响条目数，目标标签已有颜色时保留目标颜色。

> Prompt：把“scRNA seq”和“single cell RNA sequencing”合并到“scRNA-seq”，先告诉我各自影响多少条文献和最终颜色。

### 原生条目合并

通过 Zotero 的 mergeItems 模块合并顶层普通条目；操作前锁定每个对象版本，完成后核对 collection、附件和笔记是否都归入主条目。

> Prompt：检查这三条是否为同一篇论文；如果是，列出主条目、被合并条目和对象版本，等我确认后用 Zotero 原生合并。

### Reader 上下文、引用渲染与导航

通过 context 区分文献库选择和当前 Reader，通过 Zotero QuickCopy 原生渲染引文或参考文献，并用 navigate 打开条目、附件或注释。

> Prompt：读取我现在打开的 PDF 对应条目，用当前 Zotero 样式生成参考文献，然后定位到我选中的注释。

### PDF 注释与笔记

通过 Structured Document Text 把精确文本范围映射为 Zotero 原生 highlight 或 underline，并可调用 Zotero 的注释转笔记流程；sourceHash 防止文档变化后误写旧位置。

> Prompt：在当前 PDF 中给“Missing cell types”加黄色高亮，给“single-cell references”加蓝色下划线，再把两条注释按文档顺序生成笔记。

主动注释目前是实验性功能。Zotero 10.0.1 没有公开对应的桌面写入 API，因此 Bridge 使用经过能力探测的 Reader 私有 mapper 和 annotation manager。Zotero 版本变化、公开 API 出现或私有接口失效时，status 和 context 会返回兼容性提醒。公开 API 可用后，它应成为主路径，现有私有实现只保留为 fallback。

### CSL 管理

通过 Bridge 调用 Zotero 原生样式接口完成 CSL 校验、安装和卸载；卸载前保留备份，render 可直接检查实际引文与参考文献输出。

> Prompt：安装这个 CSL，用我选中的三篇文献分别预览文内引用和参考文献；格式不对时继续修改并复测。

## 写入安全

- 每个任务的第一项 Zotero 操作是 status --require-write；API、写入授权或 Bridge 能力不足时立即停止。
- 单条非破坏性写入可直接执行。多条目导入和 metadata 批次只做一次汇总确认。
- 标签维护和原生条目合并属于高影响写入，必须确认精确影响数量或对象版本。
- SDT sourceHash、标签影响数或条目版本过期时返回冲突，不沿用旧定位重试。
- 删除优先移入 Zotero 回收站；永久删除仍要求精确目标和单独确认。

本地写入密钥存放在当前 Windows 用户的 Local AppData，不进入仓库。

## 安装

需要 Zotero 10.0.x、Python 3 和支持本地 marketplace 的 Codex Desktop。

从源码构建：

~~~powershell
python .\scripts\build_release.py --clean
~~~

安装 Codex 插件：

~~~powershell
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zotero-modified@zotero-modified-private
~~~

随后在 Zotero 的附加组件管理器中选择“Install Add-on From File”，安装 dist 目录下同版本的 zotero-modified-bridge-<VERSION>.xpi 并重启 Zotero。新建 Codex 任务后先运行：

~~~text
@Zotero Modified status --require-write
~~~

Release 中的 Codex ZIP 与 Bridge XPI 必须使用相同版本。安装程序不会绕过 Zotero 的附加组件确认界面。

## 更新与卸载

Codex 插件更新器默认只检查版本和校验信息：

~~~powershell
python .\plugins\zotero-modified\scripts\update_release.py
~~~

确认更新后再执行：

~~~powershell
python .\plugins\zotero-modified\scripts\update_release.py --apply --yes --reinstall-codex
~~~

Bridge 使用 Zotero 原生附加组件更新机制；私有 Release 无法提供匿名更新时，应手动安装已校验的 XPI。

卸载时先从 Codex 移除插件，再从 Zotero 移除 Bridge 并重启，最后删除 marketplace 目录。

## 开发

~~~powershell
node .\tests\bridge_contract.test.cjs
python -m unittest discover -s .\plugins\zotero-modified\tests -v
python -m unittest discover -s .\tests -v
python .\scripts\build_release.py --clean
~~~

运行时代码、Bridge 及技能或构建脚本进入 main 后，发布工作流会提升 patch 版本并同时构建 Codex ZIP 与 XPI。README、测试和展示 metadata 的单独修改不触发 Release。

## License

项目自有代码采用 [GNU General Public License v3.0 only](LICENSE)。改编自 OpenAI Zotero 插件的部分保留其 MIT 声明，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

---

## English

This repository provides local research-library workflows for Zotero 10 through a Codex plugin and a narrow Zotero Bridge. Codex handles task planning, curation, and write policy. The Bridge exposes only native Zotero capabilities missing from the stock Local API; it does not patch Zotero itself.

The project adapts the [official OpenAI Zotero plugin](https://github.com/openai/plugins/tree/main/plugins/zotero) and adds structured curation, Reader actions, maintenance tools, and PDF annotations. It is not affiliated with Zotero, OpenAI, or Ethereal Style.

### Components

| Component | Role |
| --- | --- |
| Codex plugin | Task interpretation, search, deduplication, write planning, confirmation policy |
| Authorized Zotero Local API | Library reads, item and collection CRUD, indexed text, BibTeX/RIS |
| Zotero Modified Bridge | Colored tags, CSL, Reader context, native rendering/navigation, maintenance, experimental annotations |

### Features

- **Library curation.** The authorized Local API handles search, imports, collection management, and library-wide matching by DOI, normalized title, and author/year.

  **Prompt:** “Create a collection from this reference list, deduplicate it against my whole Zotero library, and ask once before writing the batch.”

- **Metadata workflows.** Local API patches preserve unrelated fields, while the Bridge manages native colored tags; reading state uses /To Read, /Reading, or /Done and project relevance uses rate: 1–5.

  **Prompt:** “Rate this collection for my review, keep one reading status per paper, and reuse the existing topic vocabulary.”

- **Tag maintenance.** Native Zotero tag rename/merge operations recheck exact impact counts and preserve the target tag color.

  **Prompt:** “Merge these two tag aliases into scRNA-seq, but first show the affected item counts and resulting color.”

- **Native item merge.** Zotero's mergeItems module merges top-level regular items after exact object-version checks, followed by readback verification of collections and child items.

  **Prompt:** “Check whether these records are duplicates, choose a master, and wait for my approval before using Zotero's native merge.”

- **Reader context, rendering, and navigation.** context resolves the selected library item and active Reader separately, QuickCopy renders native citations, and navigate opens items, attachments, or annotations.

  **Prompt:** “Render the open paper with my current Zotero style and navigate to the selected annotation.”

- **PDF annotations and notes.** SDT offsets map exact text to native highlights or underlines, sourceHash rejects stale locations, and Zotero's native flow converts annotations to a note.

  **Prompt:** “Highlight this phrase, underline the method name, and turn both annotations into a note in document order.”

- **CSL management.** The Bridge validates, installs, backs up, and removes CSL styles; render checks Zotero's actual citation and bibliography output.

  **Prompt:** “Install this CSL and test both citation and bibliography output with the three selected papers.”

Active annotation is experimental. Zotero 10.0.1 has no public desktop write API for this operation, so the current backend feature-detects private Reader mapper/manager methods. status and context report version drift, a newly available public API, or a broken private surface. A future public API should become primary, leaving the private adapter as fallback.

### Safety

- Start every task with status --require-write.
- Small non-destructive writes can proceed directly; multi-item batches receive one consolidated confirmation.
- Tag maintenance and native item merge require exact impact counts or object versions.
- Stale hashes, counts, or versions abort before mutation.
- Trash is preferred over permanent deletion.

The local write key stays in the current Windows user's Local AppData.

### Install

Build and add the local marketplace:

~~~powershell
python .\scripts\build_release.py --clean
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zotero-modified@zotero-modified-private
~~~

Install the same-version Bridge XPI from dist through Zotero's Add-ons Manager, restart Zotero, then start a new task with:

~~~text
@Zotero Modified status --require-write
~~~

The Codex ZIP and Bridge XPI in a Release must have the same version.

### Update

~~~powershell
python .\plugins\zotero-modified\scripts\update_release.py
python .\plugins\zotero-modified\scripts\update_release.py --apply --yes --reinstall-codex
~~~

The first command only checks. Run the second after reviewing and approving the update.

### License

Project-authored code is licensed under [GPL-3.0-only](LICENSE). Adapted portions of the OpenAI Zotero plugin retain their MIT notice in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
