# Changelog

## v0.13.0 (2026-10-08) · pytrials + Docling 外部开源资产引用

> 基于《临床试验Skill推荐》分析，新增 pytrials 和 Docling 两个外部开源工具集成。

- **新增 External Open-Source Integrations 表格**：列出 pytrials（CT.gov 批量检索客户端）和 Docling（法规文档结构化解析）两个工具
- **pytrials 增强模式 (opt-in)**：使用 pytrials 作为官方 API 客户端批量拉取 CT.gov 字段，新增适应症分布热力图、终点设计对比、中心历史项目检索
- **增量兼容**：新增内容为可选引用，不影响现有 9 源检索体系和回归测试

## v0.12.1 (2026-10-07) · 接入 `entry_point` 调用来源标记（ct-base coze_io_contract §1.3 / §2.3）

> 飞书searchlog 新增 `entry_point` 独立列，用于按**调用来源**（技能本身 / 工作台 Web 应用 / 未来第三方 API）直切筛选。本技能此前未发送该字段，现**客户端 + coze 侧**一并补齐。

**客户端（本地出站信封）**

- **`adapters/search_ictrp.py`**：新增模块级 `_ENTRY_POINT = "skill"` + `set_entry_point(v)` + `entry_point()`（枚举白名单 `skill`/`workbench`/`api`，空值/空白/非法值一律回退 `"skill"`，绝不写 `None` 或脏值）；`_attach_coze_contract()` 在顶层信封注入 `"entry_point"`（与 `query_origin` / `skill_version` 同级，`setdefault` 保证显式传参优先 + 幂等）。
- **与 `query_origin` 正交（🔴 不得混用）**：`query_origin` 按机器（硬件 ID / 主机名 SHA-256），同一台机器上 skill 与 workbench 算出的哈希逐字节相同 → 无法区分界面来源；`entry_point` 按入口/界面，故须独立字段。
- **未并入 `querystr` / `resultstr`**（§2.3 硬约束）：`entry_point` 只作顶层信封，由coze 端分流到飞书独立列。

**coze 侧（`adapters/coze/`，服务端私有 §16.7 · 本地已改，待发布）**

- **`src/graphs/state.py`**：三个承载模型**均显式声明** `entry_point: Optional[str]` —— `GraphInput`（入口投影）/ `GlobalState`（图内传递）/ `FeishuWriteInput`（节点入参）。**漏声明会被 `extra="ignore"` 静默丢弃**，与已踩过的 `skill_version` / `total_count` 同一根因，故三处一个都不能省。
- **`src/graphs/nodes/feishu_write_node.py`**：record 字面量新增 `"entry_point": getattr(state, "entry_point", None) or "skill"`；模块 docstring 补§2.3 落点说明。
- **`src/graphs/nodes/publisher_pdf_batch_node.py`**：该节点自建 record（ct-literature PDF 批次表），同样补 `"entry_point"` 键，保持同表列名一致。
- **三镜像同表**：ct-registry / ct-samplesize / meta-analysis 共用同一飞书表（`DEFAULT_APP_TOKEN=Pog0bGNMbaCWMIsGRNpckHcnn9f` / `DEFAULT_TABLE_ID=tblQ8OQ0rXsXQWkh`，靠 `skillname` 列区分技能），故列名必须**精确统一为小写 `entry_point`**，否则 `batch_create` 报未知字段名。已核对三镜像列名一致。

**验证**

- 新增 `tests/test_coze_entry_point.py`（C1–C6，6/6 RC=0）：三模型声明齐全 / 两个 record 均含该键 / 列名精确小写 / 回退语义（脏值与空值均回退 skill，绝不写 None 或空串）/ 不并入 resultstr·querystr / **pydantic 2.13.5 模型层实测**（老客户端不带字段得 None→回退 skill，新客户端值投影保留）。
- 全链路贯通实测：客户端 payload → `GraphInput` → `FeishuWriteInput` → record 取值，`workbench` 全程保留；老客户端回退 `skill`。
- 跨技能客户端契约回归 `ct-base/scripts/tests/test_entry_point.py`（E1–E9，9/9）；`py_compile` 三个改动文件均通过。
- 既有 `tests/regression_harness.py` PASS=28 FAIL=2 —— **两个失败为既存问题**（case09/case10 引用的 `scripts/search_ictrp.py` 路径早已不存在，文件在 `adapters/`）。已用 `git stash` 对照证明：改动前后同为 PASS=28 FAIL=2，与本次无关。

> ⚠️ **部署铁律（§2.3）**：飞书列已存在（2026-10-07 表头可见），故部署新 coze 代码是安全方向 ——「新coze + 有列」正常落值，不命中 `batch_create` 未知字段名报错窗口。
> ⚠️ coze 侧 `adapters/coze/` 已被 `.gitignore` 忽略（服务端私有），**发布需手动同步到 Coze 控制台**，不在 git 发布链路内。

## v0.12.0 (2026-10-06) · 工作台安全加固：静态文件白名单（P0）+ 路径黑名单（P3）

> 已发布工作台应用（`ct-registry.app.workbuddy.host`）安全加固，阻止源码/凭据/敏感数据被 HTTP 下载。

- **`workbench/server.py` + `workbench/publish-dist/workbench/server.py`**：
  - P0: 新增 `_STATIC_ALLOWED` 扩展名白名单（12 种），非白名单扩展名返回 403。
  - P3: 新增 `_STATIC_PATH_BLOCKED` 路径黑名单（`adapters`, `runs`, `scripts`, `out`, `references`），阻止目录级访问，返回 403 `forbidden path`。
- **影响**：Coze 服务端源码镜像目录结构无法通过 HTTP 探测；`references/*.json` 映射文件无法访问（已由 P1 文件名保护，P3 再加一刀）。`/api/*` 端点（`/api/search`, `/api/runs` 等）不受影响——走独立路由，不经过 `_static()`。
- **回归**：`curl http://127.0.0.1:8790/../adapters/coze/src/main.py` → 403；`curl http://127.0.0.1:8790/../references/term_map.json` → 403。

> 已发布工作台应用（`ct-registry.app.workbuddy.host`）安全加固，阻止源码/凭据被 HTTP 下载。

- **`workbench/server.py`**：`_static()` 新增 `_STATIC_ALLOWED` 扩展名白名单（12 种：css/js/svg/png/ico/json/woff/woff2/ttf/map/html/htm），非白名单扩展名返回 403 `forbidden type`。
- **`workbench/publish-dist/workbench/server.py`**：同步上述白名单修复（发布副本）。
- **影响**：`.py` / `.env` / `.pyw` 等源码/凭据文件无法通过 HTTP 下载；前端静态资源（css/js/ico/json 等）不受影响。
- **回归**：`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/../scripts/ct_registry.py` → 403。

## v0.10.0 (2026-09-18) · resultstr 检索侧审计摘要（status/ok/total/s3）+ 遗留字段补声明

> ⚠️ **归版说明（2026-09-29 周检补）**：SKILL.md 当前版本为 `0.10.0`，但本文件此前首部恒为
> `Unreleased`、全篇无 `0.10.0` 条目（ct-base §16.8 / spec_lint F13 ERROR）。现按「首条版本须与
> SKILL.md 一致」将本条归为 `v0.10.0`。**下方自 2026-09-17 起至 `v0.9.3 (2026-09-06)` 之前的
> 全部 `Unreleased` 条目同属 0.10.0 变更集**，建议发布前由人工一次性合并为单条 `v0.10.0` 记录。

- **背景（用户指令）**：飞书 `resultstr` 目前仅记 `runtime_sec` + 版本字段，信息不足以审计
  「分析是否 OK / 检索到多少条 / 是否走 S3」。参考 `publisher_pdf_batch` 已有的
  `status/ok/total/s3/runtime_sec` 摘要形态，registry 检索路径的 `resultstr` 也应携带同样结构，
  使同一飞书表、同一 `resultstr` 列的 record 形状一致、可按端点版本归因。
- **改动（均在 `adapters/coze/src/`，服务端，需重新打包上传 coze 才生效）**：
  1. `nodes/feishu_write_node.py` —— `resultstr` 检索侧新增 `status` / `ok` / `total` / `s3`
     （对齐 `publisher_pdf_*` 审计 schema，ct-base §2.2）；`hit_count` 重命名为 `total`、
     `returned` 并入 `ok`（project_list.projects 长度；不可用→信任 total_count）。
     `log_only` 模式仍只写 `runtime_sec` + 版本字段，不写检索统计（不谎报 0 命中）。
  2. `graphs/state.py` —— `FeishuWriteInput` **补声明** `total_count` / `project_list` /
     `error_msg` / `log` / `s3_stored`（该模型 `extra="ignore"`；未声明字段被 langgraph 投影
     丢弃、节点恒拿不到，与 §2.1 已修的 `skill_version` 同一根因）。**顺带修复 CHANGELOG
     2026-09-17 记录的遗留 bug**：此前 `hit_count`/`returned`/`error`/`log` 大概率恒不落库。
  3. `nodes/_version.py` —— `COZE_VERSION` `0.3.89` → `0.3.90`（resultstr schema 变更，需端点版本可归因）。
  4. `scripts/selfcheck_log_only.py` —— 断言从 `hit_count` 改为 `total`/`ok`/`status`（L16/L16b/L17），
     log_only 断言扩为「不含 total/ok/status/s3」。
- **文档**：`adapters/coze/AGENTS.md` 飞书审计小节 `resultstr` 行更新为检索侧摘要 schema。
- **验证**：`py_compile` 通过；`scripts/selfcheck_log_only.py` 全绿（L11-L17）。
- ⚠️ **契约变更**：`resultstr` 弃用 `hit_count`/`returned`，改用 `total`/`ok`（与 pdf 路径对齐）。
  旧审计看板若按 `hit_count` 解析需同步；端点版本 `0.3.90` 可作切换分界。

## Unreleased (2026-09-17) · 飞书版本字段落点统一（ct-base coze_io_contract §2.1）

- **背景（用户指令）**：版本字段写入位置不固定——registry 端点 `publisher_pdf_batch` 把
  `skill_version` 写进 `querystr`，而 meta/samplesize 又各自不同 → 飞书表里同一信息位置不一致。
  ct-base `references/coze_io_contract.md` §2.1 现规定：**版本字段一律写 `resultstr`，
  `querystr` 不再存任何版本信息**。
- **改动（均在 `adapters/coze/src/`，服务端，需重新打包上传 coze 才生效）**：
  1. 新增 `graphs/nodes/_version.py::COZE_VERSION = "0.3.89"` —— 端点版本常量单一真源。
     此前本端点**没有**版本常量，只以 `dist/coze_deploy_bundle_<ts>.zip` 时间戳区分，
     审计表无法按端点版本归因；取值沿 CHANGELOG 末条 `v0.3.88` 顺延。
  2. `nodes/feishu_write_node.py` —— `resultstr` 顶层新增 `skill_version` + `coze_version`
     （均非空才写）；新增 `_strip_version_fields()`：客户端透传的 `querystr` 若含
     `skill_version` / `coze_version` 一律剔除，保证落点唯一。
  3. `nodes/publisher_pdf_batch_node.py` —— `_build_querystr()` **移除 `skill_version` 入参**；
     `_build_resultstr()` 新增 `skill_version` / `coze_version`，元信息全空时与历史格式
     逐字节一致。
  4. `graphs/state.py` —— `FeishuWriteInput` **补声明 `skill_version`**（该模型 `extra="ignore"`，
     未声明字段会被 langgraph 过滤、节点恒拿不到，与 CHANGELOG 已记录的 `log` 同坑）；
     5 处 `skill_version` 描述改指 resultstr。
- **文档**：`adapters/coze/AGENTS.md` 新增「飞书审计：版本字段落点」小节（querystr 禁写 /
  resultstr 三键 / 升级纪律只改 `_version.py`）。
- **验证**：`py_compile` 4 文件通过；冒烟确认 `_strip_version_fields` 剔除版本键、
  `_build_querystr` 键集无版本键、`_build_resultstr` 空元信息与历史格式逐字节一致。
- ⚠️ **遗留（未修，超出本次范围）**：`FeishuWriteInput` 同样未声明 `total_count` /
  `project_list` / `error_msg` / `log` → `hit_count` / `returned` / `error` / `log`
  大概率同样恒不落库（与 CHANGELOG 2026-09-08 记录的 `log` 同一根因）。需另行补声明后打包。

## Unreleased (2026-09-08 20:08) · Coze 源码打包（feishu 审计 resultstr 重构）

- 相对上一包 `coze_deploy_bundle_20260908_101717.zip` 仅 1 文件变更：`src/graphs/nodes/feishu_write_node.py` —— 审计 `resultstr` 与入参列 `querystr` 彻底解耦（去掉 `mode`），`hit_count` 恒写（0 命中亦有审计价值），新增 `returned`（实际返回条数，仅在截断/外置与命中数不同时出现）与 `log`（节点日志摘要，截断 120）。
- `py_compile` 全量通过（src + scripts）。
- **新部署包**：`dist/coze_deploy_bundle_20260908_200835.zip`（56 files / 192,115 B / MD5 `2d17d3201270d07c9df8c04a1ba0f964` / ZIP_OK，回读逐文件 MD5 与磁盘一致）；同步覆盖根目录 `coze_deploy_bundle.zip`。**待用户上传 Coze 控制台**；本地未发布。
- ⚠️ 已知待办：`GlobalState`（`src/graphs/state.py`，pydantic `extra="ignore"`）**未声明 `log` 字段**，且无节点写入 → 新加的 `log` 审计键当前恒不落库（`getattr` 兜底不报错，非阻断）。需补 `log: Optional[str]` 并指定产出节点后再打一次包。

