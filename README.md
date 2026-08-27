# Zontex

> Research library workflows for Codex and Zotero

> This repository is an independent open-source workflow adaptation. It is not developed by, endorsed by, or affiliated with Zotero, the Zotero project, OpenAI, or Ethereal Style and its author.

[中文](#中文) · [English](#english)

## 中文

### 这是什么

Zontex 是一套面向 Zotero 10 的本地研究资料工作流，由 Codex 插件和轻量的 Zontex Bridge 组成。Codex 负责理解任务、整理候选文献和执行写入规则；Bridge 只补足 Zotero Local API 尚未开放的原生能力，不修改 Zotero 本体。

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

[查看完整功能、案例 prompt 与“一条指令串起工作流”](docs/workflows.md)

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

Zontex provides local research-library workflows for Zotero 10 through a Codex plugin and a narrow companion Bridge. It curates and deduplicates literature, manages structured metadata and CSL styles, performs guarded native maintenance, resolves Reader context, and supports experimental native PDF highlights and underlines. Zotero itself remains unmodified.

See [features and end-to-end prompts](docs/workflows.md) or the [installation and update guide](docs/installation.md).

### Install with Codex

Give Codex the repository URL or local path and ask it to test, build, add the local marketplace, install Zontex, and guide you through the one Zotero UI confirmation required for the XPI. Start the next task with `@Zontex status --require-write`.

### Manual build

```powershell
python .\scripts\build_release.py --clean
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zontex@zontex-zotero-librarian
```

Install the matching `dist\zontex-bridge-<VERSION>.xpi` in Zotero and restart it. A GitHub Release installation uses the same-version Zontex ZIP and Bridge XPI plus the published checksums.

Active PDF annotation is experimental and currently depends on feature-detected private Zotero Reader APIs. Project-authored code is licensed under [GPL-3.0-only](LICENSE); upstream MIT notices are retained in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
