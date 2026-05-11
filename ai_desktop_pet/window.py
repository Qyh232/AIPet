from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QMenu,
    QPushButton, QApplication, QFileDialog, QLineEdit,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve
from PySide6.QtGui import QAction, QPixmap, QTransform
from .config import PetConfig
from .models import PetActionType, PetEmotion, PetEvent, PetEventType, PetState
from .skins import PetSkinManager


class BubbleLabel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("BubbleWidget")
        self.setStyleSheet(
            "#BubbleWidget { background: rgba(255,255,255,230); border-radius: 10px; }"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 6, 10, 8)
        self._layout.setSpacing(2)

        # 关闭按钮（右上角）
        self._close_btn = QPushButton("×", self)
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #999; font-size: 14px; border: none; }"
            "QPushButton:hover { color: #333; }"
        )
        self._close_btn.clicked.connect(self._on_close_clicked)
        self._close_btn.hide()

        # 文字标签
        self._label = QLabel(self)
        self._label.setWordWrap(False)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._label.setStyleSheet("background: transparent; color: #333; font-size: 13px;")
        self._layout.addWidget(self._label)

        self.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide)

        # 是否为用户聊天气泡（只能手动关闭）
        self._manual_close = False

        # Streaming state
        self._stream_timer = QTimer(self)
        self._stream_timer.timeout.connect(self._stream_tick)
        self._stream_chars: list[str] = []
        self._stream_pos = 0
        self._stream_displayed = ""

    def mousePressEvent(self, event):
        # 气泡区域的点击不传播到父窗口
        event.accept()

    def _on_close_clicked(self):
        self._on_hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._close_btn.move(self.width() - 22, 2)

    def _on_hide(self) -> None:
        self.hide()
        self._manual_close = False
        self._close_btn.hide()
        self._label.setWordWrap(False)
        self._label.setMinimumSize(0, 0)
        self._label.setMaximumSize(16777215, 16777215)
        self._label.setText("")
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        if self.parentWidget():
            self.parentWidget().adjustSize()

    def _fit_size(self) -> None:
        max_w = 280
        self._label.setWordWrap(False)
        self._label.setMinimumSize(0, 0)
        self._label.setMaximumSize(16777215, 16777215)
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._label.adjustSize()
        natural = self._label.sizeHint()
        pad_w = 24
        pad_h = 18
        w = natural.width() + pad_w
        h = natural.height() + pad_h
        if w <= max_w:
            self.setFixedSize(w, h)
        else:
            self._label.setWordWrap(True)
            self._label.setFixedWidth(max_w - pad_w)
            text_h = self._label.heightForWidth(max_w - pad_w)
            if text_h <= 0:
                text_h = 30
            self._label.setMinimumHeight(text_h)
            self.setFixedSize(max_w, text_h + pad_h)
        # 确保父窗口宽度不小于气泡宽度
        parent = self.parentWidget()
        if parent:
            if self.width() > parent.width():
                parent.setFixedWidth(self.width())
            parent.adjustSize()

    def show_text(self, text: str, ms: int = 5000, manual_close: bool = False) -> None:
        self._stop_stream()
        self._manual_close = manual_close
        self._label.setText(text)
        self._fit_size()
        self._close_btn.show()
        self.show()
        if manual_close:
            self._hide_timer.stop()
        else:
            self._hide_timer.start(ms)

    def stream_text(self, text: str, char_interval_ms: int = 40) -> None:
        self._stop_stream()
        self._hide_timer.stop()
        self._manual_close = True
        self._stream_chars = list(text)
        self._stream_pos = 0
        self._stream_displayed = ""
        self._label.setText("")
        self._close_btn.show()
        self.show()
        self._stream_timer.start(char_interval_ms)

    def append_stream_text(self, chunk: str) -> None:
        self._hide_timer.stop()
        self._manual_close = True
        self._stream_displayed += chunk
        self._label.setText(self._stream_displayed)
        self._fit_size()
        self._close_btn.show()
        self.show()

    def finish_stream(self, hide_after_ms: int = 8000) -> None:
        self._stop_stream()
        # 用户聊天的回复：只能手动关闭
        if self._manual_close:
            return
        self._hide_timer.start(hide_after_ms)

    def _stream_tick(self) -> None:
        if self._stream_pos >= len(self._stream_chars):
            self._stream_timer.stop()
            if not self._manual_close:
                self._hide_timer.start(8000)
            return
        self._stream_displayed += self._stream_chars[self._stream_pos]
        self._stream_pos += 1
        self._label.setText(self._stream_displayed)
        self._fit_size()

    def _stop_stream(self) -> None:
        self._stream_timer.stop()
        self._stream_chars = []
        self._stream_pos = 0
        self._stream_displayed = ""


