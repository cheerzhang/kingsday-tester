# Kingsday Web MVP

## 1. 安装依赖

```bash
pip install fastapi uvicorn
```

## 2. 启动

在仓库根目录执行：

```bash
uvicorn webapp.server:app --reload
```

打开浏览器访问：

```text
http://127.0.0.1:8000
```

## 3. 已实现能力

- Web 端开局（角色勾选）
- 回合主流程：抽卡 / 不抽卡 / 跳过
- OR 抽卡费用选择
- 事件目标/围观选择
- 拍照、交易、供餐、表演、赠送、交换、志愿者帮助等交互分支
- 实时查看所有玩家资源与运行日志

## 4. API 概览

- `GET /api/roles` 角色列表
- `POST /api/game/start` 开局
- `POST /api/game/action` 执行动作
- `GET /api/game/state` 当前状态
- `POST /api/game/reset` 重置
