# AIPet (桌面宠物) 🐾

⚠️ 本项目中文文档。
For English version, click here: [README.en.md](README.en.md)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AIPet 是一款桌面虚拟宠物程序。宠物可自主行动、拥有多层记忆、情绪系统，并通过智能对话与用户互动。它不仅可以玩游戏、记住你的偏好，还能支持自定义宠物和多种外观。

---

## 🌟 功能亮点

### 自主行为

* 宠物会自主巡逻、偶尔打瞌睡，并根据情况切换表情
* AI 会根据上下文主动说话，增加互动感
* 行为和发言由程序定时触发（LLM），确保宠物动态生动

### 用户互动

* 点击宠物 → 跳跃 + 对话
* 拖拽宠物 → 跟随鼠标
* 聊天对话 → 流式输出 + 工具调用
* 切换宠物 → 每只宠物独立记忆与状态

### 内置智能工具

* 成语接龙游戏
* 四则运算计算器
* 运势占卜
* 猜数字游戏
* 记住用户信息（名字、偏好等）

### 多层记忆系统

* **工作记忆**：存储最近对话，用于保持多轮对话的连贯性（每次对话自动写入，最多 50 条，超过最旧的自动覆盖）
* **情景记忆**：保存历史对话片段，可通过语义检索快速查找相关内容（每次对话自动写入）

### 高度可定制

* 添加自定义宠物和外观
* 修改宠物性格、名字、行为逻辑
* 支持多种 LLM API

---

## 🎬 示例动画

![示例动画 1](examples/1.png)
![示例动画 2](examples/2.png)
![示例动画 3](examples/3.png)
![示例动画 4](examples/4.png)

---

## 💻 安装指南（Windows）

### 1. 环境准备

* 安装 Python 3.10 及以上，并勾选 "Add Python to PATH"
* 安装 Git（可选，便于后续更新）

### 2. 克隆仓库

```bat
git clone https://github.com/你的用户名/AIPet.git
cd AIPet
```

### 3. 创建虚拟环境并安装依赖

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 配置 API 密钥

编辑 `.env` 文件：

```ini
LLM_BASE_URL = https://api.deepseek.com
LLM_API_KEY = sk-xxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL_ID = deepseek-chat
```

### 5. 启动宠物

```bat
python -m ai_desktop_pet
```

> 无 API 密钥可用纯模板模式：

```bat
python -m ai_desktop_pet --no-llm
```

---

## 🐾 使用方法

| 操作   | 效果                |
| ---- | ----------------- |
| 点击宠物 | 跳跃 + 对话           |
| 拖拽宠物 | 移动宠物到屏幕任意位置       |
| 输入文字 | 与宠物聊天（需要 LLM API） |
| 右键菜单 | 切换宠物、玩游戏等         |

### 右键菜单功能

* 🐾 切换宠物（独立记忆和状态）
* 🎮 游戏
* 退出程序

### 宠物行为示例

* 每约 2 分钟随机巡逻一次
* 每 5 分钟 AI 主动发言（LLM 模式）
* 宠物记住你名字和偏好

---

## 🐶 添加自定义宠物

AIPet 支持导入自定义宠物及多种外观（outfit），你可以给宠物不同皮肤和动作动画。以下为详细步骤：

### 1. 创建宠物文件夹

在 `ai_desktop_pet/assets/sprites/` 下创建英文命名且唯一的文件夹，例如：

```
sprites/
└── mycat/                  ← 宠物 ID（英文，唯一）
    ├── meta.json           ← 动物注册文件
    └── orange/             ← 外观文件夹（outfit，英文）
        ├── meta.json       ← 外观配置文件
        ├── idle.png        ← 必须
        ├── walk.png        ← 可选
        ├── jump.png        ← 可选
        └── ...             ← 其他动画
```

> 每只宠物可以有多个外观（outfit），用户可在右键菜单中切换。

### 2. 准备动画

* PNG 格式，透明背景（RGBA）
* 每帧尺寸 64×64 px
* `idle.png` 必须，其余动作可选，缺失动作会自动用 `idle` 替代
* 可使用 AI 或工具生成已准备好的动画精灵图
* 示例：

![示例精灵图](ai_desktop_pet/assets/sprites/tudog/yellow-and-white/celebrate.png)

### 3. 配置 JSON

**动物注册文件：** `mycat/meta.json`

```json
{
  "animal_id": "mycat",
  "display_name": "我的猫咪",
  "outfits": ["orange"]
}
```

**外观配置文件：** `mycat/orange/meta.json`

```json
{
  "outfit_id": "orange",
  "display_name": "橘猫",
  "frame_width": 64,
  "frame_height": 64,
  "scale": 2,
  "fps": 6,
  "actions": {
    "idle": {"file": "idle.png", "frames": 4},
    "walk": {"file": "walk.png", "frames": 6},
    "jump": {"file": "jump.png", "frames": 4}
  },
  "emotion_to_action": {
    "idle": "idle",
    "happy": "celebrate",
    "sleepy": "sleep",
    "playing": "walk",
    "surprised": "jump",
    "sad": "sad",
    "angry": "angry",
    "hungry": "hungry",
    "excited": "excited"
  }
}
```

> 如果某个动画未准备，将使用 `idle` 作为默认。

### 4. 注册宠物品种

在 `persona.py` `_BREED_MAP` 添加：

```python
_BREED_MAP = {
    "mycat": "一只傲娇的橘猫"
}
```

### 5. 生效方法

1. 保存文件后重启 AIPet
2. 右键 → **切换宠物** → 我的猫咪 → 选择外观
3. 新宠物即可在桌面出现，并支持所有准备好的动画

### ✅ 检查清单

* [ ] PNG 高度 = 64 px
* [ ] 每帧宽度 = 64 px
* [ ] 各帧主体大小一致
* [ ] `meta.json` 中 `frame_width` 和 `frame_height` = 64
* [ ] `actions` 帧数与实际 PNG 帧数一致
* [ ] `_BREED_MAP` 已注册宠物品种
* [ ] 外观列表 `outfits` 与文件夹名一致

---

## 🛠 项目结构

```
AIPet/
├── ai_desktop_pet/
│   ├── assets/
│   ├── app.py
│   ├── action_engine.py
│   ├── agent_tools.py
│   ├── pet_state.py
│   └── window.py
├── my_agent/
│   └── memory/
├── data/
├── .env
├── requirements.txt
└── 启动宠物.bat
```

---

## 🤝 贡献

欢迎提交 Pull Request 或 Issues

---

## 📜 许可

MIT License © 2026
