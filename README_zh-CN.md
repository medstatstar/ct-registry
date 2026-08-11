# 临床试验注册检索专家（ct-registry）

[🇨🇳 中文](#) / [🇺🇸 English](./README.md)

<div align="center">
  <img src="assets/icon.svg" width="240" height="240" alt="ct-registry 图标"/>
</div>

> 跨源检索全球临床试验注册库（ClinicalTrials.gov、中国 CDE、WHO ICTRP、EU-CTR、ChiCTR、ISRCTN、DRKS、PubChem），归一化并聚合为一张可执行的格局图——用于立项查重、对照设计对标与竞品格局分析。B 档：普通数据输入 + 对外检索，可快速推广技能。

## 适用人群

`ct-*` 临床试验技能家族专用于解决临床试验全生命周期的各类需求，主要面向三类人群：

- **各制药企业的临床试验从业者** —— 申办方、CRO，以及医学 / 统计 / 注册等角色；
- **在医疗机构中设计、管理临床试验项目，或参与临床试验研究实务的医护人员**；
- **希望系统学习临床试验知识的医学专业学生**。

## 如何在对话中使用（How to Use）

直接用自然语言描述你的需求即可。助手会自动判断要查哪些注册库、各源用什么关键词（中英文自动互译）、用哪种检索模式——你无需自己选参数。以下为由简到繁的真实示例。

### 示例 1 · 快速注册库检索
**你说：**
> 查一下辉瑞 2022 年以来注册的三期肿瘤试验。

**助手回复（概要）：**
> 直连 ClinicalTrials.gov v2，归一化分期 / 状态 / 申办方，返回排序表（数量、范围、样例行），每条试验附可点击首页链接。

**如何触发真实计算：**
> 安全预览只打印计划；说"请直接计算" / "run it" 才执行真实检索。

### 示例 2 · 跨源（CT.gov + 中国 CDE）
**你说：**
> 找奥希替尼（osimertinib）在非小细胞肺癌的试验，全球和中国都要。

**助手回复（概要）：**
> 提议范围为 ClinicalTrials.gov v2 + 中国 CDE，关键词自动翻译为英文用于 CT.gov、中文（奥希替尼）用于 CDE，两源并发后合并为同一张格局图（如 CT.gov 20 + CDE 2057 → 2077 条），给出分期 / 状态 / 申办方分布。

**如何触发真实计算：**
> 安全预览打印关键词映射 + 范围；说"请直接计算"执行。CDE 走统一 Coze 端点（需 token）；CT.gov 免费直连。

### 示例 3 · 复杂 —— 多参数 CDE 路由菜单
**你说：**
> 在 CDE 查化学药物帕博利珠单抗、适应症非小细胞肺癌、状态进行中、申请人默沙东。

**助手回复（概要）：**
> 识别为 CDE 高级（结构化）检索。它不臆测，而是弹出路由菜单让你逐项确认后再拼装请求：

> ┌─ CDE 检索范围 ──────────────────────────┐
> │ 1) 关键词 / 药品名称 : 帕博利珠单抗      │
> │ 2) 适应症            : 非小细胞肺癌      │
> │ 3) 药品类型          : 化学药物          │
> │ 4) 申请人（申办方）   : 默沙东            │
> │ 5) 试验状态          : 进行中            │
> │ 6) 确认并执行                               │
> │ 7) 还拿不准 → 详细解释差异                 │
> └─────────────────────────────────────────┘

> 选 **7) 还拿不准 → 详细解释差异** 会展开每项字段的过滤含义、为何 `trial_status` 必须写精确枚举值（进行中，而非"正在进行"），以及 CDE 高级界面无期次过滤（分期由后续 detail 模式归一化后筛）。你修改任意项后再确认。

**如何触发真实计算：**
> 菜单本身是安全预览。确认（第 6 项）后说"请直接计算"，才把请求发往 CDE 统一端点。

