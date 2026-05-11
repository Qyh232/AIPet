# AIBuddy 🐾

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AIBuddy is a desktop virtual pet. It can move autonomously, has a multi-layer memory system, an emotion system, and interacts with users through AI-powered conversations. It can play games, remember your preferences, and supports custom pets with multiple outfits.

---

## 🌟 Features

### Autonomous Behaviors

* The pet can patrol randomly, occasionally nap, and change expressions according to its state.
* The AI can initiate conversations based on context to increase interactivity.
* Behaviors and speech are triggered automatically (LLM-based) to keep the pet lively.

### User Interaction

* Click the pet → Jump + Speak
* Drag the pet → Follow the mouse
* Chat → Streamed output + tool calls
* Switch pets → Each pet has independent memory and state

### Built-in Tools

* Idiom Game
* Calculator
* Fortune
* Guess Number
* Remember user info (name, preferences, etc.)

### Multi-layer Memory System

* **Working Memory**: Stores recent dialogues to maintain context (automatically records each conversation, max 50 entries, oldest entries are overwritten)
* **Episodic Memory**: Stores historical dialogues, supports semantic search (automatically records each conversation)

### Customizable

* Add custom pets and outfits
* Modify pet personality, name, and behaviors
* Supports multiple LLM APIs

---

## 🎬 Example Animations

![Example Animation 1](examples/1.png)
![Example Animation 2](examples/2.png)
![Example Animation 3](examples/3.png)
![Example Animation 4](examples/4.png)

---

## 💻 Installation (Windows)

### 1. Prerequisites

* Install Python 3.10 or higher and check "Add Python to PATH"
* Install Git (optional, recommended for updates)

### 2. Clone the repository

```bat
git clone https://github.com/your-username/AIBuddy.git
cd AIBuddy
```

### 3. Create virtual environment and install dependencies

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure API key

Edit the `.env` file:

```ini
LLM_BASE_URL = https://api.deepseek.com
LLM_API_KEY = sk-xxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL_ID = deepseek-chat
```

### 5. Start the pet

```bat
python -m ai_desktop_pet
```

> If you don’t have an API key, you can run in template mode:

```bat
python -m ai_desktop_pet --no-llm
```

---

## 🐾 Usage

| Action           | Effect                               |
| ---------------- | ------------------------------------ |
| Click the pet    | Jump + Speak                         |
| Drag the pet     | Move pet anywhere on the screen      |
| Type text        | Chat with the pet (requires LLM API) |
| Right-click menu | Switch pets, play games, exit        |

### Right-click Menu

* 🐾 Switch pets (independent memory and state)
* 🎮 Games
* Exit

### Pet Behavior Examples

* Patrols randomly about every 2 minutes
* AI initiates speech every 5 minutes (LLM mode)
* Remembers user name and preferences

---

## 🐶 Adding Custom Pets

AIBuddy supports custom pets and multiple outfits. You can assign different skins and animations to a pet. Steps:

### 1. Create Pet Folder

Create a uniquely named folder under `ai_desktop_pet/assets/sprites/`:

```
sprites/
└── mycat/                  ← Pet ID (English, unique)
    ├── meta.json           ← Animal registration file
    └── orange/             ← Outfit folder (English)
        ├── meta.json       ← Outfit configuration file
        ├── idle.png        ← Required
        ├── walk.png        ← Optional
        ├── jump.png        ← Optional
        └── ...             ← Other actions
```

> Each pet can have multiple outfits that can be switched in the right-click menu.

### 2. Prepare Animations

* PNG format, transparent background (RGBA)
* Each frame 64×64 px
* `idle.png` required; others optional, missing actions default to `idle`
* You can use AI or tools to generate fully prepared sprite sheets
* Example:

![Example Sprite](ai_desktop_pet/assets/sprites/tudog/yellow-and-white/celebrate.png)

### 3. Configure JSON

**Animal registration file:** `mycat/meta.json`

```json
{
  "animal_id": "mycat",
  "display_name": "My Cat",
  "outfits": ["orange"]
}
```

**Outfit configuration:** `mycat/orange/meta.json`

```json
{
  "outfit_id": "orange",
  "display_name": "Orange Cat",
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

> If an animation is missing, `idle` will be used as default.

### 4. Register Pet Breed

Add in `persona.py` `_BREED_MAP`:

```python
_BREED_MAP = {
    "mycat": "A proud orange cat"
}
```

### 5. Apply Changes

1. Save files and restart AIBuddy
2. Right-click → Switch Pet → My Cat → Choose outfit
3. The new pet will appear on the desktop and support all prepared animations

### ✅ Checklist

* [ ] PNG height = 64 px
* [ ] Each frame width = 64 px
* [ ] Frame content aligned consistently
* [ ] `frame_width` and `frame_height` in `meta.json` = 64
* [ ] `actions` frame count matches actual PNG frames
* [ ] Pet breed registered in `_BREED_MAP`
* [ ] Outfit list `outfits` matches folder names

---

## 🛠 Project Structure

```
AIBuddy/
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
└── start_pet.bat
```

---

## 🤝 Contributing

Welcome to submit Pull Requests or Issues

---

## 📜 License

MIT License © 2026
