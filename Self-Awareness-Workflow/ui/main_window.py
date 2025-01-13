from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFrame, QGridLayout, QProgressBar)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QLinearGradient
from datetime import datetime
from system_controller import SystemController

class ModernFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModernFrame")
        self.setStyleSheet("""
            QFrame#ModernFrame {
                background-color: #ffffff;
                border-radius: 15px;
                border: 1px solid #e1e1e1;
            }
            QFrame#ModernFrame:hover {
                border: 1px solid #d0d0d0;
                background-color: #fafafa;
            }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


class StatusIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = QColor("#22c55e")  # Default green

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw outer circle (glow effect)
        painter.setPen(Qt.PenStyle.NoPen)
        glow = QColor(self._color)
        glow.setAlpha(50)
        painter.setBrush(glow)
        painter.drawEllipse(0, 0, 12, 12)

        # Draw inner circle
        painter.setBrush(self._color)
        painter.drawEllipse(2, 2, 8, 8)

    def set_status(self, status):
        if status == "normal":
            self._color = QColor("#22c55e")  # Green
        elif status == "warning":
            self._color = QColor("#eab308")  # Yellow
        else:
            self._color = QColor("#ef4444")  # Red
        self.update()


class ModernButton(QPushButton):
    def __init__(self, text, color="#3b82f6", parent=None):
        super().__init__(text, parent)
        self.base_color = color
        self._setup_style()

    def _setup_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.base_color};
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {self._darken_color(self.base_color)};
            }}
            QPushButton:pressed {{
                background-color: {self._darken_color(self.base_color, 20)};
            }}
        """)

    def _darken_color(self, hex_color, amount=10):
        color = QColor(hex_color)
        h, s, v, a = color.getHsv()
        return QColor.fromHsv(h, s, max(0, v - amount), a).name()


class ProgressRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 120)
        self._progress = 0

    def set_progress(self, value):
        self._progress = max(0, min(100, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw background circle
        pen_width = 8
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f3f4f6"))
        painter.drawEllipse(pen_width, pen_width,
                            self.width() - 2 * pen_width, self.height() - 2 * pen_width)

        # Draw progress arc
        pen = painter.pen()
        pen.setWidth(pen_width)
        pen.setColor(QColor("#3b82f6"))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        span = int(-self._progress * 360 / 100)
        painter.drawArc(pen_width, pen_width,
                        self.width() - 2 * pen_width, self.height() - 2 * pen_width,
                        90 * 16, span * 16)


class ModernCard(ModernFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setFont(QFont('Segoe UI', 14, QFont.Weight.DemiBold))
        header.addWidget(title_label)

        self.status_indicator = StatusIndicator()
        header.addWidget(self.status_indicator)
        header.addStretch()

        layout.addLayout(header)

        # Content area
        self.content = QVBoxLayout()
        self.content.setSpacing(10)
        layout.addLayout(self.content)
        layout.addStretch()


# class AnomalyCard(ModernCard):
#     def __init__(self, parent=None):
#         super().__init__("Anomaly Detection", parent)
#
#         # Status
#         status_layout = QHBoxLayout()
#         self.status_label = QLabel("System Status: Monitoring")
#         self.status_label.setFont(QFont('Segoe UI', 11))
#         status_layout.addWidget(self.status_label)
#         status_layout.addStretch()
#         self.content.addLayout(status_layout)
#
#         # Anomaly Progress
#         self.progress_ring = ProgressRing()
#         progress_layout = QHBoxLayout()
#         progress_layout.addWidget(self.progress_ring)
#         progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.content.addLayout(progress_layout)
#
#         # Anomaly Index
#         self.anomaly_label = QLabel("No anomalies detected")
#         self.anomaly_label.setFont(QFont('Segoe UI', 11))
#         self.anomaly_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.content.addWidget(self.anomaly_label)
#
#     def set_anomaly(self, index=None):
#         if index:
#             self.status_label.setText("⚠️ ANOMALY DETECTED")
#             self.status_label.setStyleSheet("color: #ef4444; font-weight: bold;")
#             self.anomaly_label.setText(f"Anomaly detected at index: {index}")
#             self.status_indicator.set_status("error")
#             self.progress_ring.set_progress(100)
#         else:
#             self.status_label.setText("System Status: Monitoring")
#             self.status_label.setStyleSheet("")
#             self.anomaly_label.setText("No anomalies detected")
#             self.status_indicator.set_status("normal")
#             self.progress_ring.set_progress(0)
class AnomalyCard(ModernCard):
    def __init__(self, parent=None):
        super().__init__("Anomaly Detection", parent)

        # Status
        status_layout = QHBoxLayout()
        self.status_label = QLabel("System Status: Monitoring")
        self.status_label.setFont(QFont('Segoe UI', 11))
        status_layout.addWidget(self.status_label)

        # Add current index display
        self.index_label = QLabel("Current Index: --")
        self.index_label.setFont(QFont('Segoe UI', 11))
        self.index_label.setStyleSheet("color: #6b7280;")  # Gray color
        status_layout.addWidget(self.index_label)

        status_layout.addStretch()
        self.content.addLayout(status_layout)

        # Anomaly Progress
        self.progress_ring = ProgressRing()
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_ring)
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content.addLayout(progress_layout)

        # Anomaly Index
        self.anomaly_label = QLabel("No anomalies detected")
        self.anomaly_label.setFont(QFont('Segoe UI', 11))
        self.anomaly_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content.addWidget(self.anomaly_label)

    def set_anomaly(self, window_end=None, first_anomaly_index=None):
        if window_end:
            self.status_label.setText("⚠️ ANOMALY DETECTED")
            self.status_label.setStyleSheet("color: #ef4444; font-weight: bold;")

            # Display both indices when available
            if first_anomaly_index:
                self.anomaly_label.setText(f"First anomaly at index: {first_anomaly_index}\nCurrent index at: {window_end}")
            else:
                self.anomaly_label.setText(f"Anomaly detected at index: {window_end}")

            self.status_indicator.set_status("error")
            self.progress_ring.set_progress(100)
        else:
            self.status_label.setText("System Status: Monitoring")
            self.status_label.setStyleSheet("")
            self.anomaly_label.setText("No anomalies detected")
            self.status_indicator.set_status("normal")
            self.progress_ring.set_progress(0)

    def update_current_index(self, index):
        self.index_label.setText(f"Current Index: {index}")

class DiagnosticCard(ModernCard):
    def __init__(self, parent=None):
        super().__init__("Diagnostic Results", parent)

        # Fault Information
        self.fault_label = QLabel("Awaiting diagnostic...")
        self.fault_label.setFont(QFont('Segoe UI', 11))
        self.content.addWidget(self.fault_label)

        # Confidence Bar
        confidence_layout = QVBoxLayout()
        confidence_header = QHBoxLayout()
        confidence_header.addWidget(QLabel("Confidence"))
        self.confidence_value = QLabel("--")
        confidence_header.addWidget(self.confidence_value)
        confidence_layout.addLayout(confidence_header)

        self.confidence_bar = QProgressBar()
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #f3f4f6;
                border-radius: 4px;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 4px;
            }
        """)
        confidence_layout.addWidget(self.confidence_bar)
        self.content.addLayout(confidence_layout)

    def update_diagnostic(self, fault_type, confidence):
        self.fault_label.setText(f"Detected: Fault Type {fault_type}")
        self.confidence_value.setText(f"{confidence:.1f}%")
        self.confidence_bar.setValue(int(confidence))

        if confidence > 75:
            self.status_indicator.set_status("error")
        elif confidence > 50:
            self.status_indicator.set_status("warning")
        else:
            self.status_indicator.set_status("normal")


class PrognosticCard(ModernCard):
    def __init__(self, parent=None):
        super().__init__("Prognostic Analysis", parent)

        # Main layout for RUL and Controls
        main_layout = QHBoxLayout()

        # RUL Display
        rul_layout = QVBoxLayout()
        self.rul_value = QLabel("--")
        self.rul_value.setFont(QFont('Segoe UI', 24, QFont.Weight.Bold))
        self.rul_value.setStyleSheet("color: #3b82f6;")
        rul_layout.addWidget(self.rul_value)

        self.rul_label = QLabel("Remaining Useful Life (hours)")
        self.rul_label.setFont(QFont('Segoe UI', 10))
        self.rul_label.setStyleSheet("color: #6b7280;")
        rul_layout.addWidget(self.rul_label)

        main_layout.addLayout(rul_layout)
        main_layout.addStretch()

        # Controls
        controls_layout = QVBoxLayout()
        self.run_button = ModernButton("Run Prognosis", "#3b82f6")
        controls_layout.addWidget(self.run_button)

        self.timestamp_label = QLabel("Last updated: Never")
        self.timestamp_label.setFont(QFont('Segoe UI', 9))
        self.timestamp_label.setStyleSheet("color: #6b7280;")
        controls_layout.addWidget(self.timestamp_label)

        main_layout.addLayout(controls_layout)
        self.content.addLayout(main_layout)

    def update_prognosis(self, rul, timestamp=None):
        self.rul_value.setText(f"{rul}")
        if timestamp:
            self.timestamp_label.setText(
                f"Last updated: {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
            )

        if rul < 50:
            self.status_indicator.set_status("error")
            self.rul_value.setStyleSheet("color: #ef4444;")
        elif rul < 100:
            self.status_indicator.set_status("warning")
            self.rul_value.setStyleSheet("color: #eab308;")
        else:
            self.status_indicator.set_status("normal")
            self.rul_value.setStyleSheet("color: #3b82f6;")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Self-Awareness System")
        self.setMinimumSize(1000, 700)

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Header
        header = QHBoxLayout()
        title = QLabel("Self-Awareness System")
        title.setFont(QFont('Segoe UI', 24, QFont.Weight.Bold))
        header.addWidget(title)

        self.start_button = ModernButton("Start System", "#059669")
        header.addWidget(self.start_button)
        layout.addLayout(header)

        # Cards Grid
        grid = QGridLayout()
        grid.setSpacing(20)

        self.anomaly_card = AnomalyCard()
        grid.addWidget(self.anomaly_card, 0, 0)

        self.diagnostic_card = DiagnosticCard()
        grid.addWidget(self.diagnostic_card, 0, 1)

        self.prognostic_card = PrognosticCard()
        grid.addWidget(self.prognostic_card, 1, 0, 1, 2)

        layout.addLayout(grid)

        # Connect signals
        self.start_button.clicked.connect(self.start_system)
        self.prognostic_card.run_button.clicked.connect(self.run_prognosis)

        # Initialize system state
        self.system_running = False

        # Apply global style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8fafc;
            }
        """)
        # Initialize system controller
        self.controller = SystemController()

        # Initialize system state
        self.system_running = False

    # def start_system(self):
    #     if not self.system_running:
    #         try:
    #             # Start monitoring
    #             worker = self.controller.start_monitoring()
    #             if worker:
    #                 # Connect signals
    #                 worker.anomaly_detected.connect(self.handle_anomaly)
    #                 worker.diagnostic_ready.connect(self.handle_diagnostic)
    #                 worker.start()
    #
    #             # Update UI
    #             self.system_running = True
    #             self.start_button.setText("Stop System")
    #             self.start_button.base_color = "#dc2626"
    #             self.start_button._setup_style()
    #
    #             # Reset cards
    #             self.anomaly_card.set_anomaly(None)
    #             self.diagnostic_card.update_diagnostic("--", 0)
    #             self.prognostic_card.update_prognosis("--")
    #
    #         except Exception as e:
    #             print(f"Error starting system: {str(e)}")
    #             return
    #     else:
    #         # Stop monitoring
    #         self.controller.stop_monitoring()
    #
    #         # Update UI
    #         self.system_running = False
    #         self.start_button.setText("Start System")
    #         self.start_button.base_color = "#059669"
    #         self.start_button._setup_style()
    def start_system(self):
        if not self.system_running:
            try:
                # Start monitoring
                worker = self.controller.start_monitoring()
                if worker:
                    # Connect signals
                    worker.anomaly_detected.connect(self.handle_anomaly)
                    worker.diagnostic_ready.connect(self.handle_diagnostic)
                    worker.current_index_updated.connect(self.handle_current_index)  # New connection
                    worker.start()

                # Update UI
                self.system_running = True
                self.start_button.setText("Stop System")
                self.start_button.base_color = "#dc2626"
                self.start_button._setup_style()

                # Reset cards
                self.anomaly_card.set_anomaly(None)
                self.diagnostic_card.update_diagnostic("--", 0)
                self.prognostic_card.update_prognosis("--")

            except Exception as e:
                print(f"Error starting system: {str(e)}")
                return

    def handle_current_index(self, index):
        """Handle updates to the current index"""
        self.anomaly_card.update_current_index(index)

    def handle_anomaly(self, window_end, first_anomaly_index):
        self.anomaly_card.set_anomaly(window_end, first_anomaly_index)

    def handle_diagnostic(self, fault_type, confidence):
        self.diagnostic_card.update_diagnostic(fault_type, confidence)

    def run_prognosis(self):
        try:
            result = self.controller.run_prognosis()
            if result and 'estimated_rul' in result:
                self.prognostic_card.update_prognosis(
                    round(result['estimated_rul'], 2),
                    result.get('timestamp', datetime.now().timestamp())
                )
        except Exception as e:
            print(f"Error running prognosis: {str(e)}")