### 示例 4 · 模糊需求 —— grill-me 逐分支追问
**你说：**
> 我还不确定要什么——刚听说竞品有个新药。

**助手回复（概要）：**
> 逐分支追问以理清需求，例如：
> - "你知道药名，还是只知道疾病领域 / 机制？"
> - "是对比全球，还是专门看中国（CDE）？"
> - "这是为了竞品格局、对照设计对标，还是自家试验前查重？"
> - "关心哪一期 / 什么状态 / 什么时间窗？"

> 理清后（如"GLP-1 类药、全球+中国、三期、近 3 年"）再提议范围与关键词，预览计划。

**如何触发真实计算：**
> 澄清全过程为安全预览；范围确认后说"请直接计算"执行。

### 示例 5 · 结构化详情 + 文档链接
**你说：**
> 把这批 NSCLC 的 CDE 命中记录的详情（申办方、分期、终点）拉出来，并列出可下载的 PDF。

**助手回复（概要）：**
> 跑 CDE `detail` 模式（每条 65 字段），从而填充申办方 / 分期（列表模式会显示 `Unknown`）。每条记录渲染首页链接，并**仅列出**（不自动下载）EU-CTR 的 PDF。PDF 需你显式确认后才下载。

**如何触发真实计算：**
> 详情抓取 ≤100 条自动执行；>100 条先确认列表。说"下载 PDF"才触发显式下载门。

### 示例 6 · 借 WHO ICTRP 做全球广覆盖
**你说：**
> 给我 DPP-4 抑制剂治疗 2 型糖尿病、2023 年以来的全球格局。

**助手回复（概要）：**
> 用 WHO ICTRP（一次调用镜像 14+ 个一级注册库：CT.gov、EU-CTR、ISRCTN、DRKS、ChiCTR、jRCT、ANZCTR、CTRI…）外加中国 CDE（始终独立检索，因为 WHO 英文标题匹配会漏掉中文注册试验），聚合为一张竞争格局图。

**如何触发真实计算：**
> 安全预览展示范围（WHO + CDE = 两个端点）；说"请直接计算"执行。按一次需求计入共享配额。

## 能力一览 —— 场景

| 能力 | 检索源 | 试试这样说 |
|---|---|---|
| 按疾病 / 干预 / 申办方检索 | CT.gov（直连）；CDE / ChiCTR（粘贴或工作流） | "查辉瑞 2022 年以来的三期肿瘤试验" |
| 跨注册库统一归一化 | 全部源 | "把 CT.gov 和 CDE 的 NSCLC 试验合并成一张表" |
| 聚合分析：分期 / 状态 / 申办方 / 时间线 / 竞品格局 | 全部源 | "给出奥希替尼在 NSCLC 的竞品格局" |
| 中国 CDE 高级检索与多关键词检索 | 中国 CDE（统一端点） | "CDE：沙坦 + 进行中，化学药物，2023 年起" |
| WHO ICTRP 全球镜像（14+ 注册库） | WHO ICTRP（统一端点） | "DPP-4 抑制剂 T2D 全球试验，2023 年起" |
| 药物 → 靶点 / 属性映射 | PubChem（直连） | "用 PubChem 把奥希替尼映射到靶点" |
| 结构化详情（申办方 / 分期 / 终点） | CDE detail（65 字段）、EU-CTR 文档 | "拉这些 CDE 登记号的完整详情" |
| 结构化输出：JSON / Markdown / PNG / Excel | — | "把格局导出成 Excel 工作簿" |
| 链式下游分析 | → `ct-pipeline` / `ct-protocol` | "把归一化结果喂给 ct-pipeline 做情报" |

## 常见问题（FAQ）

**只给部分参数能查吗？**
能。你从不需要自己选模式或旗标——助手根据你的话自动判定 CDE 调用模式（`search` / `combined` / `multi_keyword` / `detail`）。任何字段留空即可，未用字段直接省略（发送空字段反而会污染查询）。