## Unreleased (2026-09-08 12:10) · SKILL.md description 重写：对齐 summary 写法

- description 从 964 → **703 字节**（较原始 1985 降 65%），对齐 summary 风格：中文源列表 + 英文源列表 + 用途，去掉 B 档/零保密/Coze 等内部细节。
- 本地未发布。

## Unreleased (2026-09-08 12:02) · SKILL.md description 瘦身 + 正文去中文

- `description` 从 1985 → 964 字节（-51%），保留双语但去掉逐源 WAF/token 细节（正文 Data Sources 表已覆盖）。
- Features 段（P0-A/B/C/D）中文说明全部英文化。保留的中文均为合理用例：实际用户输入（`光生物调节`/`反馈问题`）、中文服务字面报错（`字段类型错误`）、CDE 参数值示例（`列汀`）。
- 本地未发布。

## Unreleased (2026-09-08 10:44) · README 示例 1 重写：单源限定 vs 默认全球

- 示例 1（zh + en）重定位：从「快速注册库检索（默认 CT.gov）」改为「单源限定检索（用户明确说『只要 CT.gov』）」，与示例 2「默认全球检索」形成清晰对比 —— 不指定范围 → 默认全球；明确说单源 → 走单源直连。
- 残留话术扫描 CLEAN。本地未发布。

## Unreleased (2026-09-08 10:39) · README 示例 2 重写：从"跨源"到"默认全球检索"

- 示例 2（zh + en）重定位：从「跨源（CT.gov + CDE）· 用户显式要求全球和中国都要」改为「默认全球检索（WHO ICTRP 14+ 注册库 + CDE）· 无需额外指定范围」，与 `--source` 默认值 `who` 一致。
- 残留话术扫描 CLEAN。本地未发布。

## Unreleased (2026-09-08 10:33) · README 案例区评估与同步（双语）

- 对照 WHO HTTP 快路径改造评估 README：示例区（Example 1–6）语义未变无需重写；「数据源与状态」表已含最新状态。**4 处过时/缺失需更新，已双语落地**：
  1. 耗时提示段首 + 「等多久」bullet：WHO「不是秒回 / 通常 1–5 分钟」→ **按检索面宽窄分层**：≤100 条窄词 HTTP 直连数秒即回（不开浏览器）；大结果集才 1–5 分钟浏览器翻页。
  2. 吞吐表：窄词行改「HTTP 直连秒回 2–15s、≤10 页自动翻完」；中词/宽词行补充「>100 条后浏览器接管 / HTTP 探测首页 ~2–6s」。
  3. 错误速查表 ISRCTN 行：陈旧「公开 API 失效（2026-07-20）」→ 重写为官方 XML API（`/api/query/format/default`）+ 异常时自动 WHO 兜底。
  4. 「返回偏少」段：补「>100 条取回 10 页 ~80–100 条并标 is_partial 属设计内能力边界（非故障）」。
- 残留话术扫描 CLEAN（`不是秒回 / is not instant / 100-150 页 / 公开 API 失效` 均无）。本地未发布。

## Unreleased (2026-09-08 10:17) · HTTP 翻页 max_pages 上限返回修复（承 10:00 实测发现）

- 实测翻页时发现的逻辑缺陷修复：`_try_http_fast_path` 收尾原为「is_partial → 一律 None 降级 Playwright」。当调用方显式 `--max-pages 3`（只想要 3 页）且 total>30 时，HTTP 翻满 3 页 30 条后因 is_partial 被**丢弃并降级 Playwright 重新翻**（双倍浪费）。
  - 修正：**未取全但已到达调用方页数上限（`page_seq >= max_pages`）→ 直接返回 partial 结果**；仅「未取全且未达调用方上限」（撞 HTTP 10 页能力边界 / 中途停）才降级 Playwright。
  - py_compile OK。
- **部署侧翻页累计实测**（走 Coze 端点，云端 IP 不受本机 WHO 限流影响）：`thymoma` → 95 条/148（95/95 去重、跨页覆盖多注册库年代）；`penile cancer` → 80 条/120、2m12s。多页翻页真实工作；本机 IP 直连限流时「无新增→降级」防护亦被验证。
- **新部署包**：`coze_deploy_bundle_20260908_101717.zip`（56 files / 191,789 B / MD5 `dce93213c1b78e99677d1abedc949e52` / ZIP_OK）。**待部署**；本地未发布。

## Unreleased (2026-09-08 09:40) · WHO HTTP 通道升级：翻页真相 + 多页抓取

- **用户质疑「HTTP 翻页不可能？不应该」** → 深入排查推翻此前的「无法翻页」结论：
  - **真因 ①**：回发 payload 误带 `txtTitle/txtCondition/ddlPageSize` 等结果页**不渲染**的搜索控件字段 → ICTRP 服务端异常返回 2679B 软错误页。去掉即通（隔离测试：结果页 VS 三件套空回发成功 80527B；+空 txt 字段即 2679B）。
  - **真因 ②**：顶部 `dlPager` 的页码链接回发**静默返回重复页**（服务端忽略）；必须用**底部 `dlPager2`** 的 target（`ctl00$ContentPlaceHolder1$dlPager2_ctlNN$lnkPageNo`）。
  - **真因 ③**：高频连续回发触发服务端风控——翻页被**静默降级为首页缓存**（页无新增，非 2679B）。代码以「页无新增」为信号停止。
  - 干净窗口实测：cancer 连翻 P2–P6 全通、无重叠、~4–7s/页（22s 取 60 条）；diabetes 用 dlPager2 翻 P2 0 重叠。
  - 硬边界：结果页 pager 每屏仅渲染 10 个页码（1..10），第 11 页起无链接（GridViewSearch doPostBack 为 Playwright JS 专属）；`ddlPageSize=100` 搜索亦 2679B。→ **HTTP 封顶 10 页 × 10 条 = 100 条**。
- **`_try_http_fast_path` 升级为多页全量抓取**：
  - 新增 `_http_pager2_target()`（解析底部 dlPager2 目标页 target）与 `_http_page_hidden_fields()`（结果页 hidden 全集）。
  - 流程：搜索 → 0 条 / 首屏即全量 / max_pages≤1 → 直接返回；2..10 页 → 循环翻页（payload = 当前页 hidden + dlPager2 target，**严禁 txt*/ddlPageSize**；每页 2.0–3.5s 节流防风控——2026-09-08 09:37 用户要求上调，原 0.8–1.6s 在连续翻页时仍可能被限流）；翻页遇 2679B / 无新增 / 超预算 / total>10 页 → **返回 None 整体降级 Playwright**（保证取数质量不降）。
  - 验证（AST 复刻真实代码 + 真实站点，4/4）：osimertinib 2.9s 命中 2 条；无匹配词 2.0s 返 0；cancer 4.8s 探测后降级（日志证实「翻页无新增→限流判定→降级」防护路径生效）；复杂字段 0 开销降级。
- **`_wait_for_page_ready` + goto 等待修复（承 09:20 条目）** 保留：Playwright 路径作为 >100 条 / 复杂字段的兜底。
- **新部署包**：`coze_deploy_bundle_20260908_093749.zip`（56 files / 191,504 B / MD5 `19c0af9f97c3e941021a52e8ec5fa52c` / ZIP_OK）。**待部署**；本地未发布。翻页节流已按用户要求（09:37）从 0.8–1.6s 上调至 **2.0–3.5s**——0.8–1.6s 在连续翻页时仍可能被风控静默降级。

## Unreleased (2026-09-08 09:20) · WHO 节点改造：HTTP 首屏快路径 + 修复 fill 超时（方案 C）

- **诉求（彤）**：WHO 检索门户手工正常但节点超时，要求核查是否有官方 API 可用。核查结论：**无公开免费 API**（ICTRP Web Service 需付费申请；遗留 `.asmx` 端点已停用——返回 **HTTP 200 + 2679B** ICTRP 软错误页，勿按状态码判活，真 404 仅 103B）。但实测高级检索页支持**纯 HTTP POST 首屏检索**（1–15s，不触发 cookie/JS 挑战）。选型 **C = HTTP 快速探测 + Playwright 翻页兜底**。
- **`nodes/who_search_node.py` —— 新增 HTTP 首屏快路径**：
  - `_http_adv_first_page()`：`GET /AdvSearch.aspx` 取 VIEWSTATE 三件套 → `POST` 回传 + `txtCondition/txtTitle/txtIntervention/txtPrimarySponsor` + `btnSearch=Search`，内容判活（软错误页/无结果表 → 报错）。复用 `_parse_results_from_grid` / `_get_summary_and_pages` 解析，返回结构与原 Playwright 成功分支同构。
  - `_http_channel_suitable()`：仅 keyword / 简单文本字段、运算符 AND、无复杂筛选（国家/日期/阶段/招募状态/勾选）才走 HTTP，语义不可对齐一律降级 Playwright。
  - `_try_http_fast_path()`：接入 `_do_who_advanced_search` 入口（浏览器创建前）。**0 条 / ≤10 条（首屏即全量）→ 直接返回，不开浏览器**；大结果集 / 复杂字段 / HTTP 失败 → 返回 None 走原浏览器流程。
  - 实测（本地复刻真实函数 + 真实站点）：`osimertinib` **2.1s** 命中 2 条（原 Playwright 30s+ 超时）；`cancer` 3.3s 探测后正确降级（33366 条需翻页）；无匹配词 1.9s 直返 0 条；`who_country` 复杂字段直接降级零网络开销。4/4 断言通过。
- **`nodes/who_search_node.py` —— 修复 `Page.fill` 30s 超时根因**：
  - `_wait_for_page_ready()`：弃用 `networkidle`（Playwright 官方不推荐、对 GA/轮询页必超时且异常被吞）→ `domcontentloaded` + 显式等 `#ImgLoading` 遮罩隐藏 + 800ms 抖动。
  - 三处 `page.goto(..., wait_until="commit")` → `"domcontentloaded"`（等 DOM 就绪而非只等响应开始）。
  - 旧代码用 `"txtCondition" in content`（HTML 字符串）判定页面就绪是**误判**——元素在 HTML ≠ 可交互，这正是 fill 超时的直接原因。
- **已知边界**：ICTRP 服务端对所有回发（翻页 `dlPager` / 改每页条数 `ddlPageSize` 10–100 / 导出 XML）一律返回 2679B 软错误页（已排除缺 hidden 字段、缺 select、异步回发头等原因）→ HTTP 通道只做首屏 ≤10 条；翻页仍由 Playwright 承担。
- **新部署包**：`coze_deploy_bundle_20260908_091827.zip`（56 files / 189,389 B / MD5 `be25ba9dd67d19db89950d5bb89ff2cc` / ZIP_OK）。**待部署**；本地未发布。

## Unreleased (2026-09-08 08:45) · 合并检索源兜底拓宽 + README「数据源与状态」表

- **诉求（彤）**：① 对于有合并检索源的站点，原站点不通时应当使用合并检索源做备用方式；② 对于确实站点异常的情况，技能应该可以返回相应的提示信息；③ 多源检索的技能应在 README 中清晰列出各种源的情况（范式 = ct-literature）。同步沉淀为 ct-base §13.14 / §14.2 / §14.3。
- **本地 `search_ictrp.py` —— 兜底触发条件拓宽（关键修复）**：
  - **修复前缺陷**：WHO 兜底仅认 `empty_no_error`（0 条 + 无错误）。DRKS 站点迁移属**显式 error**（`error_msg` 非空），故 `empty_no_error=False` → **兜底永不触发**，只能拿到 0 条 + 迁移提示，拿不到 DRKS 数据。
  - **修复后**：WHO-COVERED 源（chictr/isrctn/drks/euctr）返回 0 条时——① 节点**显式报错**（迁移 / WAF 拦截 / 抓取失败 / API 异常）→ **直接判定原站点不通、跳过对照探针**（省一次调用）→ 立即切 WHO 线路；② 0 条 + 无错误 → 仍走**对照词探针**区分「真实零结果」与「节点故障」（探针有数据 = 真实零结果，不浪费 WHO 配额）。
  - `CONTROL_TERMS` 新增 `euctr`（WHO 亦镜像 EUCTR 记录，使探针对该源同样生效）。
