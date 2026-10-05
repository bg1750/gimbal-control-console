# Pan-Tilt Gimbal Control Console.
# Operator console for a two-axis camera platform, running against the
# built-in simulator so it works with no hardware.

import os
import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QMenuBar, QMessageBox, QWidget, QGroupBox, QSizePolicy,
    QSplitter, QLineEdit, QDialog, QFormLayout, QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import (
    QKeySequence, QAction, QColor, QDoubleValidator, QPixmap, QPalette, QBrush,
    QPainter,
)
from PyQt6.QtCore import Qt, QTimer

HERE = os.path.dirname(os.path.abspath(__file__))

from simulator import GimbalSimulator
from widgets import AttitudeIndicator, HeadingCompass

VERSION = "1.0"

# Crawler-GUI colorway.
SAGE = "#809c9a"
OLIVE = "#8e9775"
MAUVE = "#776274"
MAGENTA = "#995986"
TAUPE = "#978a84"
SANDSTONE = "#d6cfc4"
PLUM = "#5d3a4a"
PLUM_DK = "#4b2c3f"
HOVER = "#b9b1a9"
DARK_TEXT = "#2f2f2f"


class GimbalConsole(QMainWindow):
    # Labels for the status lights.
    SUBSYSTEM_LABELS = {
        "controller": "Controller",
        "input_device": "Input Device",
        "drive_power": "Drive Power",
        "pan_motor": "Pan Motor",
        "tilt_motor": "Tilt Motor",
    }

    def __init__(self):
        super().__init__()

        self.device = GimbalSimulator()

        self.indicators = {}
        self.indicator_is_red = {name: True for name in self.device.SUBSYSTEMS}
        self._blink_on = False

        self.estopped = False
        self.estop_flash_state = False

        self.setWindowTitle(f"Gimbal Control Console  v{VERSION}")
        self.setGeometry(120, 90, 1500, 880)

        self._build_stylesheets()
        self._init_ui()

        # Advance the sim and repaint ~20x/sec.
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._tick)
        self.update_timer.start(50)

        # Blink offline status lights.
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._blink_indicators)
        self.blink_timer.start(500)

        self.estop_flash_timer = QTimer(self)
        self.estop_flash_timer.timeout.connect(self._toggle_estop_flash)

        # Bring the platform online on launch.
        self._connect_all()

    # --- styling ---
    def _build_stylesheets(self):
        self.panel_style = """
            QGroupBox {
                background: transparent;
                border: 1px solid white;
                border-radius: 6px;
                margin-top: 10px;
                padding: 10px;
                font-size: 16px;
                font-weight: 700;
                color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 6px;
                color: white;
            }
        """
        self.status_box_style = f"""
            QGroupBox {{
                background-color: {TAUPE};
                border: 1px solid gray;
                border-radius: 5px;
                margin-top: 10px;
                padding: 16px;
                font-size: 16px;
                font-weight: bold;
                color: #000;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 4px;
                color: white;
            }}
        """
        self.textbox_style = f"""
            QLineEdit {{
                background-color: {SANDSTONE};
                color: #333;
                border: 1px solid {PLUM};
                border-radius: 6px;
                padding: 6px;
                font-size: 16px;
            }}
        """
        self.estop_label_base = """
            QLabel {
                color: red;
                font-size: 22px;
                font-weight: 800;
                border-radius: 6px;
                padding: 6px;
                background-color: %s;
                qproperty-alignment: AlignCenter;
            }
        """

    def _readout_style(self, bg):
        return f"""
            QLabel {{
                background-color: {bg};
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 18px;
                font-weight: 600;
                color: {DARK_TEXT};
                font-family: "Segoe UI", "Helvetica Neue", sans-serif;
                qproperty-alignment: AlignCenter;
            }}
        """

    def _button_style(self, top, border=PLUM):
        return f"""
            QPushButton {{
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                  stop:0 {top}, stop:1 #ffffff);
                border: 1px solid {border};
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 16px;
                font-weight: 600;
                color: black;
            }}
            QPushButton:hover   {{ background-color: {HOVER}; }}
            QPushButton:pressed {{ background-color: {top}; border-style: inset; }}
            QPushButton:disabled{{ color: #777; background-color: #cfc8bf; }}
        """

    def _apply_shadow(self, widget, blur=18, color=(63, 63, 63, 180)):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setOffset(3, 3)
        shadow.setColor(QColor(*color))
        widget.setGraphicsEffect(shadow)

    # --- window ---
    def _init_ui(self):
        # Warm gradient background, dimmed when the window isn't focused.
        bg = QPixmap(os.path.join(HERE, "assets", "background.jpg")).scaled(
            self.width(), self.height() + 100,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        active_bg = QPixmap(bg)
        inactive_bg = QPixmap(bg)
        painter = QPainter(inactive_bg)
        painter.fillRect(inactive_bg.rect(), QColor(0, 0, 0, 100))
        painter.end()
        palette = QPalette()
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QBrush(active_bg))
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QBrush(inactive_bg))
        self.setPalette(palette)

        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        menu_bar = QMenuBar(self)
        menu_bar.setStyleSheet(
            f"QMenuBar {{ background:{TAUPE}; color:#000; }}"
            f"QMenuBar::item:selected {{ background:{MAUVE}; color:white; }}"
            "QMenu { background:#e7e1d8; color:#000; }"
            f"QMenu::item:selected {{ background:{MAUVE}; color:white; }}"
        )
        self.setMenuBar(menu_bar)
        self._setup_file_menu(menu_bar)
        self._setup_settings_menu(menu_bar)
        self._setup_view_menu(menu_bar)
        self._setup_help_menu(menu_bar)

        control_group = QGroupBox("Control")
        control_group.setStyleSheet(self.panel_style)
        live_group = QGroupBox("Live View")
        live_group.setStyleSheet(self.panel_style)

        self.control_layout = QVBoxLayout()
        self.control_layout.setSpacing(12)
        self.live_layout = QVBoxLayout()
        control_group.setLayout(self.control_layout)
        live_group.setLayout(self.live_layout)

        control_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        live_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(control_group)
        self.splitter.addWidget(live_group)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([460, 940])
        root.addWidget(self.splitter)

        self._setup_status_indicators(self.control_layout)
        self._setup_speed_controls(self.control_layout)
        self._setup_pan_controls(self.control_layout)
        self._setup_tilt_controls(self.control_layout)
        self._setup_zoom_controls(self.control_layout)
        self.control_layout.addStretch(1)
        self._setup_estop(self.control_layout)

        self._setup_live_view(self.live_layout)

        self._default_splitter_sizes = self.splitter.sizes()

    # --- menus ---
    def _setup_file_menu(self, menu_bar):
        file_menu = menu_bar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _setup_settings_menu(self, menu_bar):
        settings = menu_bar.addMenu("Settings")
        connect_all = QAction("Connect All Subsystems", self)
        connect_all.setShortcut(QKeySequence(Qt.Key.Key_F1))
        connect_all.triggered.connect(self._connect_all)
        settings.addAction(connect_all)

        disconnect_all = QAction("Disconnect All Subsystems", self)
        disconnect_all.setShortcut(QKeySequence(Qt.Key.Key_F2))
        disconnect_all.triggered.connect(self._disconnect_all)
        settings.addAction(disconnect_all)
        settings.addSeparator()

        home_tilt = QAction("Home Tilt Axis", self)
        home_tilt.triggered.connect(self._home_tilt)
        settings.addAction(home_tilt)

        home_zoom = QAction("Home Zoom Stage", self)
        home_zoom.triggered.connect(self._home_zoom)
        settings.addAction(home_zoom)

    def _setup_view_menu(self, menu_bar):
        view = menu_bar.addMenu("View")
        fullscreen = QAction("Fullscreen", self)
        fullscreen.setShortcut(QKeySequence(Qt.Key.Key_F11))
        fullscreen.triggered.connect(self._toggle_fullscreen)
        view.addAction(fullscreen)

        reset = QAction("Reset View", self)
        reset.setShortcut(QKeySequence(Qt.Key.Key_F9))
        reset.triggered.connect(self._reset_view)
        view.addAction(reset)

    def _setup_help_menu(self, menu_bar):
        help_menu = menu_bar.addMenu("Help")
        about = QAction("About", self)
        about.setShortcut(QKeySequence(Qt.Key.Key_F5))
        about.triggered.connect(self._open_about)
        help_menu.addAction(about)
        help_menu.addSeparator()
        debug = QAction("Debug Menu...", self)
        debug.triggered.connect(self._open_debug)
        help_menu.addAction(debug)

    # --- status lights ---
    def _setup_status_indicators(self, layout):
        box = QGroupBox("Connection Status")
        box.setStyleSheet(self.status_box_style)
        self._apply_shadow(box, blur=14, color=(0, 0, 0, 180))
        grid = QGridLayout()
        grid.setVerticalSpacing(8)

        for row, name in enumerate(self.device.SUBSYSTEMS):
            label = QLabel(self.SUBSYSTEM_LABELS[name] + ":")
            label.setStyleSheet("color:#000; font-weight:600;")
            indicator = self._create_status_indicator()
            self.indicators[name] = indicator
            grid.addWidget(label, row, 0)
            grid.addWidget(indicator, row, 1)

        box.setLayout(grid)
        layout.addWidget(box)

    def _create_status_indicator(self):
        dot = QLabel()
        dot.setFixedSize(26, 26)
        dot.setStyleSheet("background-color:red; border-radius:13px; border:3px solid black;")
        return dot

    def _set_indicator_green(self, name):
        self.indicators[name].setStyleSheet(
            "background-color:rgb(144,238,144); border-radius:13px; border:3px solid black;")
        self.indicator_is_red[name] = False

    def _set_indicator_red(self, name):
        self.indicators[name].setStyleSheet(
            "background-color:red; border-radius:13px; border:3px solid black;")
        self.indicator_is_red[name] = True

    def _set_indicator_blank(self, name):
        self.indicators[name].setStyleSheet(
            "background-color:gray; border-radius:13px; border:3px solid black;")

    # --- controls ---
    def _setup_speed_controls(self, layout):
        self.speed_label = QLabel("Slew Rate: HOLD")
        self.speed_label.setStyleSheet(self._readout_style(SAGE))
        self.speed_label.setFixedHeight(54)

        down = QPushButton("Rate Down")
        up = QPushButton("Rate Up")
        for b, fn in ((down, self._gear_down), (up, self._gear_up)):
            b.setStyleSheet(self._button_style(SAGE, PLUM_DK))
            self._apply_shadow(b)
            b.clicked.connect(fn)

        row = QHBoxLayout()
        row.addWidget(down)
        row.addWidget(up)

        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(self.speed_label)
        col.addLayout(row)
        layout.addLayout(col)

    def _setup_pan_controls(self, layout):
        self.pan_label = QLabel("Pan Heading: 000°")
        self.pan_label.setStyleSheet(self._readout_style(OLIVE))
        self.pan_label.setFixedHeight(54)

        left = QPushButton("◄ Pan CCW")
        right = QPushButton("Pan CW ►")
        for b in (left, right):
            b.setStyleSheet(self._button_style(OLIVE))
            self._apply_shadow(b)
        # Momentary: pan only while held.
        left.pressed.connect(lambda: self.device.nudge_pan(-1))
        left.released.connect(self.device.stop_pan)
        right.pressed.connect(lambda: self.device.nudge_pan(1))
        right.released.connect(self.device.stop_pan)

        row = QHBoxLayout()
        row.addWidget(left)
        row.addWidget(right)

        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(self.pan_label)
        col.addLayout(row)
        layout.addLayout(col)

    def _setup_tilt_controls(self, layout):
        self.tilt_label = QLabel("Tilt Angle: 0.0°")
        self.tilt_label.setStyleSheet(self._readout_style(MAUVE))
        self.tilt_label.setFixedHeight(54)

        self.tilt_textbox = QLineEdit()
        self.tilt_textbox.setStyleSheet(self.textbox_style)
        self.tilt_textbox.setPlaceholderText("Enter tilt angle  [0 to 90]")
        self.tilt_textbox.setValidator(QDoubleValidator(0.0, 90.0, 1))
        self.tilt_textbox.setFixedHeight(40)
        self.tilt_textbox.returnPressed.connect(self._set_tilt_angle)

        set_btn = QPushButton("Set Tilt Angle")
        set_btn.setStyleSheet(self._button_style(MAUVE))
        self._apply_shadow(set_btn)
        set_btn.clicked.connect(self._set_tilt_angle)

        row = QHBoxLayout()
        row.addWidget(self.tilt_textbox)
        row.addWidget(set_btn)

        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(self.tilt_label)
        col.addLayout(row)
        layout.addLayout(col)

    def _setup_zoom_controls(self, layout):
        self.zoom_label = QLabel("Zoom Stage: Retracted (0%)")
        self.zoom_label.setStyleSheet(self._readout_style(MAGENTA))
        self.zoom_label.setFixedHeight(54)

        self.zoom_btn = QPushButton("Extend / Retract Zoom")
        self.zoom_btn.setStyleSheet(self._button_style(MAGENTA))
        self._apply_shadow(self.zoom_btn)
        self.zoom_btn.clicked.connect(self._toggle_zoom)

        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(self.zoom_label)
        col.addWidget(self.zoom_btn)
        layout.addLayout(col)

    def _setup_estop(self, layout):
        self.estop_btn = QPushButton("EMERGENCY STOP")
        self.estop_btn.setFixedHeight(70)
        self.estop_btn.setStyleSheet("""
            QPushButton {
                background-color: rgb(196, 0, 0);
                border: 2px solid #ff8a8a;
                border-radius: 10px;
                color: white;
                font-size: 20px;
                font-weight: 900;
                letter-spacing: 2px;
            }
            QPushButton:hover   { background-color: #e01010; }
            QPushButton:pressed { background-color: #8a0000; }
            QPushButton:disabled{ background-color: #7a1414; color:#ffd7d7; }
        """)
        self._apply_shadow(self.estop_btn, blur=22, color=(196, 0, 0, 160))
        self.estop_btn.clicked.connect(self._engage_estop)

        self.estop_status_label = QLabel("E-STOP ENGAGED")
        self.estop_status_label.setStyleSheet(self.estop_label_base % "rgba(255,0,0,40)")
        self.estop_status_label.hide()

        self.reset_estop_btn = QPushButton("Reset E-Stop")
        self.reset_estop_btn.setStyleSheet(self._button_style(TAUPE))
        self._apply_shadow(self.reset_estop_btn)
        self.reset_estop_btn.clicked.connect(self._reset_estop)
        self.reset_estop_btn.hide()

        layout.addWidget(self.estop_status_label)
        layout.addWidget(self.estop_btn)
        layout.addWidget(self.reset_estop_btn)

    def _setup_live_view(self, layout):
        self.attitude = AttitudeIndicator()
        self.compass = HeadingCompass()

        gauges = QHBoxLayout()
        gauges.addWidget(self.attitude, stretch=3)
        gauges.addWidget(self.compass, stretch=2)
        layout.addLayout(gauges, stretch=1)

        readout_row = QHBoxLayout()
        self.pitch_readout = QLabel("Pitch: 0.0°")
        self.roll_readout = QLabel("Roll: 0.0°")
        for lbl in (self.pitch_readout, self.roll_readout):
            lbl.setStyleSheet(self._readout_style(OLIVE))
            lbl.setFixedHeight(50)
            readout_row.addWidget(lbl)
        layout.addLayout(readout_row)

    # --- update loop ---
    def _tick(self):
        self.device.step()

        self.attitude.set_attitude(self.device.pitch, self.device.roll)
        self.compass.set_heading(self.device.heading)
        self.pitch_readout.setText(f"Pitch: {self.device.pitch:+.1f}°")
        self.roll_readout.setText(f"Roll: {self.device.roll:+.1f}°")

        mode = self.device.speed_mode
        self.speed_label.setText("Slew Rate: HOLD" if mode == 0 else f"Slew Rate: {mode} / {self.device.MAX_SPEED_MODE}")
        self.pan_label.setText(f"Pan Heading: {int(self.device.heading):03d}°")
        self.tilt_label.setText(f"Tilt Angle: {self.device.tilt_angle:.1f}°")
        state = "Extended" if self.device.zoom_extended else "Retracted"
        if self.device.zoom_moving:
            state = "Moving"
        self.zoom_label.setText(f"Zoom Stage: {state} ({int(self.device.zoom_position)}%)")

        for name in self.device.SUBSYSTEMS:
            if self.device.is_connected(name) and self.indicator_is_red[name]:
                self._set_indicator_green(name)
            elif not self.device.is_connected(name) and not self.indicator_is_red[name]:
                self._set_indicator_red(name)

    def _blink_indicators(self):
        self._blink_on = not self._blink_on
        for name in self.device.SUBSYSTEMS:
            if not self.device.is_connected(name):
                if self._blink_on:
                    self._set_indicator_blank(name)
                else:
                    self._set_indicator_red(name)

    # --- command handlers ---
    def _connect_all(self):
        self.device.connect_all()

    def _disconnect_all(self):
        for name in self.device.SUBSYSTEMS:
            self.device.disconnect(name)

    def _gear_up(self):
        self.device.gear_up()

    def _gear_down(self):
        self.device.gear_down()

    def _set_tilt_angle(self):
        if self.estopped:
            QMessageBox.warning(self, "E-Stop Active", "Reset the emergency stop before commanding motion.")
            return
        if not self.device.is_connected("tilt_motor"):
            QMessageBox.critical(self, "Tilt Axis", "Tilt motor is offline. Connect subsystems first (Settings ▸ Connect All).")
            return
        text = self.tilt_textbox.text().strip()
        try:
            angle = float(text)
        except ValueError:
            QMessageBox.critical(self, "Invalid Entry", "Enter a numeric angle between 0° and 90°.")
            return
        if not (0.0 <= angle <= 90.0):
            QMessageBox.critical(self, "Out of Range", "Tilt angle must be between 0° and 90°.")
            return
        self.device.set_tilt_angle(angle)

    def _home_tilt(self):
        if self.estopped:
            QMessageBox.warning(self, "E-Stop Active", "Reset the emergency stop first.")
            return
        if not self.device.is_connected("tilt_motor"):
            QMessageBox.critical(self, "Tilt Axis", "Tilt motor is offline.")
            return
        self.device.home_tilt()

    def _toggle_zoom(self):
        if self.estopped:
            QMessageBox.warning(self, "E-Stop Active", "Reset the emergency stop first.")
            return
        if not self.device.toggle_zoom():
            QMessageBox.critical(self, "Zoom Stage", "Tilt motor is offline.")

    def _home_zoom(self):
        if self.estopped:
            QMessageBox.warning(self, "E-Stop Active", "Reset the emergency stop first.")
            return
        self.device.home_zoom()

    # --- emergency stop ---
    def _engage_estop(self):
        self.estopped = True
        self.device.engage_estop()
        self.estop_status_label.show()
        self.estop_flash_timer.start(500)
        self.estop_btn.setDisabled(True)
        self.reset_estop_btn.show()

    def _reset_estop(self):
        self.estopped = False
        self.device.reset_estop()
        self.estop_flash_timer.stop()
        self.estop_status_label.hide()
        self.estop_btn.setDisabled(False)
        self.reset_estop_btn.hide()

    def _toggle_estop_flash(self):
        shade = "rgba(255,0,0,90)" if self.estop_flash_state else "rgba(255,0,0,15)"
        self.estop_status_label.setStyleSheet(self.estop_label_base % shade)
        self.estop_flash_state = not self.estop_flash_state

    # --- view / help / debug ---
    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _reset_view(self):
        self.splitter.setSizes(self._default_splitter_sizes)

    def _open_about(self):
        QMessageBox.about(
            self, "About",
            f"<b>Pan-Tilt Gimbal Control Console</b> v{VERSION}<br><br>"
            "Operator console for a two-axis camera platform.<br>"
            "Runs against a built-in simulator — no hardware required.<br><br>"
            "Built with Python and PyQt6."
        )

    def _open_debug(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Debug Menu")
        dlg.setStyleSheet(f"QDialog {{ background:{TAUPE}; }} QLabel {{ color:#000; }}")
        form = QFormLayout(dlg)

        pitch_box = QLineEdit(); pitch_box.setStyleSheet(self.textbox_style)
        roll_box = QLineEdit(); roll_box.setStyleSheet(self.textbox_style)
        heading_box = QLineEdit(); heading_box.setStyleSheet(self.textbox_style)
        form.addRow("Force Pitch (°):", pitch_box)
        form.addRow("Force Roll (°):", roll_box)
        form.addRow("Force Heading (°):", heading_box)

        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(self._button_style(MAUVE))

        def apply():
            try:
                if pitch_box.text().strip():
                    self.device.pitch = float(pitch_box.text())
                    self.device._pitch_target = self.device.pitch
                if roll_box.text().strip():
                    self.device.roll = float(roll_box.text())
                    self.device._roll_target = self.device.roll
                if heading_box.text().strip():
                    self.device.heading = float(heading_box.text()) % 360.0
            except ValueError:
                QMessageBox.critical(dlg, "Invalid", "Enter numeric values.")
        apply_btn.clicked.connect(apply)
        form.addRow(apply_btn)
        dlg.exec()

    # --- shutdown ---
    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Confirm Exit", "Are you sure you want to quit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.update_timer.stop()
            self.blink_timer.stop()
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QLabel  { font-family: "Segoe UI", Arial, sans-serif; color:white; font-weight:bold; }
    """)
    window = GimbalConsole()

    # Headless smoke test: open, run briefly, exercise commands, exit 0.
    if "--selftest" in sys.argv:
        window.show()
        window._connect_all()
        window.device.set_speed_mode(3)
        window.device.set_tilt_angle(45)
        window.device.nudge_pan(1)
        window.device.toggle_zoom()
        for _ in range(40):
            window._tick()
            app.processEvents()
        window._engage_estop()
        window._tick()
        window._reset_estop()
        print("selftest OK: pitch=%.1f roll=%.1f heading=%.0f tilt=%.1f zoom=%.0f" % (
            window.device.pitch, window.device.roll, window.device.heading,
            window.device.tilt_angle, window.device.zoom_position))
        return 0

    if "--screenshot" in sys.argv:
        path = sys.argv[sys.argv.index("--screenshot") + 1]
        window.resize(1500, 880)
        window.show()
        window._connect_all()
        window.device.set_speed_mode(3)
        window.device.set_tilt_angle(52)
        window.device.toggle_zoom()
        window.device.heading = 48
        window.device.pitch = -7.5
        window.device.roll = 9.0
        for _ in range(30):
            window._tick()
            app.processEvents()
        window.grab().save(path)
        print(f"saved screenshot to {path}")
        return 0

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