**结果里的数量是每组还是总数？**
总数会聚合为一张格局图。跨源运行既报告总条数，**也**给出分源明细（如 CT.gov 20 + CDE 2057 → 2077 条）。状态分布里 `RECRUITING` 与 `已完成/进行中` 同表呈现。

**怎么真查出数？**
默认是**安全预览**（只有计划 / 载荷）。说"请直接计算" / "run it" 才执行真实检索。

**中文环境输出是中文吗？**
是。脚本自动检测语言环境：中文 `zh-*` 系统下所有面向用户的提示切中文，否则英文。原始数据值（CDE 中文状态 / 适应症等）一律保真不翻译。

**为什么有些行分期 / 申办方显示 `Unknown`？**
列表检索只返回概要字段。`sponsor` 与 `phase` 仅在 CDE `detail` 模式（65 字段）或 WHO detail 才有。需要申办方 / 分期明细时请抓详情。

**免费吗？有配额吗？**
当前免费。共享第三方端点按**需求（demand）**计次（一次用户请求 = 1 次需求；其内的 WHO+CDE、关键词微调、重复检索都合并为 1）。每日上限 100 个需求；直连 Tier-1 源（CT.gov v2、EU-CTR、PubChem）与预览不计入。

**结果能当监管申报用吗？**
不能。输出仅用于参考 / 规划。CSR / 申报文件须另按 GCP 单独生成。

## 开始检索前：耗时与数据量提示

借 WHO ICTRP 做全球检索（一次调用镜像 14+ 注册库）时，后台要实打实去爬这些库，**不是秒回**。给你一个直观的预期：

- **等多久**：一次真实检索，后台通常要 **1 到 5 分钟**才把数拿回来。技能会先给你一张"已提交、正在跑"的回执，然后自动轮询，跑完才返结果——这段时间你不用一直盯着，结果好了自然会回来。
- **为什么会贴着 5 分钟**：统一的第三方端点外侧有一道 **5 分钟硬墙**（网关上限）。像 `cancer` 这种宽词、或"全球 + 不限国家"的大检索面，处理时间可能贴着这道墙走，极少情况下会超时失败。真遇到了，技能会明明白白告诉你，而不是悄悄把数据丢了。
- **数据量怎么收着点**：WHO 全球检索的结果集可以非常大。如果一次查回来的数偏少、或者超时了，多半是**检索面太宽**——把关键词收窄些（比如用 `osimertinib` 而不是 `cancer`），或改用**高级检索**（在对话里说"高级检索"，由代码自动拼 `药物 AND 适应症` 这类更精准的过滤，返回量更小、也更快）。另外每天还有 **100 次需求**的配额上限（见上 FAQ），正常使用远碰不到。

## 安全（safe preview）

**默认安全预览。** 脚本只生成并展示计划 / 载荷。网络请求**仅在你显式确认时**才执行（"请直接计算" / "run it"）。在你确认前不发任何请求、不取任何数据。

**仅公开数据——零保密输入。** 技能读取公开注册库数据；你无需提供受试者 / 方案 / CRF 数据，也绝不会传输任何保密数据。

**出域披露（egress）。** 当你执行真实检索时，只有**公开查询词**（药品名、适应症、登记号）离开你的环境，发往以下公开端点：

- **ClinicalTrials.gov v2** —— 官方 REST API（直连，无需 token）。
- **PubChem** —— PUG-REST（药物→CID / 属性 / 靶点；直连，无需 token）。
- **中国 CDE** —— 经统一 Coze `/run` 端点 `ct-search.coze.site/run`（第三方，需 Bearer token——实测无 token 返回 401）。
- **EU-CTR** —— 纯 HTTP 解析旧 EudraCT 结果（直连，无需 token，无浏览器）。
- **WHO ICTRP** —— 统一 Coze `/run` 端点（第三方，需 Bearer token）；一次调用镜像 14+ 注册库。
- **ChiCTR / ISRCTN / DRKS** —— 经**同一**统一 Coze `/run` 端点，分别以 `source=chictr|isrctn|drks` 提供（第三方，共用 token）。

