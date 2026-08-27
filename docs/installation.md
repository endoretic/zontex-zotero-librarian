# 安装、更新与卸载 / Installation, Updates, and Uninstallation

[中文](#中文) · [English](#english) · [返回 README / Back to README](../README.md)

## 中文

### 通过 Codex 安装

最省事的方式是把仓库 URL 或本地目录交给 Codex，再粘贴下面这段话：

```text
请从 <REPO_URL_OR_DIR> 安装 Zontex。先检查 Zotero、Python 和 Codex 环境，运行项目测试并构建发行包；
然后把仓库注册为本地 Codex marketplace，安装 Zontex。遇到必须在 Zotero 里点选 XPI 的步骤时，
请停下来，用最通俗的方式告诉我打开哪个菜单、选择哪个文件。重启 Zotero 后运行
@Zontex status --require-write，确认 Local API、Bridge 和持续写入授权都可用。
```

Codex 应依次完成：

1. 检查依赖并运行 helper、Bridge contract 和 release 测试。
2. 构建 Codex 插件 ZIP、Zontex Bridge XPI、checksums 与 release notes。
3. 将仓库添加为本地 marketplace，并安装 `zontex@zontex-zotero-librarian`。
4. 指引你在 Zotero 的 Plugins/Add-ons Manager 中选择 **Install Add-on From File**。Zotero 的首次 XPI 安装确认必须由用户完成。
5. 重启后运行 `@Zontex status --require-write`。若提示授权，执行 `authorize-write`，在 Zotero 中选择 **Always Allow**，再重新检查状态。

### 手动从源码构建

需要 Zotero 10.0.x、Python 3、Node.js，以及支持本地 marketplace 的 Codex Desktop。

```powershell
python -m unittest discover -s .\plugins\zontex\tests -v
python -m unittest discover -s .\tests -v
node .\tests\bridge_contract.test.cjs
python .\scripts\build_release.py --clean
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zontex@zontex-zotero-librarian
```

在 Zotero 的 Plugins/Add-ons Manager 中安装 `dist\zontex-bridge-<VERSION>.xpi`，重启后运行 `@Zontex status --require-write`。

### 通过 GitHub Release 安装

从同一 Release 下载并核对：

- `zontex-<VERSION>.zip`：Codex marketplace 包；
- `zontex-bridge-<VERSION>.xpi`：Zotero 附加组件；
- `checksums.json`：两份安装包的 SHA-256；
- `release-notes.md`：兼容性与安装提示。

把 ZIP 解压到一个长期保留的目录，将该目录添加为 marketplace，再安装插件；XPI 仍通过 Zotero 界面安装。

### 更新

把下面的指令交给 Codex：

```text
检查 Zontex 是否有更新。先识别当前安装来自 Git checkout 还是 GitHub Release，只预览版本、Release 页面、
校验来源和本地改动；替换文件前必须得到我的确认。更新后重新运行测试和 @Zontex status --require-write。
```

Release 安装可以手动预览与应用：

```powershell
python .\plugins\zontex\scripts\update_release.py
python .\plugins\zontex\scripts\update_release.py --apply --yes --reinstall-codex
```

更新器会校验 `checksums.json`、同卷暂存并保留带时间戳的备份。它不会覆盖 Git checkout；源码安装应先处理本地改动，再运行 `git pull --ff-only`。Bridge 使用 Zotero 原生附加组件更新机制。

### 卸载与改名前版本迁移

- 在 Codex 中卸载 `zontex@zontex-zotero-librarian`，并按需移除本地 marketplace。
- 在 Zotero 的 Plugins/Add-ons Manager 中移除 **Zontex Bridge**。
- 如果从改名前版本迁移，先移除旧 Codex 插件与旧 Bridge，再按本页重新安装。
- 本次迁移修改了插件名、Bridge ID、API 路由、凭据目录和构建产物名；旧 Bridge 与旧 marketplace 不会作为兼容别名继续加载。

卸载插件不会删除 Zotero 文献库。需要清理下载包、备份或本地 checkout 时，应先确认精确路径。

## English

### Install through Codex

The simplest option is to give Codex the repository URL or local directory and paste the following prompt:

```text
Install Zontex from <REPO_URL_OR_DIR>. First check the Zotero, Python, and Codex environments, run the project tests,
and build the release packages. Then register the repository as a local Codex marketplace and install Zontex. When
the process reaches a step that requires me to select the XPI in Zotero, stop and explain in plain language which menu
to open and which file to select. After Zotero restarts, run @Zontex status --require-write and verify that Local API,
the Bridge, and persistent write authorization are all available.
```

Codex should complete these steps in order:

1. Check the dependencies and run the helper, Bridge contract, and release tests.
2. Build the Codex plugin ZIP, Zontex Bridge XPI, checksums, and release notes.
3. Add the repository as a local marketplace and install `zontex@zontex-zotero-librarian`.
4. Guide the user to **Install Add-on From File** in Zotero's Plugins/Add-ons Manager. The user must personally approve the first XPI installation in Zotero.
5. After restarting Zotero, run `@Zontex status --require-write`. If authorization is required, run `authorize-write`, choose **Always Allow** in Zotero, and check the status again.

### Build manually from source

You need Zotero 10.0.x, Python 3, Node.js, and a Codex Desktop version that supports local marketplaces.

```powershell
python -m unittest discover -s .\plugins\zontex\tests -v
python -m unittest discover -s .\tests -v
node .\tests\bridge_contract.test.cjs
python .\scripts\build_release.py --clean
codex plugin marketplace add "<REPO_DIR>"
codex plugin add zontex@zontex-zotero-librarian
```

Install `dist\zontex-bridge-<VERSION>.xpi` through Zotero's Plugins/Add-ons Manager. Restart Zotero, then run `@Zontex status --require-write`.

### Install from a GitHub Release

Download all of the following from the same Release and verify them together:

- `zontex-<VERSION>.zip`: the Codex marketplace package;
- `zontex-bridge-<VERSION>.xpi`: the Zotero add-on;
- `checksums.json`: SHA-256 checksums for both installation packages;
- `release-notes.md`: compatibility and installation notes.

Extract the ZIP to a directory that will remain in place, add that directory as the marketplace, and install the plugin. Install the XPI separately through Zotero's interface.

### Updating

Give Codex the following prompt:

```text
Check whether Zontex has an update. First determine whether the current installation comes from a Git checkout or a
GitHub Release. Preview only the versions, Release page, verification source, and local changes. You must obtain my
confirmation before replacing any file. After updating, rerun the tests and @Zontex status --require-write.
```

For a Release installation, you can preview and apply an update manually:

```powershell
python .\plugins\zontex\scripts\update_release.py
python .\plugins\zontex\scripts\update_release.py --apply --yes --reinstall-codex
```

The updater verifies `checksums.json`, stages the replacement on the same filesystem volume, and keeps a timestamped backup. It will not overwrite a Git checkout. For a source installation, resolve local changes first and then run `git pull --ff-only`. The Bridge uses Zotero's native add-on update mechanism.

### Uninstallation and migration from pre-rename versions

- Uninstall `zontex@zontex-zotero-librarian` from Codex and remove the local marketplace if it is no longer needed.
- Remove **Zontex Bridge** from Zotero's Plugins/Add-ons Manager.
- When migrating from a version installed before the project rename, remove the old Codex plugin and old Bridge first, then reinstall by following this page.
- The rename changed the plugin name, Bridge ID, API routes, credential directory, and build-artifact names. The old Bridge and old marketplace are not loaded as compatibility aliases.

Uninstalling the plugin does not delete the Zotero library. Before removing downloaded packages, backups, or a local checkout, verify the exact paths.
