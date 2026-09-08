@echo off
REM ct-registry 检索工作台启动脚本 (Windows)
REM 依赖: python (PATH 中可用；含 requests/pandas/bs4/lxml)
REM 注: server.py 已内置相对路径解析 —— 技能目录经 CT_REGISTRY_SKILL 环境变量覆盖，
REM      缺省回退至脚本父目录；Python 解释器默认用 sys.executable (即本脚本调用的 python)。
cd /d "%~dp0"
python server.py