WHO ICTRP 与中国 CDE 在统一端点上**共用一枚长期有效 token**；该 token 是公开共用凭据，以 XOR+base64 混淆 blob **内嵌于 `config/keys.py`**（随包发布），开箱即用。解析优先级：`--token` CLI > 环境变量 `CT_REGISTRY_COZE_TOKEN`（遗留别名 `ICTRP_WORKFLOW_TOKEN`）> 内嵌 blob（ct-base §5.236）。任何保密数据都不会到达上述任一端点。

### Coze key（统一端点凭证）

统一 Coze 端点 `https://ct-search.coze.site/run`（CDE、WHO ICTRP、ChiCTR、ISRCTN、DRKS 共用）需要一枚 Bearer token。它是一枚**公开共用凭证**——由作者发布、绑定在端点上，并非你的个人私密。

- **开箱即用**：token 以混淆（XOR+base64）blob 的形式内嵌在 `config/keys.py` 中、随技能一同发布，因此检索无需任何配置即可运行。
- **如何覆盖**（例如作者重新签发 token）：在命令行传 `--token <JWT>`，或设置环境变量 `CT_REGISTRY_COZE_TOKEN`。请勿把 token 粘进对话。
- **是混淆、非加密**：编码只是为了不被随意查看，挡不住有意的提取。把它当凭证看待，但无需当成最高机密严防死守。
- **安全扫描器**：部分自动化扫描器会标记 `extsvc_client.py`（含 HTTP/Bearer 调用）。该 blob 是公开共用凭证，并非私钥——仓库内不含任何私密密钥。覆盖方式仅走 CLI/环境变量。

## 进阶参考（Advanced Reference）

> 以下命令面向开发者 / 进阶用户。日常对话中你**无需**手动输入——助手会在安全预览门之后替你构建并执行。

### 运行环境要求
- Python 3.10+（推荐 Anaconda）。
- 必需：`requests`、`pandas`、`beautifulsoup4`、`lxml`。
- 可选：`matplotlib`（PNG 图）；`playwright` + `playwright install chromium`（CDE 本地抓取，仅作最后兜底）。

### 一站式编排（CT.gov + PubChem + 聚合 + 报告）
```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-pubchem --out-dir ./out
```

### 跨源编排（CT.gov + CDE 并入同一格局）
```bash
# 英文主词：CT.gov 原样使用；CDE 关键词自动推导为中文
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-cde --out-dir ./out --run
# 中文主词：CT.gov 自动翻译为英文；CDE 原样使用（中文 0 条时静默降级到英文）
python scripts/ct_registry.py --cond "非小细胞肺癌" --status RECRUITING --with-cde --out-dir ./out --run
# 显式覆盖 CDE 关键词（中文 0 条时静默降级到英文）
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-cde --cde-keyword "高血压" --out-dir ./out --run
# CDE 高级筛选（药品 + 适应症 + 状态），并入
python scripts/ct_registry.py --cond "NSCLC" --with-cde --cde-mode combined --cde-keyword "678" --cde-trial-status "已完成" --run
# CDE 多关键词 AND，并入
python scripts/ct_registry.py --cond "NSCLC" --with-cde --cde-multi-keywords "高血压 糖尿病" --run
```

### 全量格局（Tier-1 + Tier-2 外部服务）
```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING \
    --with-euctr --with-cde --with-chictr --with-isrctn --with-drks --with-ictrp \
    --out-dir ./out --run
```

### 各源直连脚本
```bash
# CT.gov（必做，官方 API）
python scripts/search_ctgov.py --cond "non-small cell lung cancer" --status RECRUITING --max 50 --out ctgov.json
# EU-CTR（纯 HTTP 解析，无需 token）
python scripts/search_eu_ctr.py --q "cancer" --run --out euctr.json
# PubChem 药物 → 靶点
python scripts/enrich_pubchem.py --drug "osimertinib" --targets --out pubchem.json
```

