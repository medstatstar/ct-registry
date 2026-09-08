# ct-registry 检索工作台（直接可运行版）

> 基于 ct-base 工作台标准配置框架搭建（`workbench_ui.md` §0–§13）：
> 配置驱动 + 标准 Chrome + 四区 IA + I18N 引擎 + `--wb-*` 令牌 + WBList 组件。
> 品牌预设 **clinical-teal**；本目录共享资产 `tokens.css` / `wb-list.css` / `wb-list.js`
> 均为 ct-base/workbench 原样拷贝（勿改源）。

## 文件

| 文件 | 作用 |
|---|---|
| `index.html` | **完全自包含**单文件前端（tokens.css / wb-list.css / wb-list.js 已内联，任意环境样式一致；标准 Chrome + 检索表单 + Landscape + 试验清单 + 运行记录；页内模态替代原生 alert/confirm——预览 iframe 中原生弹窗会被拦截） |
| `server.py` | stdlib `http.server` 后端：`/api/config · health · runs · task/<id> · download` + `POST /api/search`（线程内 Popen 调 `ct_registry.py`，含子进程编排与任务状态流） |
| `workbench.config.json` | 声明式配置（HTML 与后端共读；端口 `8790`） |
| `run_workbench.cmd` | Windows 一键启动 |
| `tokens.css` / `wb-list.css` / `wb-list.js` | ct-base 共享资产（vendor 副本；页面已内联，这些文件供后续 publish_inject 对照） |
| `runs/<task_id>/` | 每次检索的产物：`report.xlsx`、`normalized.json`、`report.md`、`agg.json`、`log.txt`、`meta.json` |

## 离线兜底

页面无后端 `/api`（如被静态托管/直开副本）时：顶栏状态 pill 显示"后端未连接"且 title 提示启动方法；
点击主按钮自动进入**离线演示**（内置示例数据渲染完整界面，顶部黄色横幅明示非真实数据）。
启动 `python server.py` 后强刷（Ctrl+Shift+R）即恢复真实检索。

## 启动

```bash
# 依赖 C:\Anaconda3\python.exe (requests/pandas/bs4/lxml)
python server.py            # 或双击 run_workbench.cmd；默认 http://127.0.0.1:8790
# 端口被占: 先杀旧进程; 改代码后必须重启 + Ctrl+Shift+R 强刷 (workbench_ui.md §7)
```

## 检索表单 → CLI 参数映射

| 表单 | 映射 | 说明 |
|---|---|---|
| 疾病/条件 | `--cond` | 同时作 CDE 中文关键字（可另填覆盖） |
| 干预/药物 | `--intr` | — |
| 申办方 | `--sponsor` | — |
| 招募状态 | `--status` | CT.gov 枚举 |
| 近 N 年 / 每库上限 | `--since-years` / `--max` | — |
| 注册库 chips | `--with-ictrp/-cde/-euctr/-chictr/-isrctn/-drks/-pubchem` | CT.gov 恒开直连 |
| 固定参数 | `--run --print-summary --no-expand --auto-confirm --allow-broad --keep-meta` | 非交互旁路关键词确认门；保留 md/json |

数据源均为公开注册库（B 级只读）；CDE/WHO 走统一端点（token 由
`ct-registry/adapters/endpoint_token.py` 内嵌），结果如实披露降级路径。

## 验证（已过）

- `py_compile server.py` ✓ · 内联 JS `node --check` ✓ · zh/en 键对齐(78) ✓
- HTTP 探测 `/` `/api/config` `/api/health` `/api/runs` 全 200 ✓
- 端到端真实检索：CT.gov `osimertinib` → 385 命中→5 条 → 归一化 → 聚合 → `report.xlsx`(68KB) → landscape 摘要 → 前端 rows ✓

## 下一迭代（待办）

1. 快照追踪区：接 `ct_registry.py --track / --diff`，WBList 呈现状态变更（RECRUITING≈ACTIVE… 同义归一不误报）
2. 主按钮标签自适应（§5.3：有无会话/NL 上下文）
3. 检索历史更多列（耗时 / 命中数）+ 收藏查询
4. bug-report 端点（ct-base §20.3，本地邮箱兜底）
5. 落地进技能目录 `ct-registry/workbench/` 时：tokens/wb-list 走 publish_inject 注入；`run_workbench.cmd` 指向技能脚本
