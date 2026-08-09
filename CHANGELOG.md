# Changelog

## 0.3.78 (2026-08-09) · 归档废弃的独立 CDE Coze 端点：将 `search_cde_workflow.py` + `config/cde.dat` + `references/cde_workflow.md` 移入新建的 `CDE/` 目录（本地开发备查，不随包发布，`.gitignore`/`.clawhubignore` 已加 `CDE/` 排除）。生产路径统一走 `search_ictrp.py --source chinadrugtrials`（与 WHO 共用一枚 ictrp token），独立端点仅经 `ct_registry.py --cde-legacy` 兜底。同步修正全仓散布引用（SKILL.md / README 双份 / AGENTS.md / cli_reference / sop / search_menu / units / 测试 harness）指向 `CDE/`，并修复 2 处死链（`references/cde_workflow.md` → `CDE/cde_workflow.md`）；`CDE/search_cde_workflow.py` 内 `CONFIG_TOKEN_PATH` 改为脚本相对路径 + ARCHIVED 标注，新建 `CDE/README.md` 归档说明。