class PetWindow(QWidget):
    def __init__(self, config: PetConfig, state: PetState,
                 skin_manager: PetSkinManager, event_callback,
                 memory_manager=None):
        super().__init__()
        self.config = config
        self.state = state
        self.skin_manager = skin_manager
        self.event_callback = event_callback
        self._memory_manager = memory_manager

        self._drag_pos: QPoint | None = None
        self._click_count = 0

        # sprite animation state
        self._sprite_frames: list[QPixmap] = []
        self._sprite_frame_idx = 0
        self._sprite_flip = False
        self._sprite_timer = QTimer(self)
        self._sprite_timer.timeout.connect(self._next_sprite_frame)

        self._setup_window()
        self._setup_ui()

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(self.config.window_width)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.config.window_width - 40,
                  screen.height() - self.config.window_height - 130)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 气泡放在 layout 中，隐藏时不占空间
        self.bubble = BubbleLabel(self)
        self.bubble.hide()
        sp = self.bubble.sizePolicy()
        sp.setRetainSizeWhenHidden(False)
        self.bubble.setSizePolicy(sp)
        layout.addWidget(self.bubble, 0, Qt.AlignCenter)

        self.face_label = QLabel(self)
        self.face_label.setAlignment(Qt.AlignCenter)
        self.face_label.setFixedSize(self.config.window_width, self.config.window_height)
        layout.addWidget(self.face_label)

        # 常驻输入框
        self.chat_input = QLineEdit(self)
        self.chat_input.setPlaceholderText("和我说话…")
        self.chat_input.setStyleSheet(
            "background: rgba(255,255,255,200); border-radius: 8px; padding: 2px 6px;"
            "color: #333; font-size: 11px; border: 1px solid rgba(0,0,0,30);"
        )
        self.chat_input.setFixedHeight(24)
        self.chat_input.setMaximumWidth(140)
        self.chat_input.returnPressed.connect(self._on_chat_input)
        self.chat_input.hide()
        layout.addWidget(self.chat_input)

        self.update_pet_face(self.state.emotion, self.state.skin)

    # ── public API ──────────────────────────────────────────────────────────

    def update_pet_face(self, emotion: PetEmotion | str, skin_id: str) -> None:
        self._show_sprite(emotion, skin_id)

    def show_bubble(self, text: str) -> None:
        self.bubble.show_text(text)

    def show_bubble_stream(self, text: str) -> None:
        """逐字显示文本（打字机效果）。"""
        self.bubble.stream_text(text)

    def append_bubble_chunk(self, chunk: str) -> None:
        """追加一个流式 token 到气泡。"""
        self.bubble.append_stream_text(chunk)

    def finish_bubble_stream(self) -> None:
        """通知气泡流式结束，启动自动隐藏。"""
        self.bubble.finish_stream()

    def perform_action(self, action: PetActionType | str) -> None:
        a = action.value if isinstance(action, PetActionType) else action
        action_enum = action if isinstance(action, PetActionType) else PetActionType(a)

        if a == "jump":
            self._animate_jump()
        elif a == "move_left":
            self._animate_walk(-120, action_enum)
        elif a == "move_right":
            self._animate_walk(120, action_enum)
        elif a == "celebrate":
            self._animate_celebrate()
        elif a == "sleep":
            self.update_pet_face(PetEmotion.SLEEPY, self.state.skin)

    # ── sprite rendering ─────────────────────────────────────────────────

    def _show_sprite(self, emotion: PetEmotion | str, skin_id: str) -> None:
        outfit = self.skin_manager.get_outfit(skin_id)
        if not outfit:
            return
        action_name = outfit.get_action_name(emotion)
        sheet = outfit.get_sheet(action_name)
        if not sheet or not sheet.frames:
            return
        self._sprite_frames = sheet.frames
        self._sprite_frame_idx = 0
        self._sprite_flip = False
        self._set_sprite_pixmap(self._sprite_frames[0])
        interval = max(50, 1000 // outfit.fps)
        self._sprite_timer.start(interval)

    def _play_sprite_action(self, action_type: PetActionType) -> None:
        outfit = self.skin_manager.get_outfit(self.state.skin)
        if not outfit:
            return
        from .sprite_manager import _ACTION_MAP
        action_name = _ACTION_MAP.get(action_type, "idle")
        sheet = outfit.get_sheet(action_name)
        if not sheet or not sheet.frames:
            return
        self._sprite_frames = sheet.frames
        self._sprite_frame_idx = 0
        self._sprite_flip = (action_type is PetActionType.MOVE_LEFT)
        self._set_sprite_pixmap(self._sprite_frames[0])
        interval = max(50, 1000 // outfit.fps)
        self._sprite_timer.start(interval)

    def _next_sprite_frame(self) -> None:
        if not self._sprite_frames:
            return
        self._sprite_frame_idx = (self._sprite_frame_idx + 1) % len(self._sprite_frames)
        self._set_sprite_pixmap(self._sprite_frames[self._sprite_frame_idx])

    def _set_sprite_pixmap(self, pixmap: QPixmap) -> None:
        if self._sprite_flip:
            pixmap = pixmap.transformed(QTransform().scale(-1, 1))
        self.face_label.setPixmap(pixmap)
        self.face_label.setText("")

    def _stop_sprite_anim(self) -> None:
        self._sprite_timer.stop()
        self._sprite_frames = []
        self.face_label.setPixmap(QPixmap())

    # ── position animations ──────────────────────────────────────────────

    def _animate_jump(self) -> None:
        start = self.pos()
        up = QPoint(start.x(), start.y() - 30)
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(400)
        anim.setKeyValueAt(0, start)
        anim.setKeyValueAt(0.5, up)
        anim.setKeyValueAt(1, start)
        anim.setEasingCurve(QEasingCurve.OutBounce)
        anim.start()
        self._anim = anim

    def _animate_celebrate(self) -> None:
        start = self.pos()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(600)
        anim.setKeyValueAt(0, start)
        anim.setKeyValueAt(0.25, QPoint(start.x(), start.y() - 20))
        anim.setKeyValueAt(0.5, start)
        anim.setKeyValueAt(0.75, QPoint(start.x(), start.y() - 20))
        anim.setKeyValueAt(1, start)
        anim.start()
        self._anim = anim

    def _animate_walk(self, dx: int, action_enum: PetActionType) -> None:
        """平滑移动到目标位置，移动过程中播放 walk 动画，结束后回到 idle。"""
        screen = QApplication.primaryScreen().availableGeometry()
        start = self.pos()
        target_x = max(0, min(start.x() + dx, screen.width() - self.width()))
        target = QPoint(target_x, start.y())

        # 播放 walk 动画
        self._play_sprite_action(action_enum)

        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(abs(dx) * 8)  # 速度：8ms/px
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Linear)

        def _on_finished():
            # 移动结束，回到 idle 动画
            self._show_sprite(PetEmotion.IDLE, self.state.skin)

        anim.finished.connect(_on_finished)
        anim.start()
        self._anim = anim

    def _move_by(self, dx: int, dy: int) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        new_x = max(0, min(self.x() + dx, screen.width() - self.width()))
        new_y = max(0, min(self.y() + dy, screen.height() - self.height()))
        self.move(new_x, new_y)

    # ── mouse events ────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()  # 记录按下位置
            if self.chat_input.isHidden():
                self.chat_input.show()
                self.chat_input.setFocus()
                self.adjustSize()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            screen = QApplication.primaryScreen().availableGeometry()
            new_pos.setX(max(0, min(new_pos.x(), screen.width() - self.width())))
            new_pos.setY(max(0, min(new_pos.y(), screen.height() - self.height())))
            self.move(new_pos)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_pos is not None:
            end = self.pos()
            release_pos = event.globalPosition().toPoint()
            moved = (release_pos - self._press_pos).manhattanLength() > 5
            self._drag_pos = None
            if moved:
                self.event_callback(PetEvent(
                    type=PetEventType.USER_DRAGGED, source="window",
                    payload={"to": {"x": end.x(), "y": end.y()}},
                ))
            else:
                self._click_count += 1
                self.event_callback(PetEvent(
                    type=PetEventType.USER_CLICKED, source="window",
                    payload={"click_count": self._click_count},
                ))

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        chat_action = QAction("💬 聊天", self)
        chat_action.triggered.connect(self._toggle_chat_input)
        menu.addAction(chat_action)

        pet_menu = menu.addMenu("🐾 切换宠物")
        animals = self.skin_manager.list_animals()
        for animal_id, animal_name in animals.items():
            animal_sub = pet_menu.addMenu(animal_name)
            for skin_id, display_name in self.skin_manager.list_outfits(animal_id).items():
                act = QAction(display_name, self)
                act.triggered.connect(lambda checked=False, s=skin_id: self._switch_pet(s))
                animal_sub.addAction(act)

        game_menu = menu.addMenu("🎮 游戏")
        idiom_action = QAction("成语接龙", self)
        idiom_action.triggered.connect(self._start_idiom_chain)
        game_menu.addAction(idiom_action)
        guess_action = QAction("猜数字", self)
        guess_action.triggered.connect(self._start_guess_number)
        game_menu.addAction(guess_action)
        fortune_action = QAction("抽签", self)
        fortune_action.triggered.connect(self._start_fortune)
        game_menu.addAction(fortune_action)

        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())

    # ── menu handlers ────────────────────────────────────────────────────────

    def _toggle_chat_input(self) -> None:
        if self.chat_input.isHidden():
            self.chat_input.show()
            self.chat_input.setFocus()
        else:
            self.chat_input.hide()
        self.adjustSize()

    def _on_chat_input(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self.event_callback(PetEvent(
            type=PetEventType.USER_CHAT, source="window",
            payload={"text": text},
        ))

    def _open_chat(self) -> None:
        self._toggle_chat_input()

    def _switch_pet(self, pet_id: str) -> None:
        """切换宠物：更新外观 + 通知 app 切换状态文件（app.switch_pet 会触发开场白）。"""
        self.state.skin = pet_id
        self.update_pet_face(self.state.emotion, pet_id)
        app = getattr(self.event_callback, '__self__', None)
        if app and hasattr(app, 'switch_pet'):
            app.switch_pet(pet_id)

    def _change_skin(self, skin_id: str) -> None:
        self._switch_pet(skin_id)

    def _open_import_wizard(self) -> None:
        pass

    def _start_idiom_chain(self) -> None:
        if self.chat_input.isHidden():
            self.chat_input.show()
            self.adjustSize()
        self.event_callback(PetEvent(
            type=PetEventType.USER_CHAT, source="window",
            payload={"text": "我们来玩成语接龙吧！你先出一个成语"},
        ))

    def _start_guess_number(self) -> None:
        if self.chat_input.isHidden():
            self.chat_input.show()
            self.adjustSize()
        self.event_callback(PetEvent(
            type=PetEventType.USER_CHAT, source="window",
            payload={"text": "我们来玩猜数字吧"},
        ))

    def _start_fortune(self) -> None:
        self.event_callback(PetEvent(
            type=PetEventType.USER_CHAT, source="window",
            payload={"text": "帮我抽个签看看今天运势"},
        ))

    def _upload_document(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文档", "",
            "文档文件 (*.txt *.md *.pdf);;所有文件 (*)",
        )
        if not file_path:
            return

        self.bubble.show_text("正在学习文档…📖", 10000)

        import threading

        def _do_ingest():
            try:
                count = self._memory_manager.rag_pipeline.ingest_file(file_path)
                msg = f"学完啦！记住了{count}段内容～📚"
            except Exception as e:
                msg = f"学习失败了…{e}"
            QTimer.singleShot(0, lambda: self.bubble.show_text(msg, 4000))

        threading.Thread(target=_do_ingest, daemon=True).start()
