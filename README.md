# Zontex — Research library workflows for Codex and Zotero

> This repository is an independent open-source workflow adaptation. It is not developed by, endorsed by, or affiliated with Zotero, the Zotero project, OpenAI, or Ethereal Style and its author.

[中文](#中文) · [English](#english)

## 中文

### 这是什么

Zontex 是一套面向 Zotero 10 的本地研究资料工作流，由 Codex 插件和轻量的 Zontex Bridge 组成。Codex 负责理解任务、整理候选文献和执行写入规则；Bridge 补足 Zotero Local API 尚未开放的原生能力，不修改 Zotero 本体。

项目改编自 [OpenAI Zotero 插件](https://github.com/openai/plugins/tree/main/plugins/zotero)，增加了全库去重与结构化 metadata，覆盖标签维护和原生条目合并，并加入 Reader 操作与实验性 PDF 注释。它也兼容 Ethereal Style 工作流采用的<sup>*</sup> `/状态`、`rate: N` 和 `#标签`约定。

<sup>*</sup> 本项目不是 Ethereal Style 的分支、扩展或配套产品；“兼容”只表示写入的 Zotero metadata 能被采用相同约定的界面或工作流识别。

### 架构

| 组件 | 职责 |
| --- | --- |
| Zontex for Codex | 理解指令、检索与去重、规划写入、执行确认规则 |
| Zotero 授权 Local API | 文献库读取，item、collection、note 等常规 CRUD |
| Zontex Bridge | 彩色标签、CSL、Reader 上下文、原生渲染与导航、高影响维护及实验性注释 |

Bridge 是窄权限层，不提供任意代码执行端点，也不接管普通 CRUD。

### 能做什么

Zontex 可以整理文献列表并复用全库条目，也能维护 metadata 与阅读状态、合并标签和重复条目。它还支持渲染引文与 Reader 导航、CSL 管理，以及在当前 PDF 中创建实验性的原生 highlight 或 underline。

[查看完整功能、案例 prompt。“用一条指令串起工作流”](docs/workflows.md)

### Ethereal Style 标签与 metadata 约定

用户要求使用 Ethereal Style 约定时，默认按以下规则为条目添加 metadata：

- `/To Read`、`/Reading`、`/Done`：少量彩色 slash status；每个条目至多一个。
- `rate: 1` 至 `rate: 5`：写入 `Extra`，表示对当前课题的重要性，不代表期刊或作者质量。
- `Topic A`、`Method`、`Dataset`：不带 `#Topic/` 前缀的普通主题标签；只给少量稳定且高频的主题分配原生颜色。
- `#Role/Core`、`#Role/Method`、`#Role/Gap`：仅在必要时使用的三种角色标签。
- 彩色小圆点只表示 Zotero 原生彩色标签；`#` 或 `/` 前缀本身不会赋予颜色。

### 安装

#### 通过 Codex 安装（推荐）

把仓库 URL 或本地目录交给 Codex，然后直接发送：

```text
请从 <REPO_URL_OR_DIR> 安装 Zontex。检查环境并运行项目测试，构建本地发行包，把仓库添加为
Codex marketplace，再安装 Zontex。需要我在 Zotero 中安装 XPI 时，用最通俗的步骤告诉我点哪里；
不要跳过 Zotero 的确认。重启后运行 @Zontex status --require-write，确认插件和写入授权可用。
```

Codex 会处理构建、marketplace 和插件命令。Zotero 首次安装 XPI 的确认仍需由用户在 Plugins/Add-ons Manager 中完成。

#### 手动构建或通过 GitHub Release 安装

需要 Zotero 10.0.x、Python 3 和支持本地 marketplace 的 Codex Desktop。

从源码构建并安装：

```powershell
python .\scripts\build_release.py --clean
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zontex@zontex-zotero-librarian
```

随后在 Zotero 的 Plugins/Add-ons Manager 中选择 **Install Add-on From File**，安装 `dist\zontex-bridge-<VERSION>.xpi` 并重启 Zotero。

通过 GitHub Release 安装时，下载同版本的 `zontex-<VERSION>.zip` 与 `zontex-bridge-<VERSION>.xpi`，核对 `checksums.json`，将 ZIP 解压到稳定目录后重复上述 marketplace 与 XPI 步骤。

[查看完整安装、更新与卸载说明](docs/installation.md)

### 更新

如果最初把仓库交给 Codex，直接说：

```text
检查 Zontex 是否有更新。先判断当前安装来自 Git checkout 还是 GitHub Release，只预览版本、改动和校验信息；
发现本地改动或需要替换文件时先停下，得到我确认后再更新，并在完成后重新运行 @Zontex status --require-write。
```

手动检查 Release 安装包：

```powershell
python .\plugins\zontex\scripts\update_release.py
```

确认后再运行：

```powershell
python .\plugins\zontex\scripts\update_release.py --apply --yes --reinstall-codex
```

Bridge 使用 Zotero 原生附加组件更新机制。Git checkout 不会被更新器覆盖，应先处理本地改动，再使用 `git pull --ff-only`。

### 写入安全

- 每个任务的第一项 Zotero 操作是 `status --require-write`；API、授权或 Bridge 能力不足时立即停止。
- 多条目导入和 metadata 批次只做一次汇总确认。
- 标签维护和原生条目合并要求精确影响数量或对象版本。
- 过期的 SDT hash、标签数量或条目版本会在写入前终止操作。
- 删除优先移入 Zotero 回收站；永久删除仍需单独确认精确目标。

主动注释目前是实验性功能。Zotero 10.0.1 没有公开对应的桌面写入 API，因此当前实现使用经过能力探测的 Reader 私有 mapper 与 annotation manager。Zotero 版本变化、公开 API 出现或私有接口失效时，`status` 和 `context` 会返回兼容性提醒；公开 API 可用后应成为主路径，私有实现只保留为 fallback。

### 开发

```powershell
python -m unittest discover -s .\plugins\zontex\tests -v
python -m unittest discover -s .\tests -v
node .\tests\bridge_contract.test.cjs
python .\scripts\build_release.py --clean
```

项目自有代码采用 [GNU General Public License v3.0 only](LICENSE)。改编自 OpenAI Zotero 插件的部分保留其 MIT 声明，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## English

### What is Zontex?

Zontex is a local research-library workflow for Zotero 10, made up of a Codex plugin and the lightweight Zontex Bridge. Codex interprets requests, curates candidate literature, and applies the write policy. The Bridge fills in native capabilities that Zotero Local API does not yet expose, without modifying Zotero itself.

The project adapts the [OpenAI Zotero plugin](https://github.com/openai/plugins/tree/main/plugins/zotero), adding library-wide deduplication and structured metadata, tag maintenance and native item merging, Reader actions, and experimental PDF annotations. It is also compatible with the `/status`, `rate: N`, and `#tag` conventions used by Ethereal Style workflows.<sup>*</sup>

<sup>*</sup> Zontex is not a fork, extension, or companion product of Ethereal Style. “Compatible” only means that the Zotero metadata written by Zontex can be recognized by interfaces or workflows that use the same conventions.

### Architecture

| Component | Responsibility |
| --- | --- |
| Zontex for Codex | Interpret requests, retrieve and deduplicate literature, plan writes, and enforce confirmation rules |
| Authorized Zotero Local API | Read the library and perform routine CRUD for items, collections, notes, and related objects |
| Zontex Bridge | Manage colored tags and CSL; resolve Reader context; provide native rendering and navigation; perform high-impact maintenance and experimental annotations |

The Bridge is a narrowly scoped capability layer. It exposes no arbitrary-code execution endpoint and does not take over routine CRUD.

### What it can do

Zontex can curate literature lists while reusing records already present anywhere in the library. It can also maintain metadata and reading status, merge tags and duplicate items, render citations, navigate the Reader, manage CSL styles, and create experimental native highlights or underlines in the active PDF.

[See all features, example prompts, and the “one prompt, end-to-end workflow” examples](docs/workflows.md#english).

### Ethereal Style tag and metadata conventions

When the user requests the Ethereal Style conventions, Zontex applies the following defaults:

- `/To Read`, `/Reading`, and `/Done`: a small set of colored slash-prefixed status tags, with at most one status per item.
- `rate: 1` through `rate: 5`: stored in `Extra` to express relevance to the current project, not the quality of the venue or authors.
- `Topic A`, `Method`, and `Dataset`: ordinary topical tags without a `#Topic/` prefix. Native colors are reserved for a small number of stable, frequently reused topics.
- `#Role/Core`, `#Role/Method`, and `#Role/Gap`: three optional role tags, used only when they add useful information.
- A colored marker represents a native Zotero colored tag. A leading `#` or `/` does not assign a color by itself.

### Installation

#### Install through Codex (recommended)

Give Codex the repository URL or local directory, then send:

```text
Install Zontex from <REPO_URL_OR_DIR>. Check the environment and run the project tests, build the local release
packages, register the repository as a local Codex marketplace, and install Zontex. When I need to install the XPI
in Zotero, stop and explain in plain language exactly which menu to open and which file to select. Do not bypass
Zotero's confirmation. After Zotero restarts, run @Zontex status --require-write and verify that the plugin and
persistent write authorization are available.
```

Codex handles the build, marketplace, and plugin commands. The user must still approve the first XPI installation in Zotero's Plugins/Add-ons Manager.

#### Build manually or install from a GitHub Release

You need Zotero 10.0.x, Python 3, and a Codex Desktop version that supports local marketplaces.

Build and install from source:

```powershell
python .\scripts\build_release.py --clean
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zontex@zontex-zotero-librarian
```

In Zotero's Plugins/Add-ons Manager, choose **Install Add-on From File**, install `dist\zontex-bridge-<VERSION>.xpi`, and restart Zotero.

For a GitHub Release installation, download `zontex-<VERSION>.zip` and `zontex-bridge-<VERSION>.xpi` from the same release, verify them against `checksums.json`, extract the ZIP to a stable directory, and repeat the marketplace and XPI steps above.

[See the full installation, update, and uninstall guide](docs/installation.md#english).

### Updating

If you originally gave the repository to Codex, send:

```text
Check whether Zontex has an update. First determine whether the current installation comes from a Git checkout or
a GitHub Release. Preview only the versions, changes, and verification information. If there are local changes or
files would be replaced, stop and wait for my confirmation before updating. When finished, rerun
@Zontex status --require-write.
```

To inspect a Release update manually:

```powershell
python .\plugins\zontex\scripts\update_release.py
```

After reviewing and approving the update, run:

```powershell
python .\plugins\zontex\scripts\update_release.py --apply --yes --reinstall-codex
```

The Bridge uses Zotero's native add-on update mechanism. The updater will not overwrite a Git checkout; resolve local changes first, then use `git pull --ff-only`.

### Write safety

- The first Zotero operation in every task is `status --require-write`. Stop immediately if the API, authorization, or required Bridge capability is unavailable.
- Multi-item imports and metadata batches receive one consolidated confirmation.
- Tag maintenance and native item merging require an exact affected-item count or object versions.
- A stale SDT hash, tag count, or item version stops the operation before any write.
- Prefer moving items to Zotero's trash. Permanent deletion still requires a separate confirmation of the exact target.

Active annotation is experimental. Zotero 10.0.1 does not expose a public desktop write API for this operation, so the current implementation feature-detects private Reader mapper and annotation-manager APIs. `status` and `context` report Zotero version drift, a newly available public API, or a private API that no longer works. Once a public API is available, it should become the primary path and the private implementation should remain only as a fallback.

### Development

```powershell
python -m unittest discover -s .\plugins\zontex\tests -v
python -m unittest discover -s .\tests -v
node .\tests\bridge_contract.test.cjs
python .\scripts\build_release.py --clean
```

Project-authored code is licensed under the [GNU General Public License v3.0 only](LICENSE). Portions adapted from the OpenAI Zotero plugin retain their MIT notice; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