- **兜底结果溯源标注**：兜底成功 → 回填 `records`/`total`，清 `error_msg` 与 `source_likely_down`（数据可用），并置 `fallback_used=who_ictrp` / `fallback_reason=<src>_down` / `<src>_records_via_who` / `note`（保留原诊断 + 说明来自 WHO 合并源）。
- **兜底失败（WHO 亦报错 / WHO 无该源记录）→ 保留明确 `error_msg`** 并追加 `[WHO 回退亦失败: …]`，`source_likely_down=True`——**绝不把「源不可用」伪装成「无结果」**。
- **README（中英双语同步）**：新增「## 数据源与状态」——一张主表（源 / 访问方式 / 角色覆盖 / **当前状态含实测日期** / 兜底策略）+「各来源如何配合」（CDE 始终独立检索、WHO 为合并兜底源、CTIS 非 WHO 一级镜像故无兜底）+「站点异常会返回什么」（DRKS 迁移 / ChiCTR 故障 / ISRCTN 拦截 / 真实零结果 vs 源故障的探针区分）。
- **验证**：
  - `py_compile` OK。
  - **离线补丁测试 4/4 分支符合规范**：① 显式迁移报错 + WHO 兜底成功 → 2 条回填、`fallback_used=who_ictrp`、`error_msg=None`、`note` 保留迁移诊断、**探针调用 0 次**（修复前此场景完全不触发）；② 0 条 + 探针判定故障 → 兜底成功；③ 真实零结果（探针有数据）→ **不兜底、不报故障**；④ 显式报错 + WHO 亦失败 → 保留 `error_msg` + `[WHO 回退亦失败: …]`。
  - **真实 DRKS 端到端实测**：迁移报错 → `[SOURCE-DOWN] DRKS 节点显式报错，判定原站点不通` → `[FALLBACK-WHO] 切 WHO ICTRP 线路查 drks 来源`；本次 WHO 节点自身 Playwright `Page.fill` 超时（站点/节点侧波动，约 1h 前 WHO 尚正常），故落到「保留明确提示」分支并正确追加 `[WHO 回退亦失败: …]`。
- ⚠️ **本次改动全在本地编排层，无需重新打包部署 Coze**（ISRCTN XML API 包 `coze_deploy_bundle_20260908_083106.zip` 仍需单独部署）。**本地未发布**。

## Unreleased (2026-09-08 07:40) · DRKS/ISRCTN 站点异常诊断 + EU-CTR/CTIS 默认翻页收敛

- **诉求（彤）**：部署后全源回归测试——EU-CTR/CTIS 误判"超时"实为测试参数错误（误用 literature 的 `max_results` 而非 `max_pages`，节点抓默认页数累积超时）；真实问题在 DRKS（站点迁移）与 ISRCTN（holding）。
- **服务端（`adapters/coze/src/graphs/`）**：
  - `nodes/drks_search_node.py`：**迁移预检短路**——新增 `_precheck_drks_migrated()`（requests `allow_redirects=False` 探测旧入口 navigate.do，1.1s 命中 HTTP 307 → bfarm.de），命中即快速返回明确错误 + WHO 兜底指引，不再 Playwright 每页 30s 空转（此前 0 条耗 60s+）；`_do_search` 0 条时回读 page_title/url 记入 `site_hint` 诊断。
  - `nodes/isrctn_search_node.py`：**改用官方 XML API 彻底替代 Playwright 爬网页**（根因纠正）。此前误判 ISRCTN 处于 `/holding` 维护页；实测该页实为 **cookie/JS 机器人验证挑战页**（"Please enable cookies and JavaScript to use ISRCTN"，靠 `CHK` cookie 做跳转），无头浏览器被拦截返回此页 → 解析不到 `/ISRCTN` 链接故 0 条（彤反馈手工浏览器/WebFetch 均正常返回数据：cancer 5613 条 / diabetes 4314 条）。官方 FAQ 明确「请勿爬取本站，XML API 是获取试验数据更高效的方式」。改用公开 XML API `GET /api/query/format/default?q=<kw>&limit=<n>`（无需 key，返回 XML，**绕开验证挑战**），解析 `trial.publicIdentifierCanonical`（含 ISRCTN 前缀）兜底 `trial/isrctn` 子元素 + `trialDescription/title`；`max_pages` 映射为 `limit`（下限 10 / 上限 100，符合官方「限制单次查询规模」建议）；多关键词仍按 project_id 取交集；真正 0 匹配（`totalCount=0`）不再误报「站点异常」。已用逐行复刻脚本对真实 API 功能验证：cancer/diabetes 正确返回 10 条、编号标题无误，无匹配词返回 0 且不报故障。
  - `sources.py`：drks/isrctn 白名单注释登记站点状态（307 迁移 / holding），防后续误判。
- **本地（发布包）**：
  - `search_ictrp.py` `_build_simple_payload`：euctr/ctis **无显式 max_pages 时默认收敛**——euctr=3 页（~60 条）、ctis=2 页（~100 条）；EU-CTR 单页实测 ~13s，此前默认 10 页累积 130s+ 易撞网关/客户端超时；显式 `--max-pages` 可覆盖。
- **验证**：`py_compile` 3/3；预检逻辑 standalone 复刻实测 **1.1s 命中 307→BfArM**；search_node 分支与 sources 白名单一致（selfcheck A1 无影响）。
- ⚠️ 服务端改动需**重新打包部署**到 Coze 控制台才生效。**本地未发布**。

## Unreleased (2026-09-07 21:00) · EU-CTR/CTIS 抓取上移 Coze + 新增 CTIS 源

- **诉求（彤）**：功能/代码保护——EU-CTR 上移 Coze（本地解析器随包发布属资产泄露）；调研发现 CTIS（EudraCT 继任者，2022+）有**公开无认证 REST API**（实测打通，纠正此前"CTIS 需 OAuth2"误判），一并新增 CTIS 源（search + detail）。
- **服务端（`adapters/coze/src/graphs/`）**：
  - `sources.py`：`SUPPORTED_SEARCH_SOURCES` + `euctr`/`ctis`；`SUPPORTED_DETAIL_SOURCES` + `ctis`（euctr 不做 detail——EudraCT 详情页是 ASP.NET postback 壳，本地本就只有 list）。
  - 新 `nodes/euctr_search_node.py`：移植本地 `search_eu_ctr.py` 的 HTML list 解析（纯 HTTP requests，无反爬无需 Playwright），修复标题 label 前缀残留；实测 osimertinib 20 条。
  - 新 `nodes/ctis_search_node.py`：POST `/ctis-public-api/search`（关键字段 `searchCriteria.containAll`，非 keyword/sponsor——传错字段 HTTP 200 但 data 恒空）；实测 45 条。
  - 新 `nodes/ctis_scrape_details_node.py`：GET `/retrieve/{ctNumber}` 8 线程并行拉 events/results/documents（实测 13 字段）。
  - `search_node.py` / `scrape_details_node.py`：路由加 euctr/ctis 分支；**顺手清理 publisher_pdf 封存注释残留**（selfcheck A1 正则把注释行 `state.source=="publisher_pdf"` 误提取成分支 → 白名单差集 FAIL，删注释后 35/35 全绿）。
- **本地（发布包）**：
  - `search_eu_ctr.py` 121 行抓取器 → **薄壳**（`--source euctr` 转发 search_ictrp.py），旧逻辑保留为 `--local` 显式降级开关（迁移期防全断，实测 20 条）。
  - ⚠️ `--local` 已删除：抓取执行器上 Coze 后，本地不再保留 HTML 解析资产（符合 §20.14 "词表留本地、上移抓取执行器"）。
  - 新 `search_ctis.py` 薄壳（`--source ctis`）。
  - `search_ictrp.py`：API_SOURCE/RECORD_SOURCE + euctr/ctis；CLI `--source` choices 扩展；`_SOURCE_ID_RE` + euctr（WHO-COVERED 可 fallback；ctis 非 WHO 镜像**不**登记 fallback）。
  - `normalize.py`：ADAPTERS + `"CTIS": norm_euctr`（CTIS 字段与 EUCTR 同构）+ `--ctis` 入参。
  - `ct_registry.py`：`_run_tier2_fallback` spec 的 EUCTR 改 `is_endpoint=True`（走统一端点）+ 加 CTIS 行；新增 `--with-ctis` / `--ctis-keyword` CLI。
- **验证**：服务端三节点 mock-import 后**实测直连**（EU-CTR 20 条 / CTIS search 45 条 / CTIS detail 13 字段）；selfcheck 35/35；薄壳预览正确转发、`--local` 兜底 20 条；`_source_record_check` euctr 甄别单测通过（EUCTR 号三形态 True、ChiCTR/ctis 号 False）。
- ⚠️ Coze 端改动需**重新打包部署**到 Coze 控制台才生效；本地薄壳在部署前走 `--local`（euctr）或返回空（ctis 无本地旧实现）。**本地未发布**。

## Unreleased (2026-09-07 20:40) · WHO 兜底泛化到全部 5 个 WHO-COVERED 源

- **诉求（彤）**：CT.gov、EU-CTR、ChiCTR、ISRCTN、DRKS 五个 WHO 覆盖源，当"专门要查询某源但该源站点不通"时，自动将 WHO ICTRP 作为备用兜底，取回该源覆盖的试验（不中断、不空手）。
- **架构分层**：5 源分两组处理——ChiCTR/ISRCTN/DRKS 走统一端点（同 `search_ictrp.py`，判 `source_likely_down` 后同进程切 WHO）；CT.gov/EU-CTR 是 Tier1 本地直连（不经统一端点），兜底在编排层。
- **改动（`adapters/search_ictrp.py`）**：ChiCTR 专属 fallback 泛化为三源通用。
  - 新增 `_SOURCE_ID_RE`（`chictr`→ChiCTR 号 / `isrctn`→ISRCTN\d{8} / `drks`→DRKS\d+）+ `_source_record_check(rec, src)`（registry 字段 → 注册号字段 → raw 文本 三重甄别，按源参数化）。
  - 新增 `_fallback_who_for_source(payload, src, ...)`（原 `_fallback_who_for_chictr` 改名泛化，keyword 中→英本地化保留）；`run()` 触发条件从 `source == "chictr"` 放宽为 `source in _SOURCE_ID_RE`，信封字段随源名参数化（`<src>_records_via_who`、`fallback_reason=<src>_down`）。
  - 保留兼容别名 `_is_chictr_record` / `_fallback_who_for_chictr`（外部旧引用不失效）。
- **改动（`scripts/ct_registry.py`）**：Tier1 源（CT.gov / EU-CTR）站点不通兜底。
  - 新增 `_tier1_who_backfill(args, out_dir, norm_inputs, src_label, en_kw)`：WHO 主路径已成功（norm_inputs 已含 --ictrp）→ 镜像已覆盖，仅提示不重复发请求；否则补发一条 WHO 自由词检索到 `ictrp_backfill_<src>.json` 并并入归一化。无关键词/配额满/WHO 也失败均如实告警、不中断。
  - `_run_ctgov` 包 try/except `CalledProcessError`：CT.gov 官网不通时不再中断整个管线，自动走 WHO 兜底（修复原"无条件先行 + 站点挂即整体崩溃"缺陷）。
  - `_run_tier2_fallback` 的 EU-CTR 失败分支（rc≠0 非超时）补 `_tier1_who_backfill`；ISRCTN/DRKS/ChiCTR 走统一端点、adapter 内已有 fallback，编排层不重复。
- **验证**：`py_compile` 通过；`_source_record_check` 三源甄别单测 8/8；`_tier1_who_backfill` 三分支单测（已含 --ictrp 短路 / 无关键词 / 正常补发并入）；黑盒联测模拟 CT.gov 站点不通（rc=1）→ 触发 WARN + WHO 兜底成功并入 norm_inputs；双重失败（WHO 兜底也挂）时优雅降级、管线不中断。主路径 `--cond osimertinib` 预览/执行无回归。
- ⚠️ 本地改动**未发布**（发布需 ct-base §16 红线 + 用户授权）；本条目含 9/7 前两条（WAF 切换 + WHO 中英翻译）同属 v0.10.0 范围。

## Unreleased (2026-09-07 17:40) · WHO 中英自动翻译 + ChiCTR acw_sc__v2 纯 Python 破解

- **诉求 1（WHO 只支持英文 → 中文关键词自动翻译）**：实测 WHO ICTRP 端对中文关键词稳定返回 0（`光生物调节` 直发 0 条），英文正常（`photobiomodulation` 命中 974 条）。根因：WHO 端只按英文检索。在线翻译兜底（MyMemory）对医学术语不可靠（实测 `光生物调节`→`Photobioregulation`，WHO 命中 0；正确词 `photobiomodulation` 命中 974），故权威翻译必须进 curated term_map。
  - `adapters/search_ictrp.py` 新增 `_localize_who_keyword()` / `_localize_who_payload()`：对 `source=who` 的 payload（含 keyword 与 multi_keywords 两种形态）做中→英本地化——先走 `kw_localize` term_map（权威），词典 miss 的长尾词才落 `online_translate` 兜底，并如实标注 `source=term_map/online`。注入点两处：`run()` 入口（覆盖直接 `--source who --keyword 中文` 与 `ct_registry --with-ictrp` 主路径）、`_fallback_who_for_chictr` 构造 WHO payload 后（覆盖 ChiCTR→WHO 切换路径，其 keyword 是中文）。
  - 新增 CLI `--no-kw-localize`（默认开启，可关闭）。
  - `references/term_map.json` 增补 PBM 领域词条（ct-base 单源 → 双向同步，现 254 条）：`光生物调节→photobiomodulation (PBM)`、`经颅光生物调节→transcranial photobiomodulation (tPBM)`、`近红外光生物调节→near-infrared photobiomodulation`、`低强度激光治疗→low-level laser therapy (LLLT)`。
  - **验证**：`py_compile` 通过；隔离测 `_localize_who_keyword('光生物调节')→('photobiomodulation','term_map')`、复合短语「经颅光生物调节治疗儿童」拆词本地化、纯英文/`chictr` 源不误伤；联网实测 `--source who --keyword 光生物调节` → 自动转 `photobiomodulation` → WHO 命中 974 条（对比改前中文直发 0 条）。term_map 增补须同步 ct-base（本次已双写），发布前 `publish_preflight` 会校验一致性。
