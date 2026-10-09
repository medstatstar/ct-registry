# 已分析论文登记册（living registry）

> 单一事实来源：记录所有被评估并提议纳入 ct 系列的**外部论文 / 文章 / 工具介绍**。
> 维护规则：新论文评估完毕追加一行（**倒序，最新在上**）；只记结论与落地改进项，详细评估见各技能 CHANGELOG 与工作区日志。
> 评估方法论见 `docs/12-paper-improvement.md §21`；新评估填写模板见 `references/paper_eval_template.md`。

---

## 登记册

### 2026-10-06 · PharmaSUG 2026 AI-125「GenAI 进 ADaM 编程」
- **来源**：微信公众号解读文 `https://mp.weixin.qq.com/s/pjjTNThd6bIlxEe0mEXRfA`（已精读，置信度高；主题经 AI-125 论文内容核对）
- **主题**：用 GenAI + AWS Bedrock 增强 ADaM Spec 验证与 SAS 代码开发（Spec 验证前移 → 变量级生成 → 程序整合；raw/polished 双版；ToDo 占位符；JSON 结构化协议 + 多级兜底；自适应分块；治理留痕清单）
- **最相关技能**：ct-adam（高）/ ct-sdtm（中高）/ ct-tlf（中，上游质量）
- **结论**：印证并具体化用户 10-05 修正「LLM 自由生成可采纳但须标识」（与 ct-base §6.9 同源）；raw/polished 双版=留痕+标识工程实现，ToDo 占位符=把不确定留给人。
- **落地改进**：
  - ct-base §5 新增「出站上下文脱敏 — 内部规则与敏感示例值剔除」红线（D 方案）
  - ct-adam `AI_ADAM_GENERATION_DRAFT.md` 工程模式草稿（E 方案，强制绑定 §6.9 + §5）
- **未改动**：§6.9 无需改（论文仅印证）

### 2026-10-05 · PharmaSUG China 2026 AI201「ADaM2TFL」
- **来源**：论文 PDF（用户分享，已精读全文 6 页，置信度高）；公众号解读文 `https://mp.weixin.qq.com/s/QDrt1P9CJhk3enPn4x4Neg`
- **主题**：LLM-native TFL 自动化架构（compact skill file 喂上下文 + 可复用确定性工具 + agent 生成候选 R 程序；五阶段 Init→Parse(人工确认门)→Cache(源哈希/新鲜度)→Generate→Verify(结构检查)；6 设计模式；知识积累循环仍实验性）
- **最相关技能**：ct-tlf（高）/ ct-base（高，方法论）
- **结论**：方法论印证 > 新增能力；指出 ct-tlf 两缺口（ADaM 源完整性闸门、失败知识库模板）；论文自身定位探索性原型、强调「模型不是完整方案」。
- **落地改进**：
  - ct-base §6.9「AI 生成物标识与人工确认门」红线（A 方案，同步 AGENTS.md §4.1 + docs/03 §6.9）
  - ct-tlf v0.5.0 ADaM 源完整性闸门（B 方案：tlf_build.py + pub_tables.py 源指纹缓存 + 产物 `_source_fingerprint`）
  - 用户修正采纳：「LLM 自由生成代码可考虑，但需对结果明确标识」
- **未照搬**：不让 LLM 自由生成 R 程序（C 档可复现红线）；不引入 Word shell 解析（ct-tlf 用 r4csr mock shell 本地内置）

### 2026-10-05 · 微信公众号 gtsummary 介绍文
- **来源**：`https://mp.weixin.qq.com/s/3cdDYhEVKZlmP-nd3YT38A`（已读，置信度高）
- **主题**：gtsummary R 包（基于 gt）——医学期刊投稿表（Table 1 基线 + 自动 P 值 / 回归表 OR·HR+95%CI / 生存表；JAMA/Lancet/NEJM 主题；导出 docx/xlsx）
- **最相关技能**：ct-tlf（中，出表技能）
- **结论**：不适合作 ct-tlf 监管 TLF 核心（缺 RTF / 期刊主题哲学 / opinionated 默认检验 / 加 R 依赖）；但暴露「把 ADaM 转成投稿论文表」的真实缺口。
- **落地改进**：
  - ct-tlf v0.4.0 模块 H「期刊发表表」（gtsummary 可选 R 引擎，与监管核心严格隔离；边界声明非监管 RTF、方法学诚实声明）
- **未照搬**：不并入监管核心（A 方案守红线，B 方案补缺口）

---

## 统计

- 已评估：3 篇（全部高置信，其中 2 篇已精读原文 PDF）
- 已落地改进：ct-base §5 + §6.9 两条红线；ct-tlf v0.4.0 模块 H + v0.5.0 源完整性闸门；ct-adam AI 生成 ADaM 草稿
- 误判撤回：1 次（AI201 延伸阅读标题误当论文内容，10-05 已撤回）