### 统一端点（WHO ICTRP + 中国 CDE + ChiCTR / ISRCTN / DRKS）
```bash
# 推荐：统一 Coze /run 端点（WHO 与 CDE 共用一枚内嵌于 config/keys.py 的 token）
python scripts/search_ictrp.py --source who --q "osimertinib" --run --out ictrp.json
python scripts/search_ictrp.py --source chinadrugtrials --q "高血压" --run --out cde_list.json
python scripts/search_ictrp.py --source chinadrugtrials --q "678" --drugs-name "帕博利珠单抗" --trial-status "进行中" --run --out cde_list.json
python scripts/search_ictrp.py --source chinadrugtrials --q "高血压 糖尿病" --run --out cde_list.json
python scripts/search_ictrp.py --source chictr --q "肺癌" --run --out chictr.json
python scripts/search_ictrp.py --source isrctn --q "cancer" --run --out isrctn.json
python scripts/search_ictrp.py --source drks --q "diabetes" --run --out drks.json
# 旧版独立 CDE 端点（已归档至本地 CDE/ 目录，不随包发布；仅作兜底参考）
python CDE/search_cde_workflow.py --keyword "奥希替尼" --run --out cde_list.json
# token 已内嵌于 config/keys.py（随包发布），无需手动操作。
# 如需覆盖（如极罕见 403），设环境变量 CT_REGISTRY_COZE_TOKEN 或传 --token。
```

### CDE 四种调用模式（自动判定；旗标仅供参照）
```bash
# 模式 search（默认关键词 或 高级筛选）
python CDE/search_cde_workflow.py --drugs-name "帕博利珠单抗" --indication "非小细胞肺癌" --drugs-type "化学药物" --appliers "默沙东" --trial-status "进行中" --run
# 模式 combined（关键词 + 高级筛选）
python CDE/search_cde_workflow.py --mode combined --keyword "678" --trial-status "已完成" --run
# 模式 multi_keyword（空格分隔 AND）
python CDE/search_cde_workflow.py --mode multi_keyword --multi-keywords "高血压 糖尿病" --run
# 模式 detail（项目列表 → 并行 65 字段抓取；≤100 自动，>100 先确认）
python CDE/search_cde_workflow.py --project-list cde_list.json --run --out cde_detail.json
# 仅预览（默认，不发网络）
python CDE/search_cde_workflow.py --keyword "奥希替尼"
```

### 归一化 → 聚合 → 报告 → Excel
```bash
python scripts/normalize.py --ctgov ctgov.json --cde cde.json --chictr chictr.json \
    --euctr euctr.json --isrctn isrctn.json --drks drks.json --out normalized.json
python scripts/aggregate.py --in normalized.json --out agg.json
python scripts/report.py --in agg.json --out report.md --png report.png
# 临床友好四表 Excel（编排器自动生成；--no-excel 关闭）
python scripts/export_xlsx.py --in normalized.json --out report.xlsx --title "Asciminib 2023-2026"
```

### 结构化详情 + 确认门 PDF 下载
```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING \
    --with-cde --with-euctr --with-detail --out-dir ./out --run
# 真正下载列出的 EU-CTR PDF（显式确认门）
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING \
    --with-cde --with-euctr --with-detail --download-docs --out-dir ./out --run
python scripts/download_docs.py --in ./out/normalized.json --out-dir ./out/docs --yes
```

### WHO ICTRP 高级字段（节选 → CLI）
`--who-title`（+ 运算符）、`--who-condition`、`--who-intervention`（别名 `--intr`）、`--who-recruitment-status`（别名 `--status`）、`--who-sponsor`、`--who-country`、`--who-phase`（逗号分隔）、`--who-date-start` / `--who-date-end`（DD/MM/YYYY）、`--who-with-results`、`--who-secondary-id`。任一结构化字段会自动选 `mode=combined`。