- **诉求 2（ChiCTR acw_sc__v2 技术解法，可改 Coze 代码）**：实测破解——ChiCTR 挑战页内联 `var arg1='<40 hex>'` + 混淆 JS，算法为 acw_sc__v2 标准结构：40 位位置重排表 + 固定 XOR 密钥 `3000176000856006061501533003690027800375`，**纯 Python 可确定性求解**（本地对拍 Node 执行挑战 JS 3/3 一致；带 cookie 重试即拿真实页）。同时发现旧节点两处失效根因：① 入口参数已改版——真实检索是 `searchproj.html?title=<kw>&page=N`，旧 `searchContent=`/`searchproj.aspx` 已失效（返回「最新注册」默认列表而非检索结果）；② 无需 Playwright 即可过 WAF。
  - `adapters/coze/src/graphs/nodes/chictr_search_node.py` **重写为 HTTP-first**：新增 `_acw_solve()`（纯 Python 求解）、`_is_challenge()`、`_http_session()`（curl_cffi 优先 TLS 指纹模拟 Chrome、回退 requests）、`_http_get()`（自动解挑战带 cookie 重试）、`_parse_results()`（新版 `<a class="tit1" title>` + `<td>` 行解析，兼容旧结构兜底）；`_do_search_http()` 为主通道，Playwright（`_do_search_playwright`）保留为整体失败/0 条时的降级兜底。
  - **验证**：`py_compile` 通过；mock Coze 依赖后真实 import 端到端跑通——识别挑战页提取 arg1 ✓、解析真实结果页 10 条（编号+标题准确）✓、真实会话 HTTP 自动解挑战后搜索「光生物调节」命中 10 条 ✓（页面不再含挑战标记）。
  - ⚠️ Coze 端改动需**重新打包部署**到 Coze 控制台才生效（`adapters/coze/coze_deploy_bundle_20260906_192243.zip` 为旧版）；本地侧 `search_chictr.py`（调统一端点）代码无需改，节点更新后自动受益。

## Unreleased (2026-09-07) · ChiCTR WAF 自动切换 WHO 线路专查 chictr 结果

- **诉求**：ChiCTR 直连被阿里云 WAF `acw_sc__v2` 拦截 / 后端节点故障（0 条 + `source_likely_down`，2026-09-06~09-07 持续）时，不再只能报「源不可用」，而是自动改用 WHO ICTRP 线路取回 ChiCTR 来源记录。
- **改动（`adapters/search_ictrp.py`）**：
  - `run()` 签名新增可选 `args` 形参；当 `source=chictr` 且对照探针判 `source_likely_down=True`、且未关 `--no-fallback-who` 时，调用新增 `_fallback_who_for_chictr()`。
  - 新增 `_fallback_who_for_chictr(payload, token, endpoint, timeout, source_label, args)`：用同一 keyword 发一次 WHO search，从返回记录中筛出 **ChiCTR 来源**（见 `_is_chictr_record` 三重兜底：registry 字段含 chictr / 注册号字段匹配 `ChiCTR(?:-[A-Za-z]{2,4})?-?\d{8,12}` 正则 / raw 文本含 ChiCTR 号），回填信封。
  - 命中后改写为：`records=chi`、`total=N`、`source_likely_down=False`、`fallback_used="who_ictrp"`、`fallback_reason="chictr_waf_down"`、`chictr_records_via_who=N`、`note=…`；WHO 线路也无 ChiCTR 记录则维持源不可用标记。
  - 新增 `_is_chictr_record(rec)` 与 `_CHICTR_ID_RE` 正则。
  - `main()` 三处 `run(...)` 调用点补传 `args=args`；新增 CLI `--no-fallback-who`（默认开启，可关闭回退）。
- **范围收敛**：仅对 `chictr` 源启用（用户诉求即 chictr）；`isrctn`/`drks` 仍走原「对照探针判故障」逻辑，不触发 WHO 回退（WHO 对二者镜像覆盖弱）。
- **复用既有链路**：回退走 `_run_once`（与正常检索同通道），不重复配额计数（usage_guard 仅在 `main()` 计一次）；临时文件落 `tempfile.gettempdir()` 用完即删。
- **验证**：`py_compile` 通过；隔离测 `_is_chictr_record` 对 `registry='ChiCTR'` / `Main ID='ChiCTR1900021234'` / `登记号='ChiCTR-TRC-14004108'` / raw 含 ChiCTR 号均判 True，对 `NCT...` / `DRKS...` / `ISRCTN...` 判 False。联网回退实测（2026-09-07，chictr 仍 down）：`run()` 正确判 `source_likely_down` → 触发 WHO 回退（`fallback_attempted=True`）；WHO 自身亦撞 `trialsearch.who.int` 导航超时时信封置 `fallback_who_status=who_error` 并追加 error_msg、维持源不可用标记、无崩溃；WHO 健康且命中 ChiCTR 记录时预期走 `fallback_used=who_ictrp` / `chictr_records_via_who=N` 分支（本机实测当日 WHO 亦偶发超时，未观测到非空命中样本，逻辑路径经单测覆盖）。**边界**：回退仅当 WHO ICTRP 线路本身健康才有效；若 WHO 同步故障则如实报 `who_error`，不伪装成功。

## Unreleased (2026-09-06 19:22) · 平台心跳/唤醒测试不落飞书审计

- **问题**：Coze 托管平台对端点的周期性心跳探活（payload 仅 `source`，如 `{"source": "chinadrugtrials"}`，不带 `query_origin`、无任何真实检索字段）经主图跑到 `feishu_write_node` 后照常落库，在飞书 searchlog 表产生 query_origin 为空的噪音行。
- **修复（coze 端 `adapters/coze/src/graphs/nodes/feishu_write_node.py`，仅飞书写入节点，检索照常跑）**：新增 `_is_keepalive_probe(state)`——`query_origin` 为空 **且** `querystr` 为 JSON 对象、键集 ⊆ `{"source"}`（心跳的极简形状）→ 判为平台心跳/唤醒测试，跳过写飞书（`feishu_error="skipped: keepalive_probe"`，主流程不受影响）。querystr 非 JSON / 非对象 / 空 / 含 source 之外任何键 → 一律不拦（保守，宁多写不漏暴露）。
- **判定边界（用户明确并实证，2026-09-06）**：专指 **coze 代码内部/平台发出的心跳唤醒**（用户实证其 querystr 非空、形如 `{"source": "chinadrugtrials"}`）；**外部入参不算**——合规客户端必然注入 `query_origin`（ct-base §8.6）不命中；外部入参即使漏注入 `query_origin`，querystr 也带 mode/keyword 等真实字段 → 照常落库，保留 v0.3.88"空值暴露不合规调用"的审计设计。
- **验证**：`py_compile` 通过；判定逻辑 10 类输入冒烟 ALL_PASS（心跳 `{"source":...}` 形状→跳过；带 qo 全字段合规入参→写；漏 qo 带 keyword 入参→写保留暴露；qs 空/非 JSON/含未知键→保守不拦）。重打包 `dist/coze_deploy_bundle_20260906_192243.zip`（52 条目，MD5 `65b671e284dbf27766e997c852da4053`，排除 `__pycache__`/`.venv`/`dist`/`CDE`/`srcX`/`assets`）。
- **生效边界**：需将新部署包上传 Coze 控制台重新部署后生效（上传需用户确认）。

## v0.9.3 (2026-09-06) · 新增本地 Web 检索工作台 workbench/ (v0.1.1, clinical-indigo)

- **新增 `workbench/` 目录**：本地可运行的单页检索控制台。前端 `index.html`（单文件、全内联零外链、SVG 图标、zh/en 97 键 1:1 对齐）+ 后端 `server.py`（stdlib `http.server` 编排 `scripts/ct_registry.py` 子进程，默认端口 8790，已加 CORS+PNA；端点 `/api/config /api/health /api/search /api/runs /api/task /api/download /api/run-delete /api/bug-report`）。
- **品牌统一 clinical-indigo**：与技能 `assets/icon.svg` 一致（`#1C6DD0`）；顶栏 logo 字节级内联真实 `icon.svg`（含 `logoShadow` 投影滤镜 + `translate(83,40)` 十字医学标记），去除此前自绘变体。
- **发布前修复（A/B/C/D/G 五项）**：① 配置漂移 `bugReport.enabled` 在 `workbench.config.json` 与 `#wb-config` 兜底双处统一为 `true`；② `server.py` 去掉硬编码绝对路径，改为 `_resolve_skill_dir()`（`CT_REGISTRY_SKILL` 环境变量 > 脚本父目录 > 向上回溯兜底）+ `PY=sys.executable`；③ logo 替换为真实 `icon.svg`、品牌切 clinical-indigo；④ 兜底 `modules` 补齐为 4 区（search-form/result/tracking/run-history）；⑤ `run_workbench.cmd` 改可移植 `python server.py`。
- **质量闸门**：ct-base §9 质量闸门 10/10 PASS；§16 三道闸门（secret_scan / shared_sync_check / spec_lint）对 workbench 目录无阻断；`py_compile` ✓ / 内联 JS `node --check` ✓ / 端点全 200（CORS+PNA 头齐全）✓；两段式反馈模态端到端可用。
- **已知非阻塞**：ct-registry 核心既有 `spec_lint` ERROR（F08 summary 超长 / F19 正文非英文）与本工作台无关，待另行整改。
- **启动方式**：`cd workbench && python server.py`（或双击 `run_workbench.cmd`），浏览器开 `http://127.0.0.1:8790/`。

## v0.9.3 (2026-09-06) · 修复 国家 列重复 (normalize 去重)

