# Changelog

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
- **coze 端（`adapters/coze/ICTRP_CDE/projects/src/` 本地基准，待重新部署生效）**：`search_node` / `who_search_node` / `scrape_details_node` 移除"缺失时自动生成"兜底，改为**缺来源告警 + 保留空值**（飞书表该行 query_origin 为空，暴露不合规调用）；`state.py` 8 处 `query_origin` 字段描述全部对齐新语义；`_compute_query_origin` 定义保留仅供客户端参照。
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
