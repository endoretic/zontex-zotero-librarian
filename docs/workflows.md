# Zontex 功能与工作流

[返回 README](../README.md)

Zontex 让 Codex 负责理解任务、检索与规划，让 Zotero Local API 处理常规读写，再由窄权限的 Zontex Bridge 补足原生维护、Reader 和注释能力。

## 功能

### 文献整理与全库去重

通过 DOI、PMID 和标题，结合首位作者与年份归一化候选文献，先查完整 Zotero 文献库，再只导入缺失条目并复用已有记录。

```text
@Zontex 把这份引文列表整理进 “SDT Review”：全库去重，保留已有条目，只导入真正缺失的文献，并汇总需要我决定的 metadata 冲突。
```

### Metadata 与阅读流程

通过 Zotero 原生字段、`Extra` 和受控标签维护 `rate: N` 与唯一的 `/状态`；主题标签保持普通，`#Role/...` 角色标签只保留少量。

```text
@Zontex 把 “SDT Review” 里的核心方法论文设为 rate: 5 和 /To Read，复用现有主题词，不要给每篇文章生成一次性标签。
```

### 全库标签维护

通过精确计数、写入前复核和原生颜色保留完成标签改名或合并，避免并发修改扩大影响范围。

```text
@Zontex 预览把全库的 “Structural Damage Detection” 和 “damage detection” 合并到 “Damage Detection”；列出数量与颜色，等我确认后执行。
```

### 原生条目合并

通过显式主条目和对象版本调用 Zotero 原生 merge 模块合并重复记录，附件、笔记及关联数据一并保留。

```text
@Zontex 找出这两个 DOI 重复条目，比较 metadata 和附件，选择信息最完整的作为主条目；先给我合并预览。
```

### Reader 上下文、引用渲染与导航

通过当前窗口与 Reader 上下文解析目标，调用 Zotero 原生 CSL 预览，并按明确 key 定位条目、附件或注释。

```text
@Zontex 告诉我当前 Reader 打开的论文，用 APA 渲染它的参考文献条目，然后在 Zotero 中定位其父条目。
```

### PDF 注释与笔记

通过当前 PDF 的结构化文本段、精确偏移和源文档 hash 创建原生 highlight/underline，再用 Zotero 原生路径汇总为笔记。

```text
@Zontex 在当前 PDF 中高亮包含 “stochastic damage tracking” 的完整句子，加上 Method 标签，再把这篇论文的注释汇总成一条笔记。
```

主动创建 PDF 注释目前是实验性功能。Zotero 10.0.1 尚无公开的桌面写入接口，当前主路径会先做能力探测，再使用 Reader 私有 mapper 与 annotation manager；版本或接口变化可能使其失效。`status` 与 `context` 会返回兼容性提醒，未来公开接口出现后应改为主路径，现有实现只保留为 fallback。

### CSL 管理

通过 Bridge 调用 Zotero 样式管理器安装 CSL，并用原生渲染结果验证 citation 与 bibliography 输出。

```text
@Zontex 安装这份 CSL，分别渲染当前论文的文内引文和参考文献；如果结果不符合示例，帮我修改后重新验证。
```

## 用一条指令串起工作流

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