- **Bug**：检索结果 Excel 的「国家」列出现同一国名大量重复（如单格 106 个 "United States"），且概要国家分布被重复计数放大。
- **根因**：`normalize.py` 中 CT.gov 路径按**每个中心 location 各取一个国名**（第 89 行）、WHO 路径列表原样保留（542-545 行），均未去重；`export_xlsx.py` 的概要 `cc` 计数器又直接遍历该列表逐项 +1，双重放大。
- **修复**：在 `normalize.py` 两路提取后均用 `list(dict.fromkeys(...))` 按首次出现顺序去重；下游试验总表 / 原始明细 / 概要分布三处同步修正。
- **验证**：重跑 383 条归一化，记录内重复国家数 = 0；Excel 国家列重复 token = 0；单格最多国家由 106 降至 30（真实多国全球试验）；国家分布改为「每试验唯一国计数」（如 United States 120、China 185）。
- **验证（落地后）**：相对路径解析生效（`SKILL_DIR` 自动定位 `scripts/ct_registry.py`）；`/api/config` 返回 `clinical-indigo` + `bugReport.enabled=true` + 4 模块；`/` 首页 200 且含真实 logo；真实检索端到端 ok（CT.gov osimertinib）。
- **发布前规范整改（spec_lint ERROR 清零）**：F08 `summary` 精简为仅中文一句话；F19 `SKILL.md` 正文全文英文化（Features/Safety 中文段译英、Bug Reporting 用户触发短语英文化、Language 段 `中文指南`→`Chinese guide`）；F12 补齐 `.clawhubignore`（`workbench/runs/`、`workbench/__pycache__/` + `*.bak/*.zip/*.tar.gz/.idea/.vscode/_user_meta.json`）并与 `.gitignore` 同集；CHANGELOG 顶部版本头对齐 `0.9.3`（原 `Unreleased` → `v0.9.3`）。
- **WHO/ChiCTR 检索可靠性修复（2026-09-06 实测根因，源于 osimertinib NSCLC 检索「WHO 返回 0」）**：
  - **① WHO combined 模式合同守卫**：统一端点 WHO combined 仅认 `who_country/who_phase/who_date_*/who_sponsor/who_secondary_id/who_recruitment_status` 为「真筛选」，`who_condition/who_intervention/who_title` 不算；仅传后两者会触发后端内层校验错误（`combined 模式必须至少带一个筛选…`）返回 0 条。`search_ictrp._build_who_payload` 检测此情形自动降级为 search 自由词（实测 578 条），`ct_registry._who_cmd` 同步改为 disease+drug 默认走 search、仅显式给「真筛选」才用 combined（双层防御）。
  - **② 升级反馈环防数据丢失**：网关 `escalate_to_combined` 信号不再覆盖已取数据——`run()` 取到 >0 条即返回，避免升级失败把部分结果覆盖成 0；`_escalate_payload` 多词自由文本不再首空格臆测拆分（消除 `who_condition='non-small'` 类无效片段，整句作 `who_condition`）。
  - **③ 提交超时重试**：统一网关偶发抖动（提交偶卡死）导致误判 0；提交超时 30s→60s 且最多重试 3 次（指数退避）。
  - **④ 后端错误/空返回可见性**：`_parse_response` 提取 project_list 内层 `error` 提升到 `error_msg`；0 条+200+无错误标记 `empty_no_error`，使 ChiCTR 等「反复空返回（疑后端节点故障）」被编排层判失败并披露降级，而非静默当作「该源无结果」。
  - **效果**：修复前 WHO（combined+condition/intervention）返回 0、用户感知「WHO 不可用」；修复后同查询返回真实 osimertinib NSCLC 试验（如 Sac-TMT + Osimertinib 用于 III 期 EGFR 突变 NSCLC），WHO 全球覆盖恢复。
  - **⑤ `_control_probe` 对照探针 keyword 字段 bug 修复（2026-09-06 接力）**：探针 `_control_probe` 原把整个 `CONTROL_TERMS` 列表（如 `["二甲双胍","肺癌","高血压","aspirin"]`）整体塞进 `keyword` 字段（应为单字符串），端点收 dict 而非 str、POST 异常被 `except` 吞掉 → 探针永远返回 `None`、节点故障永远判不出。`search_ictrp._control_probe` 改为逐个对照词发同步请求、任一有数据即判定非故障、全空才返回 `True`→标 `source_likely_down=True`。`run()` 的触发条件本已正确（`payload.get("source") in CONTROL_TERMS`），无需改。
  - **⑤b `_control_probe` 真根因修复（2026-09-06 16:29 复测发现）**：模块**未导入 `requests`**（本模块走 urllib/共享通道），探针内 `requests.post` 抛 `NameError` 被 `except Exception: return None` 吞掉 → 探针仍永远返回 `None`（此前「触发条件本已正确」的判断有误，keyword 修复只是必要非充分）。修复：函数内局部 `import requests as _requests`；同时 `kws = ctrl if isinstance(ctrl,(list,tuple)) else [ctrl]` 修正 `ctrl[:2]` 对字符串按字符切分的隐患（「肺癌」→「肺」「癌」单字查询）。**验证**：探针隔离测试返回 `True`；完整 chictr 检索 `osimertinib` → `[SOURCE-DOWN]` 打印、`source_likely_down=True`、`error_msg` 明确「对照词（肺癌）亦返回 0+无错误，判定为源不可用而非真实零结果，查中国用 CDE」。当日复测 ChiCTR 仍坏（`肺/癌/肺癌/diabetes` 全 0）。
  - **参数带入复核（飞书后台实证）**：用户提供的飞书后台请求体 `{"keyword":"osimertinib","mode":"search","params":{"user_language":"en"},"skill_version":"0.9.3","source":"chictr"}` 与脚本 `_build_simple_payload`+`_attach_coze_contract` 构造的 payload 逐字段一致（`keyword`/`mode`/`source`/`skill_version`/`params` 均正确）；本地 `print_preview`(不加 `--run`) 复现同一 payload。后台另有一条 `{"source":"chictr"}` 仅含 source，是 vibeflow 初始化节点的**中间态快照**（只设 source），非最终请求体，**不代表参数丢失**。ChiCTR 返回 0 系后端节点故障（6 词对照实验含 metformin/肺癌/高血压/aspirin 全空、无 error），非参数问题。
  - **完整日志复核（用户提供的 `CTDB_searchlog (2).xlsx`，34 行）**：逐行验证后确认——① **ChiCTR 主查询参数全部正确带入**：7 条带词 chictr 请求（`keyword`=`osimertinib`/`奥希替尼`、`mode`=`search`、`source`=`chictr`）逐字段正常，非参数问题；② **裸 `{"source":"chictr"}` 共 12 次**（14:19–14:48，runtime 15.7–16.0s），是框架对 source 的**周期性探活请求**（只带 source 不带 query，端点正常响应回空），非主查询、不影响数据；③ **WHO combined 根因获日志实证**：带 `who_recruitment_status='Recruiting'`（真筛选）的 combined 跑满 164.7s，而只带 `who_condition`+`who_intervention` 的 combined **瞬时返回 0.009/0.005/0.036s**——后端合同校验失败立即回空，正是「WHO 返回 0」的根因；④ **可观测性盲区（重要）**：飞书后台 `resultstr` 字段**只记录 `runtime_sec`，不记录 `total_count`/返回条数/错误**，故平台侧**无法从日志区分「ChiCTR 节点故障返回的空」与「某词真无结果」**——所有 source 空返回在日志里都长一样（"请求成功、耗时 15.7s"）。本地落盘 JSON 已通过 `_control_probe` 标 `source_likely_down` 弥补此盲区，但平台日志格式非本技能可控。

## Unreleased (2026-09-03) · 对齐 ct-base coze_io_contract §1（入参信封）+ §2（飞书存储）

- **背景**：按 ct-base `references/coze_io_contract.md` 统一契约，所有 ct-* 技能调 coze 端点（不分计算/检索端点）一律遵守。ct-registry 此前仅 `query_origin`（ct-base §8.6）合规，`skill_version` / `user_language` 缺失、`runtime_sec` 未实现。
- **客户端 `adapters/search_ictrp.py`（§1.1 / §1.2）**：
  - 新增 `_skill_version()`（读 `SKILL.md` frontmatter `version:`，失败回退 `"0.9.3"`）。
  - 新增 `_attach_coze_contract(payload, args)`：出站 payload 注入顶层 `skill_version` + `params.user_language`（由 `scripts/i18n.resolve_user_language` 三级判定，按用户输入文本 zh/en）；幂等、不破坏既有检索字段。
  - `build_payload` 四个分支（detail / who / cde / simple）统一包裹 `_attach_coze_contract`，覆盖全部 `source`（who / chinadrugtrials / isrctn / drks / chictr）。
  - 导入兜底：`scripts/` 无 `__init__.py`，启动时把技能根目录加入 `sys.path` 再 `from scripts.i18n import resolve_user_language`。
- **§2.1（skill_version → 飞书 querystr）**：随客户端 `querystr` 序列化（`_run_once` L697-700，序列化 payload 除 querystr/query_origin）自动带出 `skill_version` → coze 端 `feishu_write_node` 写入飞书 `querystr` 列，满足契约。
- **coze 服务端参考 `adapters/coze/src/`（§2.2，2026-09-06 已修复并重新部署 `coze_deploy_bundle.zip` + 同步 `srcX/`）**：
  - `main.py` `/run` · `/stream_run` · `/node_run` 三入口收到 `request.json()` 即刻 `payload["received_at"] = time.time()`（此前仅 `/run`+`/stream_run` 两处，漏了 `/node_run`）。
  - `state.py` `GlobalState` / `GraphInput` / `FeishuWriteInput` 均新增 optional `received_at: float`，经状态透传至飞书节点。
  - 🔴 **`resultstr` 硬编码空串 bug 修复（根因）**：原 `feishu_write_node` 第 88 行 `record["fields"]["resultstr"] = ""` 写死空串——节点只拿到 `querystr`/`query_origin`，拿不到检索结果，飞书 `resultstr` 列永远空。修复后新增 `build_resultstr(state)`：写入**完整响应**（`total_count` / `error_msg` / `log` / `project_list`（>5KB 自动截断标记防单元格超限，2026-09-06 16:27 用户指定由 50KB 收紧）/ `scraped_data_json`（>50KB 截断））+ 顶层 `runtime_sec = round(time.time() - received_at, 3)`（仅当 `received_at` 非 None）；🔴 只进飞书日志、不出 coze 响应（§2.2 红线）。向后兼容：`received_at=None`（直连测试）时 `resultstr` 不含 `runtime_sec`，与历史格式逐字节一致。
  - **平台探活请求（心跳）处理**：飞书后台所见裸 `{"source":"chictr"}` 共 12 次（14:19–14:48，runtime ~16s）是 **Coze/飞书托管层对各注册 source 的周期性可达性探测（入站）**，非本工作流生成、亦非参数丢失；我们的代码原本会照常路由→打后端→返 0→还写飞书，既浪费 ~16s/次又污染审计表。修复双层防御：① `search_node` 入口用 `sources.is_health_probe_request()` 判定「仅 source、无真实检索参数」→ 短路返回（不触发后端检索）；② `feishu_write_node` 同步跳过落库（`feishu_error="skipped: health_probe"`）。**该探活请求无法从本工作流代码侧"删除"**（属托管平台行为），但已做到"瞬时返回 + 不污染日志"；若需彻底关停，须在 Coze/飞书控制台侧配置健康检查策略。
- **验证**：客户端 `py_compile` + 离线行为测试（4 个 source 路径均带出 `skill_version="0.9.3"`、`params.user_language` 按输入 zh/en 正确；`querystr` 序列化含 `skill_version`；幂等）；服务端三文件 `py_compile` 通过 + `runtime_sec` 计算逻辑单元抽查（round 3 位、`received_at=None` 留空）。

## Unreleased (2026-09-06 17:18) · WHO 抓取三层优化（A 切片累积 / B 主库直连 / C 端点断点翻页）

- **背景（当日实测定性）**：统一网关 WHO search 单次仅回 ~10 条——根因不是翻页缺失（服务端 `_do_who_search` 本会翻页），而是 `total_records > WHO_RESULT_CEILING(400)` 时**早退只回首页 + escalate 信号**；combined 需真筛选且 ~165s；网关 300s 硬墙。WHO 官方 `trialsearch.who.int` 全链路 200 无反爬。
- **A · `adapters/search_who_sliced.py`（新增）**：切片累积——宽查询切成 N 个窄子查询（`--by-registry` 按 WHO 一级注册库前缀 EUCTR/JPRN/CTRI/NTR/…、`--by-year` 按年份、或 `--slices` 自定义），逐片子进程复用 `search_ictrp.py`（继承降级守卫/超时重试/探针），按 Main ID 客户端合并去重，`--max-slices`（默认 5）控配额，输出含 per-slice 统计。
- **B · `adapters/search_euctr_direct.py`（新增）**：EU CTR 主库直连——`/ctr-search/search?query=` 收集 EudraCT 链接 → 国家版详情页（ES 优先，GB 停更自动跳过换国）按 label 解析（Full title/Sponsor/Trial status/EudraCT number 等），1.5s 限频 + EudraCT 本地缓存。**决策记录**：WHO `Trial2.aspx` 实测为纯 postback 壳（无数据无 JS 端点）不可纯 HTTP 直抓；ISRCTN 详情为 JS 壳（1.2KB）——两者放弃，EUCTR 实测直连完全可用（osimertinib 20 条/页、详情含 AstraZeneca/Novartis 等申办方）。
- **C · coze 服务端 `who_search_node.py` + `state.py`（已重打包部署 `coze_deploy_bundle.zip` + `srcX/`，待上传 Coze 控制台生效）**：
  - `SearchNodeInput`/`GlobalState` 新增 `page_start`（断点续抓起始页）与 `paginate_all`（显式翻页开关）。
  - `_do_who_search`：①`paginate_all=True` 时 `total>400` 不再早退，在 `WHO_NODE_BUDGET(270s)` 预算内从 `page_start` 尽力翻页，`is_partial` 标记缺口；②`page_start>1` 先 `__doPostBack` 跳页再续翻；③输出新增 `page_start/page_end/next_page_start`，客户端据 `next_page_start` 续抓累积；④默认不传时行为与历史逐字节兼容。
  - 客户端 `search_ictrp.py` 配套：`--page-start` / `--paginate-all` 透传进 payload（who search 分支）。
- **验证**：5 文件 `py_compile` 全过；客户端 payload preview 确认 `page_start/paginate_all/max_pages` 正确入包；内网文件服务器部署后 grep 校验 4 项（page_start 参数/paginate_all 守卫/next_page_start/state 字段）全 FOUND。A/B 层 live 测试：EUCTR 直连 3/3 成功；切片累积测试运行中（见工作区 `who_sliced_test.log`）。
- **遗留**：①C 需用户重新上传 Coze 控制台后才实际生效；②EUCTR 详情 `试验状态` 字段标签变体（部分国家版未捕获）待补；③A 层合并结果是样本（每片 10 条）非全量，全量仍需 C 层续抓循环。
- **A 层 live 测试补记（2026-09-06 17:35）**：①按注册库前缀切片（`osimertinib EUCTR` 等）实测**不可行**——WHO 自由词不索引 Main ID（JPRN 片干净 0 条，非故障）；②正确切片轴为 **combined + `who_date_*` 年份桶**（真筛选，桶内服务端可完整翻页）；③但当前统一网关对 WHO combined 严重不稳（提交连续抖动重试 + 600s 轮询超时），日期桶单测未通过（`who_yearbucket_test.log`）——属端点当日故障，非代码问题，网关恢复后 A 的日期桶策略可用；④单片超时默认已提至 240s（120s 会误判）。
- **复查修复（2026-09-06 17:45）**：`_do_who_search` 断点续抓补 2 个边界守卫——①跳页到 `page_start` 返回空时**回退从第 1 页重抓**（原实现会带着第 1 页数据冒充第 N 页，客户端合并错位）；②`page_start > total_pages` 时返回**空集 + `page_end=None` + `next_page_start=None`**（原实现会静默返回第 1 页数据且页码区间越界）。修复后重编译 + 重打包（287,776B），SHA256 三方（本地/zip/srcX）逐一核对一致（注意：PowerShell 5.1 读无 BOM UTF-8 中文会乱码，grep 校验需 `-Encoding UTF8`，此前一次 False 为读取误报）。

## Unreleased (2026-09-01) · nmpa_pv 始终返回 0 归因 + 数据源改指 CDR-ADR + WAF 检测/诊断加固