### CDE 高级字段（节选 → CLI）
`--reg-no`、`--indication`、`--case-no`、`--drugs-name`、`--drugs-type`（枚举：中药/天然药物/化学药物/生物制品）、`--appliers`、`--communities`、`--researchers`、`--agencies`、`--trial-status`（11 值枚举：进行中/尚未招募/招募中/招募完成/已完成/主动暂停/主动终止/IEC·IRB暂停/IEC·IRB终止/责令暂停/责令终止）。注意：CDE 高级界面**无期次过滤**——分期由 detail 后筛。

### 人机交互契约（两道门）
- **Gate 1 —— 检索前简报（在 `--run` 之前）：** 助手打印各源关键词（中英对照）、范围、时间/状态筛选、`demand_id` 分组与配额影响，以及"免费、每日 100 个需求"提示。仅在确有选择时才追问。
- **Gate 2 —— 检索后列表确认：** 展示列表（总数、范围、样例行、`Unknown` 分期/申办方提示）。详情抓取：≤100 条自动执行；>100 条先确认。PDF 绝不自动下载。

### 错误处理（速查）
| 错误 | 原因 | 处理 |
|---|---|---|
| CT.gov `URLError` | 无网络 / 代理 | 确认 clinicaltrials.gov 可达；配置代理 |
| CDE 空白 / "access blocked" | 安全狗 WAF 拦截浏览器 | 用统一端点工作流（推荐）；或协助粘贴 → `parse_cde.py`（不出域） |
| WHO / CDE HTTP 401 | 缺 `Authorization: Bearer <token>` | token 内嵌于 `config/keys.py`（随包）；若仍 401，设 `CT_REGISTRY_COZE_TOKEN` 或传 `--token` |
| WHO / CDE HTTP 403（罕见） | token 损坏 / 吊销 | 经环境变量 `CT_REGISTRY_COZE_TOKEN` / `--token` 重发（长期有效，403 非过期） |
| CDE HTTP 500 `字段类型错误` | 字段写成 `{"value":x}` 或 `project_list` 写成数组 | 用纯字符串；`project_list` 须为 JSON **字符串** |
| ISRCTN 404 | 公开 API 失效（2026-07-20） | 用统一端点 `source=isrctn` |
| CDE 读取超时 | 大结果集 / 网关抖动（单次上限约 300 秒） | 用默认 300 秒重试；属瞬时，非载荷错误 |

### 链式调用
`ct-registry` → `ct-pipeline`（消费 `normalized.json` 做竞品情报）/ `ct-protocol`（设计对标）。

---

**版本**：v0.3.78 | **License**：MIT | **Authors**：medstatstar, phoe-zip

如有功能建议、Bug 反馈或其他意见，请直接联系作者：medstatstar@gmail.com（张文彤 / Wintone Zhang）。

## 保密声明

> CT 全系列技能由 16 余个专用行业技能构成，按「保密信息出域风险 + 是否对外检索」分为 A、B、C、D 四级，完整覆盖新药临床试验（Clinical Trial）全流程的各方面需求。
>
> - **A 级 / B 级（不涉密）**：完全本地运行、仅使用普通数据；B 级虽需对外公开检索，但不涉及任何保密信息。这两级技能均会在 GitHub 公开发布。
> - **C 级 / D 级（涉密）**：涉及药企需严格保密的临床试验数据、内部资讯等敏感内容（如 ct-analysis、ct-sdtm 等）；C 级在本地处理、数据不出域，D 级还需政策审批。这两级技能仅限企业内部使用，目前不对外公开发布。
>
> 若您对这些涉密技能确有实际需求，欢迎与作者联系，定制并安装相关技能。
>
> 📧 联系方式：medstatstar@gmail.com，张文彤（Wintone Zhang）
