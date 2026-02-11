# JS 全量迁移进度

## 目标

将现有 Python 项目完整迁移到 JavaScript，保证规则行为与当前版本一致。

## 已完成（第 1 阶段）

已新增 JS 引擎目录：`jsapp/engine/`

- `jsapp/engine/gameLogic.js`
  - 运行时初始化
  - 角色读取
  - 运行时状态读写
  - 重置逻辑
- `jsapp/engine/coreLogic.js`
  - 抽卡费用校验
  - 费用扣除
  - 抽卡配置解析
  - 胜率统计更新
- `jsapp/engine/victoryChecks.js`
  - 各角色胜利条件函数
  - 胜利函数注册表

以上三个模块为对 `pyapp/game_logic.py`、`pyapp/core_logic.py`、`pyapp/victory_checks.py` 的 JS 对齐版。

## 下一步（第 2 阶段）

- 迁移 `pyapp/event_effects.py` 到 `jsapp/engine/eventEffects.js`
- 迁移 `pyapp/game_flow.py` 到 `jsapp/engine/gameFlow.js`
- 迁移 API 层到 Node（替换 `webapp/server.py`）
- 增加“Python vs JS”对比回归测试，确保每个动作路径输出一致

## 说明

当前仓库中 Python 版本仍保留，作为迁移期行为基准。

## 纯前端效果预览

- 文件：`jsapp/demo.html`
- 说明：单文件原生 JS Demo，无需后端，直接浏览器打开即可看环形布局、中央事件区、底部日志和手动/自动模式切换。