- **根因（主因·已修）数据源 URL 失效**：原 `BASE_URL = https://www.nmpa.gov.cn/xxgk/yjjsh/ypblfytb/` 已于 2026 年**改版迁移**——真人浏览器访问提示「页面有更新」并跳回首页，脚本客户端直连返回 **HTTP 412 WAF**。服务端无头浏览器拿到的是首页空壳 → 解析 0 锚点 → 被旧逻辑**静默当成「真 0 条」**（假阴性）。原本机只看到 412 误把 WAF 当主因，用户真人浏览器反馈「跳首页」才定位到 URL 迁移。
- **修复**：`BASE_URL` 改指 **国家药监局药品评价中心（CDR-ADR）「安全警示 > 药品」栏目** `https://www.cdr-adr.org.cn/sy_aqjs1/yp`（实测 HTTP 200、含真实内容、标题带药名）。该站**无 nmpa.gov.cn 式强 WAF**，服务端无头浏览器可直接抓取。新增 `SUB_LISTS`（信息通报历史 / 药物警戒快讯 / 公告通告三个子栏目完整列表）与 `SEED_URLS`，`_do_scrape` 改为遍历种子页而非失效的 `index_N.html` 分页。
- **WAF 检测** `_detect_waf(html, title)`：识别空标题 + 随机 id 的 `<meta>` 挑战标记、常见挑战文案（访问验证/人机验证/captcha/…）、WAF 厂商签名（incapsula/cloudflare/yundun/…）。命中即标记 `status="blocked"` 并明确告警「请勿把 0 当真 0」。
- **页面级诊断** `_gather_diag()`：每页收集 `page_title / html_len / total_anchors / html_anchors / waf_detected / sample_hrefs / sample_anchor_texts`，打日志并随响应返回，部署后无需翻服务端日志即可定位真因。
- **等待策略**：`wait_until="commit"` → `wait_until="load"` + 等待列表锚点 `a[href$='.html']` 出现，兼容 JS 渲染列表。
- **结果状态字段**：输出 JSON 新增 `status`（`ok`/`blocked`/`empty_list`/`no_match`/`error`）与 `diagnostics`；`blocked` 时带 `error: "WAF_BLOCKED: …"`。ct-safety 客户端 `nmpa_coze.py` 解析 `projects`/`tier`，新增键不影响既有契约。
- **解析健壮性**：`<a>` 标题文本为空时回退读 `title` 属性；`.html` 过滤放宽含 `.shtml`。
- **验证**：`py_compile` 通过；用真实 CDR-ADR 页面离线复刻 `_parse_list` 逻辑，确认相对链接 `./202006/t20200615_47501.html` 经 `urljoin` 正确拼为绝对地址、药名过滤生效（甲氨蝶呤→第75期、含钆对比剂→第76期、阿莫西林→0 为正确结果）。重建部署包 `adapters/coze/coze_deploy_bundle.zip`（MD5 `d5e293cf5dd4b87fb7e618e3bc1ab01d`，48 文件，排除 `CDE/`/`_archive_20260820/`/`__pycache__`）。**待用户重新上传 Coze 控制台后，对 `甲氨蝶呤` 等应返回真实命中；`阿莫西林` 等常用药返回 0 属正确（未进入信息通报，可查同栏修订说明书公告/警戒快讯）。**

## v0.9.3 (2026-08-29) · 去重桥接可审计化：每条记录输出 dedup_reason / dedup_tier

- **来源**：ct-update 2026-08-29 周检 P1-F「去重桥接加固」。动机：非英文试验（尤其 CDE/ChiCTR）依赖自由文本里的注册号做跨库桥接，而聚合层此前只输出 `dedup_group_id`，**误并（false positive）与正确合并在结果里无法区分**，漏并同样无迹可查。
- **`scripts/aggregate.py` `dedup()`**：新增合并证据链。每次真正折叠两个簇的 `union()` 都登记 `(i, j, tier, evidence)`；分组后为每条记录写两个增量字段：
  - `dedup_reason` — 人类可读证据，如 `tier1_id_bridge (shared registry id CHICTR2000029999) <-> CTGOV:NCT01234567`、`tier2_fuzzy (title match + sponsor/start_year=2021/intervention) <-> CTRI:CTRI/2021/05/033333`；单例为 `singleton: no cross-registry match`。
  - `dedup_tier` — `tier1_id_bridge` / `tier2_fuzzy` / `transitive` / `none`（可组合，如 `tier1_id_bridge+tier2_fuzzy`）。
  - **`transitive` 档的必要性**：并查集是传递闭包，A-B、B-C 成立时 A 与 C 同组但无直接边；这类记录标 `transitive` 并列出同组对端，避免"无证据"被误读为 bug。
- **`dedup_summary` 新增**：`merge_edges`（实际合并边数）、`dedup_tier_breakdown`（各档记录数）。
- **`scripts/report.py`**：报告的跨库去重段落输出合并依据分布，并对 `tier2_fuzzy` 单独告警——该档仅凭"标题 + 单一佐证（申办方/起始年/干预之一）"即合并，误并风险最高，提示抽查 `dedup_reason`。
- **兼容性**：纯本地、零联网；仅增量追加字段，`dedup_group_id` / `primary_source` / `registry_id_norm` / `secondary_ids` 与 `dedup_summary` 原有键全部保持不变（冒烟测试含向后兼容断言）。
- **验证**：`py_compile` aggregate.py + report.py 通过；17 项断言全绿的冒烟测试覆盖四条路径——Tier1 注册号桥接（CT.gov↔ChiCTR 中英文对照）、Tier2 模糊匹配（CTRI↔CT.gov 无共享 ID）、singleton、原有字段向后兼容。

## v0.9.2 (2026-08-27) · 凭据模块改名 config/keys.py → adapters/endpoint_token.py

- **问题**：`config/keys.py` 的命名/位置与已发布技能（ct-base `adapters/coze/src/endpoint_token.py`、ct-advisor `adapters/coze_token_embedded.py`）不一致；`config/` 目录本应只放 JSON 配置，混入 `.py` 凭据模块易触发误读/扫描告警。
- **改名**：`config/keys.py` → `adapters/endpoint_token.py`；import 由 `from config.keys import ...` 改为 `from endpoint_token import ...`（同目录兄弟模块，机制与既有 `from extsvc_client import ...` 一致）。
- **同步**：README / README_zh-CN / SKILL.md / `adapters/coze/CDE/cde_workflow.md` 及代码内注释的 `config/keys.py` 引用全部更新；`config/ictrp.dat` 等历史引用保留不动。
- **验证**：py_compile 全过；`search_ictrp.py` 离线 preview 正常；`scripts/publish_preflight.py` 闸门全绿（exit 0）。

## v0.9.1 (2026-08-27) · 飞书表 querystr 去重 query_origin（ct-base §8.6）

- **问题**：飞书多维表格的 `querystr` 列重复打包了 `query_origin` 键值，而 `query_origin` 已由独立列保存（ct-base §8.6 客户端注入、coze 端透传写入），属冗余。
- **coze 端 `adapters/coze/src/graphs/nodes/feishu_write_node.py`**：新增 `_strip_query_origin()`，在飞书写入前从 `querystr` 移除 `query_origin` 键（仅当 querystr 为含该键的 JSON 对象时剥离；非 JSON / 非对象 / 解析失败一律原样返回，不破坏既有内容）。
- **调用方 `adapters/search_ictrp.py`**：序列化 `querystr` 时同步排除 `query_origin`（与 `querystr` 自身一同从序列化集合剔除），从源头不再发出冗余键值。
- **验证**：py_compile 两文件均通过；`_strip_query_origin` 对「含 query_origin JSON / 不含 / 非 JSON / 空串」四类输入行为均正确。

## v0.9.0 (2026-08-22) — 增加 bug report 功能（ct-base §20.3 接入补齐）

- **🔴 bugreport 接入补齐（发布前检查发现缺漏）**：
  - `adapters/bug_report.py` 升级为含历史回执的当前版本（补齐 `confirm_thanks`/`build_followup`/`parse_history` + `_MSGS` thank/done/pending 双语文案 + `send_to_endpoint` 透传 `history`）；此前为旧副本，缺 §20.3.7 历史回执。
  - `config/config.json` `auto_approve_endpoints` 补齐统一 bug-report 端点 `https://ct-bugreport.coze.site/run`（此前仅含计算端点，违反 §20.3.5）。
  - `README.md` Safety 段新增 bug-report 端点出站披露（§16.6，此前缺失）。
  - `SKILL.md` Bug Reporting 段补齐「主动触发」显式请求路径（§20.3.1）+ 发送后历史回执（§20.3.7），此前仅强信号路径、无回执约定。
- 三道发布闸门：publish_secret_scan（0 P0/0 P1）、shared_sync_check（无漂移）、clawhub_security_audit（仅预已发布技能的既有审计项，无新增阻断）。

## v0.3.88 (2026-08-20) · query_origin 生成主体红线落地（ct-base §8.6 更新）

- **背景**：飞书表成对验证发现 coze 端 `query_origin` 跨窗口漂移（08-14 `ad2d1f` → 08-20 `086aaa`）——根因是 coze 端兜底生成 `sha256(容器 hostname)`，容器重建即变，且标识的是服务器而非来源机器。ct-base §8.6 据此明确红线：**`query_origin` 必须由技能安装设备（客户端）生成并携带，禁止由 Coze 服务器生成**。
- **调用方 `adapters/search_ictrp.py`**：新增 `_compute_query_origin()`（`sha256(本机 hostname)`）；参数解析后**未显式传 `--query-origin` 时自动计算注入**（4 处透传逻辑原本就存在，此前因参数恒为 None 从未生效）；`--query-origin` help 文案同步（"缺失时 Coze 自动生成"→"必须由本机生成，未传自动注入"）。
- **coze 端（`adapters/coze/src/` 本地基准，待重新部署生效）**：`search_node` / `who_search_node` / `scrape_details_node` 移除"缺失时自动生成"兜底，改为**缺来源告警 + 保留空值**（飞书表该行 query_origin 为空，暴露不合规调用）；`state.py` 8 处 `query_origin` 字段描述全部对齐新语义；`_compute_query_origin` 定义保留仅供客户端参照。
- **验证**：本机注入值 `sha256:b8cae3d4...` → 真实出站回传**完全一致**（coze 端"客户端已传则保留"路径本就存在，无需改）；list/detail 双模式 preview 均自动注入；coze 端 py_compile 全过、无 `state.query_origin = _compute_query_origin` 残留。
- **生效边界**：本地调用方改动**立即生效**（同一技能安装设备所有调用 query_origin 恒定，不再漂移）；coze 端兜底移除需**重新部署工作流**后生效（部署前线上仍兜底生成，但正常路径客户端已注入，无影响）。

## v0.3.87 (2026-08-14) · 调用方流式 SSE 解析落地 + 死代码清理（发布前整改）

- **流式调用改造（调用方 `adapters/search_ictrp.py`）**：
  - 根因：上一轮 `_parse_sse` 仅设计方案、未对真实 SSE 验证，假设结果在终帧 `data.data`；但真实 coze 流 `workflow_end.output` 恒为 `{}`、结果在主节点 `search_node`/`scrape_details_node` 的 `node_end.output`，且**普通流式不发 node 帧**，必须带 `x-workflow-stream-mode: debug` 头。
  - 落地 `_parse_sse`（从主节点 `node_end.output` 取回传参数 project_list/total_count/log，忽略恒空终帧，抽 error_msg）+ `_try_stream`（强制 debug 头、取不到自动回退同步 `/run`）；`_run_once` 流式优先；`run()` 与全部调用点透传 `use_stream`；新增 `--no-stream` 开关。
  - 验证：CDE「肺癌」流式取到 **1308 条**真实记录；`--no-stream` 同步回归 HTTP 200 正常。coze 端零改动。
- **死代码清理（`config/keys.py`）**：删除 0 调用的历史遗留 `store_token()`（唯一可写 `.dat` 的路径，曾触发 §16.0 `never written` 注释矛盾）+ `config_path()`；`get_secret` 对 `LEGACY_DAT_PATH` 的只读回退保留。
- **发布前检查（ct-base §16）整改**：补 `.gitignore`/`.clawhubignore` 裸 `tests/`+`scripts/tests/` 排除（防测试源码随 ClawHub 包泄漏）；README 补反幻觉信任段（§13.3）与英文版耗时/量上限警告（§13.7）；SKILL.md 正文中文「检索耗时提示」块英文化（§16.2）；**§16.9 出站调用归专用目录**：11 个出站脚本从 `scripts/` 迁至新建 `adapters/`，`ct_registry.py` 子进程路径改指 `ADAPTERS_DIR`，纯本地脚本（normalize/aggregate/report/parse_cde/usage_guard/i18n）留 `scripts/`；本条目对齐 version 0.3.87；§16.0 审计 2 个 STILL_PRESENT 中 `never written` 项已实质解决。
- 仍全部本地改动，未发布（推送 / 上传 Coze 平台需用户确认）。

## v0.3.86 (2026-08-14) · WHO 检索首屏大结果集探测 + 升级阶梯（抗封优化落地）

- **背景**：用户确认"尽量走高级检索"= 大结果集探测拦截；`WHO_RESULT_CEILING` 定为 **400**。coze 端 + 调用方（`search_ictrp.py`）一起优化。
- **coze 端 `coze/src_backup/src/graphs/nodes/who_search_node.py`**：
  - 新增常量 `WHO_RESULT_CEILING = 400`（约 40 页，仍在 `max_pages=50` 内）。
  - `_do_who_search`（basic）与 `_do_who_advanced_search`（combined）首屏读 `total_records` 后接入拦截：超 400 **不翻页**，回传 `escalate_to_combined` / `escalate_to_advanced` 信号 + `is_partial=True` + 首屏占位数据（约 10 条）。
  - 中档（100–400）允许翻页但置 `is_partial` 标记。
  - `who_search_node` 主节点把信号透传进 `project_list` 的 `output_data`（随 JSON 字符串回传，无需改 state 模型字段）。
- **调用方 `scripts/search_ictrp.py`**：
  - `_parse_response` 从 `project_list` 内层 `inner` 透传 `escalate_to_combined` / `escalate_to_advanced` / `large_result_set` / `is_partial` 到 `out_obj`。
  - `run()` 重构为升级反馈环（外层循环，最多 `MAX_WHO_ESCALATION=2` 次重发）：收 `escalate_to_combined` → 调 `_escalate_payload` 升 combined（已有 `who_*` 直接升；含分隔符 keyword 粗拆 `who_condition`/`who_intervention`）；收 `escalate_to_advanced` → 加 `who_recruitment_status=Recruiting` 升 advanced 终态；仍超限则终止、保留截断结果交上层/用户收窄。
  - 新增 `_run_once` / `_escalate_payload` / `_read_out_json` 辅助函数；顶部加 `import re`。
- **架构边界**：粗粒度 keyword 拆词为尽力而为，精准拆分仍由上层 `ct_registry.py` 完成（`search_ictrp` 无 LLM）；basic 单 keyword 无分隔符时返回 `None` 交上层，不猜词丢结果。
- **验证**：两端 `ast.parse` 语法校验 ✓；`_escalate_payload` 升级逻辑单测（中文/英文空格拆、无分隔→`None`、combined→advanced 加 Recruiting）全过 ✓。
- **文档**：`coze/WHO_SEARCH_OPTIMIZATION.md` §0.6/§3.2/§3.9 标注已落地。
- 仍全部本地改动，未发布（上传 Coze 平台 / 推送需用户确认）。

## v0.3.85 (2026-08-13) · CT.gov v2 检索 P2 补齐 + 真实联网回归（全套参数覆盖完成）

- **背景**：用户指出"P0 1 2 全部依次实现"含 P2（上轮只做到 P1），本轮补完 P2 四项。
- **`scripts/search_ctgov.py` 新增（P2）**：
  - `--geo`：`filter.geo` 地理距离，接受 `distance(lat,lon,dist[km|mi])` 或裸 `lat,lon,dist`（自动包装），并强制官方半径范围 **1-500 mi / 1-805 km**（超范围即报错；`_normalize_geo` 幂等，`_build_params` 编程调用亦兜底）。
  - `--patient`（`query.patient` 患者友好搜索）。
  - postFilter.* 四参数：`--post-status`/`--post-ids`/`--post-geo`/`--post-adv`（语义同 filter.* 但不影响相关性排序）。
- **真实联网回归（用户提示"现在应该是真实环境了"）**：沙箱 urllib 直连 clinicaltrials.gov 成功，全参数实测通过——P0 组合（phase+多值状态+sort+日期）5/5 字段级命中、`--ids` 精确 2/2、`--geo` 上海 50km、`--patient`、postFilter 3/3、`--adv` 3/3、`--fast` 分页正常。
- **发现并修正**：`query.rmtln` 为 **v1 遗留参数、v2 API 已移除**（真实请求 HTTP 400，与 `query.term` 对照确认）→ 移除 `--rmtln`，文档注明替代（`--query`/`--adv`）。
- **至此官方 v2 `/studies` 全参数覆盖**：10 个 query.*（cond/intr/spons/term/titles/outc/lead/id/locn/patient）+ 5 个 filter.*（overallStatus/ids/geo/advanced + postFilter 同构）+ sort + fields + pageSize/pageToken/countTotal。
- **验证**：py_compile ✓；断言（P2 四项 + 范围拦截 + P0/P1 回归）全过 ✓；真实联网回归全参数 ✓。
- **文档**：README.md / README_zh-CN.md 参数说明补 P2、移除 rmtln；`CTGOV_V2_PARAM_AUDIT.md` 标记 P0+P1+P2 全落地 + 真实回归记录。
- 仍全部本地改动，未发布。

## v0.3.84 (2026-08-13) · CT.gov v2 高级检索完整支持（P0+P1 落地，主功能强化）

- **背景**：用户委托审计 CT.gov 检索能力（`CTGOV_V2_PARAM_AUDIT.md`），结论 = 原 `search_ctgov.py` 仅覆盖 3/9 `query.*` + 1/5 `filter.*`；本次将 P0+P1 全部落地。
- **`scripts/search_ctgov.py` 重写（纯参数层扩展，向后兼容）**：
  - `query.*` 补齐：新增 `--query`（query.term，支持 AREA[]）、`--titles`、`--outc`、`--lead`、`--id`、`--locn`。
  - `filter.advanced`：新增 `--adv` 原始表达式透传 + 便捷参数 `--phase`/`--study-type`/`--age-group`/`--sex`/`--has-results`（自动组装 AREA[] 表达式，多值 `(A OR B)`，与 `--adv` 做 `(<便捷>) AND (<--adv>)` 合并）。
  - 服务端日期区间：`--first-post-*`/`--last-update-*`/`--start-date-*`/`--primary-completion-*`/`--completion-*`（since/until → `AREA[Field]RANGE[since,until]`，缺省 MIN/MAX）；`--date-after` 旧本地后过滤保留。
  - 多值：`--status`/`--ids` 逗号多值 → 管道分隔；`--sort`（≤2 个，`field[:asc|:desc]`/`@relevance`）→ 管道数组；`--fields` 暴露。
  - 校验：枚举白名单（phase/study-type/age-group/sex）、日期 YYYY-MM-DD 严格校验、sort 数量与格式——非法即 argparse 报错。
- **验证**：py_compile ✓；离线参数组装断言 13/13 ✓；CLI PREVIEW URL 构造 + 非法参数拦截 ✓；真实联网回归待部署环境。
- **文档**：README.md / README_zh-CN.md 补 CT.gov 高级检索示例与参数说明；`CTGOV_V2_PARAM_AUDIT.md` 标记 P0+P1 已落地（P2 于 v0.3.85 补齐）。
- 仍全部本地改动，未发布。

## v0.3.83 (2026-08-13) · Keyword gate 非交互防呆 + 文档修复

- **新增 `CTGOV_V2_PARAM_AUDIT.md`（CT.gov v2 检索能力审计，用户委托）**：对照 OpenAPI 规范 / Search Areas / Expert Search 语法核实，结论 = 本地 `search_ctgov.py` 仅覆盖 3/9 `query.*` + 1/5 `filter.*`（且状态仅单值），**`filter.advanced`/sort/服务端日期区间/多值状态全缺**；给出 P0–P2 缺口分级与 CLI 透传扩展设计（纯参数层，normalize 管线零影响）。


- **根因（实测复盘）**：`_kw_system_gate()` 未确认时无条件 `sys.exit(0)`，不检查 stdin TTY、不理会 `--auto-confirm`（它只管结果条数确认）——agent 非交互照抄 SKILL.md 示例命令必静默退出、零产物。
- **① 代码防呆（`scripts/ct_registry.py`）**：gate 菜单分支前加 `if not sys.stdin.isatty():` → 非 TTY 时自动 adopt 已展开词集并继续（打印提示），交互模式行为不变；显式 `--no-expand` / `--kw-en|--kw-zh` / `--kw-adopt` 仍优先。验证：`echo "" | ct_registry.py --cond ... ` 非交互直达 PREVIEW ✓（不再 kw_gate.stopped）。
- **② SKILL.md**：one-shot 示例命令补 `--no-expand` + 注释"agent/非交互必须带 --no-expand / --kw-en / --kw-zh / --kw-adopt"。
- **③ references/search_procedure.md**：Keyword gate 小节新增 🔴 非交互警告（四选一参数 + 解释 --auto-confirm 无效范围）。
- **④ i18n 缺失修复（xlsx 键名问题）**：`scripts/i18n_messages.json` 缺失导致 `t()` 全部回退键名——Excel 交付物 sheet/单元格标题显示为 `xlsx.sheet.*` / `xlsx.kpi.*` 等键名而非文本。已从 ct-base 底座复制主文件（31,658 B）补齐；验证 `t("xlsx.sheet.readme")→"说明"`、重导出 sheet 名=「说明/检索结果概要/试验总表/原始明细」✓。
- **⑤ 多源遍历优化（Coze 源码分析后落地）**：
  - **CT.gov 基座无条件先行**：原 `if not skip_covered: _run_ctgov`（WHO 成功时跳过 CT.gov）→ CT.gov 恒跑——Tier-1 免费直连、零共享配额、秒级且数据比 WHO/ICTRP 实时；WHO 成功时仍保留 CT.gov 作实时基座与交叉验证，normalize/aggregate 按 registry_id 去重不重复。
  - **WHO 快速失败可配 `--who-timeout`**（默认 **90s**，透传 `search_ictrp.py --timeout`）：WHO 被挡/超慢时不阻塞，CT.gov + CDE 基座出结果；传 `--who-timeout 300` 恢复完整 5 分钟版（等待 WHO 全量返回）。验证：默认 90 / 显式 300 命令构造 ✓、py_compile ✓、--help ✓。
  - WHO + CDE 并行（Batch-1 `_run_batch1` ThreadPoolExecutor）——已实现，本次确认无需改。

## coze 归档同步 (2026-08-13) · 线上导出 `project_20260813_085334.tar.gz` 核对 + 刷 src_backup

- **核对结论：SEARCH 缺口已正确补齐**。导出包 `src/graphs/nodes/` 含 `isrctn_search_node.py` / `chictr_search_node.py` / `drks_search_node.py`；`search_node.py` 路由含 who/isrctn/drks/chictr 四源分支（含 import）。`search_node.py` / `isrctn_search_node.py` / `chictr_search_node.py` 与本地目标态逐字节一致。
- **`graph.py` 仍只有 `search_node` / `scrape_details_node` / `feishu_write` 三图节点**（确认 ISRCTN/ChiCTR/DRKS 是 `search_node` 内部路由子函数，非独立图节点——这正面解释了此前 `JSON format error` 根因：平台「新增节点」面板要 JSON schema，而本工作流无需新增节点）。
- **15 个 `.py` 全部 `py_compile` 通过，无 `NameError` 隐患**；`drks` 占位节点会实际 GET `drks.de` 门户壳并解析 0 条、返回空列表（符合搁置、不污染数据）。
- **`src_backup/` 已用线上真值覆盖**（旧版备份至 `coze/src_backup_pre20260813/`）；并重加 `state.py` 的 `GraphInput`/`SearchNodeInput`/`ScrapeDetailsInput` 的 `source` 五源描述（与 `GlobalState` 对齐）。
- **待办（部署环境回归，沙箱出网受限未跑）**：`source=isrctn` / `source=chictr` 的列表→详情全链，确认 `project_id` 为各源真实编号。

## 0.3.82 (2026-08-13) · 安全审计整改（ClawHub SkillSpector / NVIDIA，审计对象 v0.3.80）

- **SKILL.md manifest 披露修正（消除 Description-Behavior Mismatch 类发现）**：
  - `summary` / `description`：ChiCTR 由「用户粘贴不出域」改为「经统一端点（source=chictr，第三方，共享 Bearer）检索，粘贴仅作本地解析兜底」；ISRCTN 由「公开 API 已失效」补「但可经统一端点（source=isrctn）取」。
  - `description` / `network_note`：补 PDF 文档下载（`download_docs.py` → 本地 `--out-dir`）与 `--cde-api-key` 商业 API 路径声明；`network_note` 显式说明 ChiCTR/ISRCTN/DRKS 同样经统一端点出域、共享 Bearer 是**作者发布的长期共享公开凭据（XOR+base64 混淆、可从包提取）**、非个人密钥、滥用可停用。
  - `filesystem` / `data`：写明可选写 PDF；`data` 由「无外部传输」改为「仅公开查询词经统一端点/可选 CDE API 出域，不发送用户文件或密钥」。
- **`references/units.md` 浏览器说明修正（消除 Intent-Code Divergence High）**：原「NEVER use Playwright」改为真实分层——T1 直连纯 HTTP 无浏览器；**T2 统一端点在服务端用 Playwright**；**CDE 粘贴模式本地回退用 Playwright**。明确「本技能脚本不直接抓浏览器」但「浏览器自动化确实存在于两处」。
- **删除孤儿 `references/report_template.md`（消除 Context-Inappropriate Capability + 生成 R 脚本两条 High）**：该文件是完整的样本量/效能分析模板 + 可独立运行 R 脚本，与注册检索无关（从 ct-samplesize 误带入，无任何 ct-registry 代码加载），已移至 `_archived_orphans/`（可恢复，不随技能发布扫描）。
- **未改项（用户决策）**：内嵌共享 Bearer token（XOR+base64）按既定授权保留发布；`store_token()` 在 0.3.81 已不存在（审计扫 0.3.80，已过时）。
- **修正 `coze/MODIFICATION_GUIDE.md`（解决"JSON format error"）**：本项目是 **LangGraph 代码工作流**，`graph.py` 全图只有 `search_node` 一个图节点，ISRCTN/ChiCTR 搜索是其**内部路由子函数**（非独立图节点）。原指南"新增两个 task 节点"写法误导用户在 Coze 画布点「新增节点」（该面板要 JSON schema）而报 `JSON format error`。改为**纯文件操作**：新增 `isrctn_search_node.py`/`chictr_search_node.py` + 整文件替换 `search_node.py`，`graph.py` 不动、节点 I/O 由 Pydantic 自动推导、不填任何 JSON 框。
- **`coze/src_backup/src/graphs/state.py`**：`GraphInput.source` / `SearchNodeInput.source` 描述补全 5 源（原只写 chinadrugtrials/who），与 `GlobalState.source` 一致；py_compile 通过。
- **`AGENTS.md`**：移除已移出的 `report_template.md` 引用（断链修复）。
- **影响**：本地未发布；若重跑审计，manifest 低估来源 / ChiCTR 出域 / 浏览器 / 能力漂移四条主因应显著降低。下一步是否重新发布到 ClawHub 等平台**等你确认**（红线）。

- **`search_ictrp.py` 新增 `--fetch-mode {list,detail,both}`**：把"列表 / 详情 / 列表+详情"三种需求显式化、对称覆盖 who / chinadrugtrials / isrctn / drks / chictr。
  - `list`（默认）：仅检索列表，1 次 Coze 调用。
  - `detail`：仅下载详情，需 `--project-list`（列表输出文件或 project_list JSON 字符串），1 次调用。
  - `both`：检索列表后**同一次调用内**自动拉取详情（内部 2 次 Coze 调用，但同一 `demand_id` 去重只计 1 次配额）；详情输出到 `<out>_detail.json`。
- **成本护栏**：`both` 模式下列表 >100 条默认跳过自动详情（与 CDE `_run_cde_detail` 跳过逻辑一致），加 `--auto-confirm` 强制拉取。复用列表输出已保留的 `project_list_raw` 字段作 detail 输入。
- **编排器 `--with-detail` 对称覆盖 WHO/ISRCTN/DRKS/ChiCTR**：`ct_registry.py` 新增 `_run_coze_detail` / `_run_coze_autodetail`，从 `norm_inputs` 反推实际检索到的 Coze 源（`--ictrp/--isrctn/--drks/--chictr`），复用列表 `project_list_raw` 走统一端点 detail（与列表同 `demand_id` 去重只计 1 次配额）；沿用 >100 条护栏与 `--auto-confirm`；**detail 空返回/超时时降级保留列表**（绝不拿空详情盖掉好列表）并提示后端缺口。
- **⚠️ Coze 后端依赖（需知）**：WHO detail 后端已实现（`who_scrape_details_node`）；**ISRCTN/DRKS/ChiCTR 的 detail 后端未实现**（coze 工作流源码 detail 路由仅覆盖 chinadrugtrials + who，见 `coze/src_backup/AGENTS.md`）——本地已就绪并降级兜底，若要真拿到这三源详情，需在 Coze 平台扩展工作流（新增 isrctn/drks/chictr detail 节点）后重新导出。
- **Coze 本地备份同步扩展（目标态）**：`coze/src_backup/graphs/nodes/` 新增 `isrctn_scrape_details_node.py` / `drks_scrape_details_node.py` / `chictr_scrape_details_node.py`（镜像 WHO 节点的线程/事件循环/Playwright 机制，`_extract_id` 多键容错，解析器 JSON-LD/表格/分节文本兜底）；`scrape_details_node.py` 路由补三源分支；`coze/src_backup/AGENTS.md` 与 `coze/README.md` 同步更新（源表、节点清单、"目标态"标注）；新增 `coze/DETAIL_EXTENSION_PLAN.md`（Coze 平台操作清单：新增节点→改路由→重部署→回归验收）。**线上工作流尚未含三源详情，需按清单在 Coze 平台操作后重新导出、再更新本归档。**
- **Coze v2 导出已落地并同步归档（2026-08-12 15:00）**：用户按清单在 Coze 平台补完三源 detail 节点，新导出 `project_20260812_150019.tar.gz` 已替换 `coze/src_backup/`（新 `src/` 布局）。核对结论：三节点与本地版本**零差异**、路由已接、`GlobalState.source` 扩五源；另发现新增**飞书写入节点**（`feishu_write_node.py`，search/detail 后触发，缺凭据有 except 兜底）。
- **⚠️ 新发现：三源 SEARCH 后端未实现（老缺口）**：`search_node.py` 仅 who/chinadrugtrials 两源路由，`isrctn/drks/chictr` 的 search 请求静默落入 CDE 抓取分支（旧备份同样如此，非回归）→ 三源「列表→详情」链条断裂（列表为 CDE 形状，ID 非各源真实编号，detail 必然失败；本地 `_run_coze_detail` 空返回降级、不污染数据）。下一轮需补三源 search 节点（方案已写入 `DETAIL_EXTENSION_PLAN.md` 附录）。
- **三源 SEARCH 节点已实现（目标态，待 Coze 平台落地）**：`coze/src_backup/src/graphs/nodes/` 新增 `isrctn_search_node.py` / `drks_search_node.py` / `chictr_search_node.py`（镜像 WHO 机制：线程/事件循环/Playwright 反爬、逐页抓取去重、240s 总时间预算、多关键字按 project_id 取交集；`project_id` 用各源真实编号并写 `isrctn`/`drks_id`/`registry_id` 键，与详情节点 `_extract_id` 容错契约对齐）；`search_node.py` 已加三源 import+路由+docstring 扩五源；AGENTS.md / coze/README.md / DETAIL_EXTENSION_PLAN.md 同步更新。**需按清单在 Coze 平台导入三 search 节点并重新导出后，三源「列表→详情」全链才通。**
- **三源真实页面案例测试（2026-08-12 15:2x，不触 Coze 端点）**：用 requests 抓真实注册库页面跑解析器——
  - **ISRCTN ✅ 全链验证通过**：搜索解析 10 条真实编号（`?q=` 参数，`?query=` 会 400）+ 总数 4300 + 详情 36 字段（name/ISRCTN/Sponsor/Phase 等）。发现并修复：`_build_search_url` 由 `?query=` 改 `?q=`；`_extract_total` 增加 `N results` 匹配。该站有 CHK cookie 挑战（Playwright 天然可过）。
  - **ChiCTR ⚠️ 需 Playwright 复验**：入口由 `searchproj.aspx`（404）改为 `searchproj.html`；该页带 **acw_sc__v2 JS 反爬（阿里云 WAF）**，本地 requests 无法直达，部署节点用 Playwright 执行 JS 可过——解析器待部署后对照真实结果页验证。
  - **DRKS ❌ 无可用 GET 搜索**：`/search/de/trial` 404，`navigate.php?navigation_id=trialsearch` 只回 BfArM 门户壳。真实检索需 **ASP.NET 表单流程（GET 搜索页→填查询框→POST→__doPostBack 翻页，同 who_search_node 模式）**——已标注为占位实现，部署前需移植 WHO 表单方案。
  - 注：三源均属 WHO 覆盖的备用源（WHO 正常时跳过），DRKS 表单移植的优先级可据此评估。
- **README 文献下载耗时/规模警示（2026-08-12 实测）**：在 `README.md` 与 `README_zh-CN.md` 的「确认门 PDF 下载」节后新增 ⚠️ 警示框。依据：读 `scripts/download_docs.py` 确认其为**严格顺序、单文件 60s 超时、无数量上限、无重试循环、略过已存在文件**；沙箱实测 EU 基础设施往返延迟 ≈1–3s/请求、沙箱出网限速 ~20–30 KB/s（大文档会撞 60s 超时被跳过，明确标注为沙箱限速、非生产真实值）。给出最坏耗时公式 `文件数×60s` 与缓解措施（`fetch_eu_ctr_docs.py --max N`、分批、续传、`--timeout` 调大）。同步修正 `download_docs.py` docstring 中"per-file retries"为"no retry loop"，与代码一致。
- **DRKS 暂搁置（用户决策 2026-08-12）**：真实页面实测 DRKS 检索无可用 GET URL（ASP.NET 表单框架），本地 `drks_search_node.py` 保留占位、`search_node.py` 的 drks 分支保留（返回空列表，ct-registry 侧空返回降级兜底、不污染数据）；落地时只导入 isrctn_search / chictr_search 两节点。恢复条件见 `DETAIL_EXTENSION_PLAN.md` 附录。
- **新增 `coze/MODIFICATION_GUIDE.md`（Coze 工作流修改详细指南）**：面向 Coze 平台操作者的完整手册——当前状态一览（5 源 × 检索/详情 × 状态）、本轮操作步骤（导入 isrctn_search/chictr_search 节点 + search 路由代码段 + drks 分支二选一）、历史已完成项备查、导出与归档同步、回归验收清单、常见问题与回滚。
- **指南修订（用户反馈 JSON format error）**：Step 1 改为「在项目文件树新增 .py 文件」（勿把代码粘进 JSON 配置字段——Python 节点代码是文件不是 JSON 字段，v2 详情节点走的就是文件路径）；FAQ 新增 `JSON format error` 条目。
- **向后兼容**：省略 `--fetch-mode` 时沿用旧逻辑（`--mode detail` 或 `--project-list` 触发 detail，否则 search），不影响现有编排器与测试。
- 验证：`py_compile` 通过；dry-run 预览确认 list/detail/both 三路径 payload 正确构建；离线单测 `_read_project_list_raw` / `_read_record_count` / `_detail_out_path` / `_resolve_fetch_mode` / `_run_coze_detail` 降级（空返回/超时/>100 护栏）与 `_swap_norm_input` 全绿。

## 0.3.80 (2026-08-12) · CDE 独立端点正式退役 + 配额统一 100 + P1-4/6/7 修复

- **CDE 独立端点正式退役（RETIRED）**：`ct-searchcde.coze.site/run`（`CDE/search_cde_workflow.py`）于 2026-08-12 正式退役；`ct_registry.py --cde-legacy` 现为无操作警告，自动回退统一端点 `search_ictrp.py --source chinadrugtrials`。全仓文档（SKILL.md / README 双份 / AGENTS.md / cli_reference / sop / search_menu / units / CDE/README / CDE/cde_workflow）将「FALLBACK reference」统一改写为「RETIRED 2026-08-12」；CDE/ 目录保持本地归档、不随包发布。
- **配额统一为 100**：测试配额与正式配额统一 `DAILY_LIMIT = 100`（取代测试期临时 2000 与早期文档规划值 20），注释固化。
- **P1-4 WHO 宽词超时**：`search_ictrp.py` 在 WHO 纯关键词检索（无结构化字段过滤）时打印 BREADTH 预判提示，引导改用 `--mode combined` 字段级 AND 过滤或收窄关键词。
- **P1-6 WHO 无 PDF / download_docs 仅 EU-CTR**：无文档链接时打印 GUIDE，列出不提供 PDF 的来源（ICTRP/CDE/CTGOV/WHO）并引导跳官网，注明仅 EU-CTR 可自动拉取。
- **P1-7 并行会话并发崩溃**：`usage_guard.py` 新增 advisory 文件锁 `_with_lock`，串行化共享 `usage.json` 的 read-modify-write；补充并发约束说明（单技能单会话，或依赖锁）。
- **宽词体验修复（Tier-2 软警告 + 部分数据高亮）**：针对用户反馈"输入过宽词无警告、跑几分钟才说范围过宽/只返回部分数据"——`keyword_breadth.py` 新增 `is_soft_broad`（Tier-2 宽病类：糖尿病/高血压/哮喘/肥胖/抑郁等，仅整词匹配，**不碰子串/词根以杜绝误伤组合检索**）；`ct_registry.py` 的 `_guard_keyword_breadth` 对 Tier-2 软词改为「仅 WARN、不中止」（保留最泛伞词 cancer/肿瘤/治疗 等的硬 `sys.exit(2)`），新增 `--allow-broad` 静默开关；`search_ictrp.py` 的 BREADTH 预判提示**扩到全 source**（去掉 `source=="who"` 限制）并对软词触发；`_run_parallel` 子进程 `stdout` 实时透传（不再 `capture_output` 吞掉 BREADTH/PARTIAL 警告）；`_parse_response` 在 `total_available > 取回条数` 时打印醒目 `[PARTIAL]` 缺口警告。自测与 `py_compile` 通过。

## 0.3.78 (2026-08-09) · 归档废弃的独立 CDE Coze 端点：将 `search_cde_workflow.py` + `config/cde.dat` + `references/cde_workflow.md` 移入新建的 `CDE/` 目录（本地开发备查，不随包发布，`.gitignore`/`.clawhubignore` 已加 `CDE/` 排除）。生产路径统一走 `search_ictrp.py --source chinadrugtrials`（与 WHO 共用一枚 ictrp token），独立端点仅经 `ct_registry.py --cde-legacy` 兜底。同步修正全仓散布引用（SKILL.md / README 双份 / AGENTS.md / cli_reference / sop / search_menu / units / 测试 harness）指向 `CDE/`，并修复 2 处死链（`references/cde_workflow.md` → `CDE/cde_workflow.md`）；`CDE/search_cde_workflow.py` 内 `CONFIG_TOKEN_PATH` 改为脚本相对路径 + ARCHIVED 标注，新建 `CDE/README.md` 归档说明。
