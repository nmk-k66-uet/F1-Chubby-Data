import sys
import fastf1
import fastf1.plotting
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QComboBox, QPushButton, QLabel, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QTabWidget)
from PyQt6.QtCore import QThread, pyqtSignal

fastf1.Cache.enable_cache('f1_cache')

class FastF1DataLoader(QThread):
    data_loaded = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, year, gp, session_type):
        super().__init__()
        self.year, self.gp, self.session_type = year, gp, session_type

    def run(self):
        try:
            session = fastf1.get_session(self.year, self.gp, self.session_type)
            session.load(telemetry=True, weather=False) 
            self.data_loaded.emit(session)
        except Exception as e:
            self.error_occurred.emit(f"Lỗi khi tải: {str(e)}")

class F1Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Pulse Dashboard - Advanced Analytics")
        self.setGeometry(50, 50, 1200, 900) # Tăng thêm chiều cao để chứa đồ thị mới
        self.current_session = None
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- PANEL ĐIỀU KHIỂN ---
        control_layout = QHBoxLayout()
        self.year_combo = QComboBox()
        self.year_combo.addItems(["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"])
        self.gp_combo = QComboBox()
        self.gp_combo.addItems(["Australia", "China", "Japan", "Bahrain", "Saudi Arabia", "Miami", "Emilia-Romagna", "Monaco", "Spain", "Canada", "Austria", "Great Britain", "Belgium", "Hungary", "Netherlands", "Italy", "Azerbaijan", "Singapore", "United States", "Mexico", "Brazil", "Las Vegas", "Qatar", "Abu Dhabi"])
        self.session_combo = QComboBox()
        self.session_combo.addItems(["FP1", "FP2", "FP3", "Q", "S", "SS", "SQ", "R"])
        
        self.btn_load = QPushButton("Tải Dữ Liệu")
        self.btn_load.clicked.connect(self.load_data)
        self.btn_load.setStyleSheet("background-color: #E10600; color: white; font-weight: bold;")
        
        self.status_label = QLabel("Sẵn sàng.")

        control_layout.addWidget(QLabel("Mùa giải:"))
        control_layout.addWidget(self.year_combo)
        control_layout.addWidget(QLabel("Chặng:"))
        control_layout.addWidget(self.gp_combo)
        control_layout.addWidget(QLabel("Session:"))
        control_layout.addWidget(self.session_combo)
        control_layout.addWidget(self.btn_load)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Bảng kết quả
        self.tab_results = QWidget()
        self.tab_results_layout = QVBoxLayout(self.tab_results)
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["Hạng", "Tay đua", "Đội", "Thời gian"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tab_results_layout.addWidget(self.result_table)
        self.tabs.addTab(self.tab_results, "Kết quả chung (Results)")

        # Tab 2: Telemetry & Driver Inputs
        self.tab_telemetry = QWidget()
        self.tab_telemetry_layout = QVBoxLayout(self.tab_telemetry)
        
        driver_select_layout = QHBoxLayout()
        self.drv1_combo = QComboBox()
        self.drv2_combo = QComboBox()
        self.btn_plot_telemetry = QPushButton("Vẽ so sánh Telemetry")
        self.btn_plot_telemetry.clicked.connect(self.plot_telemetry)
        
        driver_select_layout.addWidget(QLabel("Tay đua 1:"))
        driver_select_layout.addWidget(self.drv1_combo)
        driver_select_layout.addWidget(QLabel("Tay đua 2:"))
        driver_select_layout.addWidget(self.drv2_combo)
        driver_select_layout.addWidget(self.btn_plot_telemetry)
        driver_select_layout.addStretch()
        self.tab_telemetry_layout.addLayout(driver_select_layout)

        self.fig_telemetry = Figure(figsize=(10, 8))
        self.canvas_telemetry = FigureCanvas(self.fig_telemetry)
        self.tab_telemetry_layout.addWidget(self.canvas_telemetry)
        
        self.tabs.addTab(self.tab_telemetry, "Phân tích Viễn đo (Telemetry)")

        # Tab 3: Track Map (Tốc độ & Gear)
        self.tab_track = QWidget()
        self.tab_track_layout = QVBoxLayout(self.tab_track)
        
        track_control_layout = QHBoxLayout()
        self.track_drv_combo = QComboBox()
        
        # Thêm ComboBox chọn loại dữ liệu tô màu cho bản đồ
        self.track_color_combo = QComboBox()
        self.track_color_combo.addItems(["Tốc độ (Speed)", "Số (Gear)"])
        
        self.btn_plot_track = QPushButton("Vẽ Bản đồ Đường đua")
        self.btn_plot_track.clicked.connect(self.plot_track_map)
        self.btn_plot_track.setStyleSheet("background-color: #15151E; color: white;")
        
        track_control_layout.addWidget(QLabel("Chọn tay đua:"))
        track_control_layout.addWidget(self.track_drv_combo)
        track_control_layout.addWidget(QLabel("Tô màu theo:"))
        track_control_layout.addWidget(self.track_color_combo)
        track_control_layout.addWidget(self.btn_plot_track)
        track_control_layout.addStretch()
        self.tab_track_layout.addLayout(track_control_layout)

        self.fig_track = Figure(figsize=(8, 8))
        self.canvas_track = FigureCanvas(self.fig_track)
        self.tab_track_layout.addWidget(self.canvas_track)
        
        self.tabs.addTab(self.tab_track, "Bản đồ đường đua (Track Map)")

        # Tab 4: Strategy (Chiến thuật, Lốp & Race Trace)
        self.tab_strategy = QWidget()
        self.tab_strategy_layout = QVBoxLayout(self.tab_strategy)
        
        strategy_control_layout = QHBoxLayout()
        self.strategy_drv_combo = QComboBox()
        self.btn_plot_strategy = QPushButton("Vẽ Phân tích Chiến thuật (Grid)")
        self.btn_plot_strategy.clicked.connect(self.plot_strategy)
        self.btn_plot_strategy.setStyleSheet("background-color: #E10600; color: white;")
        
        strategy_control_layout.addWidget(QLabel("Chọn tay đua (Để xem độ mòn lốp):"))
        strategy_control_layout.addWidget(self.strategy_drv_combo)
        strategy_control_layout.addWidget(self.btn_plot_strategy)
        strategy_control_layout.addStretch()
        self.tab_strategy_layout.addLayout(strategy_control_layout)

        # Canvas Matplotlib to hơn để chứa 3 biểu đồ
        self.fig_strategy = Figure(figsize=(12, 10)) 
        self.canvas_strategy = FigureCanvas(self.fig_strategy)
        self.tab_strategy_layout.addWidget(self.canvas_strategy)
        
        self.tabs.addTab(self.tab_strategy, "Chiến thuật & Lốp (Strategy)")

    def load_data(self):
        self.status_label.setText("Đang tải dữ liệu (có thể mất vài phút vì bật Telemetry)...")
        self.btn_load.setEnabled(False)
        self.loader_thread = FastF1DataLoader(
            int(self.year_combo.currentText()), 
            self.gp_combo.currentText(), 
            self.session_combo.currentText()
        )
        self.loader_thread.data_loaded.connect(self.on_data_loaded)
        self.loader_thread.start()

    def on_data_loaded(self, session):
        self.current_session = session
        self.status_label.setText("Tải thành công!")
        self.btn_load.setEnabled(True)
        
        self.populate_table(session.results)
        
        drivers = session.results['Abbreviation'].dropna().tolist()
        self.drv1_combo.clear(); self.drv1_combo.addItems(drivers)
        self.drv2_combo.clear(); self.drv2_combo.addItems(drivers)
        self.track_drv_combo.clear(); self.track_drv_combo.addItems(drivers)
        self.strategy_drv_combo.clear(); self.strategy_drv_combo.addItems(drivers)
        
        if len(drivers) >= 2:
            self.drv1_combo.setCurrentText(drivers[0])
            self.drv2_combo.setCurrentText(drivers[1])

    def populate_table(self, results_df):
        self.result_table.setRowCount(0)
        for index, row in results_df.iterrows():
            r = self.result_table.rowCount()
            self.result_table.insertRow(r)
            self.result_table.setItem(r, 0, QTableWidgetItem(str(row.get('Position', ''))))
            self.result_table.setItem(r, 1, QTableWidgetItem(str(row.get('FullName', ''))))
            self.result_table.setItem(r, 2, QTableWidgetItem(str(row.get('TeamName', ''))))
            self.result_table.setItem(r, 3, QTableWidgetItem(str(row.get('Time', ''))))

    def plot_telemetry(self):
        if not self.current_session: return
        drv1, drv2 = self.drv1_combo.currentText(), self.drv2_combo.currentText()
        
        try:
            lap_drv1 = self.current_session.laps.pick_drivers(drv1).pick_fastest()
            lap_drv2 = self.current_session.laps.pick_drivers(drv2).pick_fastest()

            tel_drv1 = lap_drv1.get_telemetry().add_distance()
            tel_drv2 = lap_drv2.get_telemetry().add_distance()

            color_drv1 = f"#{self.current_session.get_driver(drv1)['TeamColor']}"
            color_drv2 = f"#{self.current_session.get_driver(drv2)['TeamColor']}"
            if color_drv1 == "#nan" or not color_drv1: color_drv1 = "white"
            if color_drv2 == "#nan" or not color_drv2: color_drv2 = "gray"

            self.fig_telemetry.clear()
            ax1, ax2, ax3, ax4 = self.fig_telemetry.subplots(4, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1, 1, 1]})
            self.fig_telemetry.subplots_adjust(hspace=0.1)

            ax1.plot(tel_drv1['Distance'], tel_drv1['Speed'], color=color_drv1, label=drv1)
            ax1.plot(tel_drv2['Distance'], tel_drv2['Speed'], color=color_drv2, label=drv2)
            ax1.set_ylabel('Speed (km/h)')
            ax1.legend(loc='lower right')
            ax1.grid(True, linestyle='--', alpha=0.6)

            ax2.plot(tel_drv1['Distance'], tel_drv1['Throttle'], color=color_drv1)
            ax2.plot(tel_drv2['Distance'], tel_drv2['Throttle'], color=color_drv2)
            ax2.set_ylabel('Throttle (%)')
            ax2.grid(True, linestyle='--', alpha=0.6)

            ax3.plot(tel_drv1['Distance'], tel_drv1['Brake'], color=color_drv1)
            ax3.plot(tel_drv2['Distance'], tel_drv2['Brake'], color=color_drv2)
            ax3.set_ylabel('Brake')
            ax3.set_yticks([0, 1])
            ax3.grid(True, linestyle='--', alpha=0.6)

            ax4.plot(tel_drv1['Distance'], tel_drv1['nGear'], color=color_drv1)
            ax4.plot(tel_drv2['Distance'], tel_drv2['nGear'], color=color_drv2)
            ax4.set_ylabel('Gear')
            ax4.set_xlabel('Distance (m)')
            ax4.grid(True, linestyle='--', alpha=0.6)

            self.canvas_telemetry.draw()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi vẽ biểu đồ", f"Không thể vẽ dữ liệu: {str(e)}")

    def plot_track_map(self):
        if not self.current_session: return
        driver = self.track_drv_combo.currentText()
        color_mode = self.track_color_combo.currentText()
        
        try:
            lap = self.current_session.laps.pick_drivers(driver).pick_fastest()
            telemetry = lap.get_telemetry()

            x = telemetry['X']
            y = telemetry['Y']
            
            # Khởi tạo điểm và segments
            points = np.array([x, y]).T.reshape(-1, 1, 2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)

            self.fig_track.clear()
            ax = self.fig_track.add_subplot(111)

            # Phân nhánh theo lựa chọn của người dùng (Tốc độ hoặc Gear)
            if "Speed" in color_mode:
                data_to_plot = telemetry['Speed']
                cmap = plt.get_cmap('plasma')
                norm = plt.Normalize(data_to_plot.min(), data_to_plot.max())
                cb_label = 'Tốc độ (km/h)'
                title_suffix = "Speed Profile"
            else:
                data_to_plot = telemetry['nGear']
                # Số từ 1 đến 8, dùng dải màu phân biệt rõ ràng (Paired/tab10)
                cmap = plt.get_cmap('Paired', 8) 
                norm = plt.Normalize(1, 9)
                cb_label = 'Số (Gear 1-8)'
                title_suffix = "Gear Shift Map"

            lc = LineCollection(segments, cmap=cmap, norm=norm, linestyle='-', linewidth=5)
            lc.set_array(data_to_plot) 

            line = ax.add_collection(lc)
            cb = self.fig_track.colorbar(line, ax=ax)
            cb.set_label(cb_label)

            ax.axis('equal') 
            ax.axis('off')
            ax.set_title(f"Track Map - {driver} {title_suffix}", fontsize=14, fontweight='bold')

            self.canvas_track.draw()

        except Exception as e:
            QMessageBox.warning(self, "Lỗi vẽ Track Map", f"Không thể vẽ dữ liệu: {str(e)}")

    def plot_strategy(self):
        if not self.current_session: return
        driver = self.strategy_drv_combo.currentText()
        
        try:
            # Dùng GridSpec để chia layout: Hàng 1 (2 cột), Hàng 2 (gộp 2 cột làm 1 cho biểu đồ Gap)
            self.fig_strategy.clear()
            gs = self.fig_strategy.add_gridspec(2, 2, height_ratios=[1, 1.2]) 
            ax1 = self.fig_strategy.add_subplot(gs[0, 0]) # Boxplot
            ax2 = self.fig_strategy.add_subplot(gs[0, 1]) # Tyre
            ax3 = self.fig_strategy.add_subplot(gs[1, :]) # Gap To Leader (Full chiều ngang)
            
            # Lấy data đã lọc các vòng pit (cho Boxplot & Tyre)
            quick_laps = self.current_session.laps.pick_quicklaps()
            
            # ==========================================
            # BIỂU ĐỒ 1 (TRÁI): BOXPLOT ĐỘ ỔN ĐỊNH LAP TIME
            # ==========================================
            top_drivers = self.current_session.results['Abbreviation'].head(5).tolist()
            lap_times_data, labels, colors = [], [], []
            
            for drv in top_drivers:
                drv_laps = quick_laps.pick_drivers(drv)
                times = drv_laps['LapTime'].dt.total_seconds().dropna()
                if not times.empty:
                    lap_times_data.append(times)
                    labels.append(drv)
                    color = f"#{self.current_session.get_driver(drv)['TeamColor']}"
                    colors.append(color if color and color != "#nan" else "white")
            
            bplot = ax1.boxplot(lap_times_data, tick_labels=labels, patch_artist=True)
            for patch, color in zip(bplot['boxes'], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.8)
                
            ax1.set_title("Race Pace Consistency (Top 5 Drivers)", fontweight='bold')
            ax1.set_ylabel("Lap Time (Seconds)")
            ax1.grid(True, linestyle='--', alpha=0.4)

            # ==========================================
            # BIỂU ĐỒ 2 (PHẢI): TYRE DEGRADATION (HAO MÒN LỐP)
            # ==========================================
            drv_laps_tyre = quick_laps.pick_drivers(driver).dropna(subset=['TyreLife', 'LapTime'])
            x = drv_laps_tyre['TyreLife']
            y = drv_laps_tyre['LapTime'].dt.total_seconds()
            compounds = drv_laps_tyre['Compound']
            
            compound_colors = {'SOFT': 'red', 'MEDIUM': 'yellow', 'HARD': 'white', 'INTERMEDIATE': 'green', 'WET': 'blue'}
            for compound in compounds.unique():
                mask = compounds == compound
                ax2.scatter(x[mask], y[mask], color=compound_colors.get(compound, 'gray'), label=compound, alpha=0.8, edgecolors='black')
                
            if len(x) > 1:
                z = np.polyfit(x, y, 1) 
                p = np.poly1d(z)
                ax2.plot(x, p(x), color='cyan', linestyle='--', linewidth=2, label='Degradation Trend')

            ax2.set_title(f"Tyre Degradation Profile - {driver}", fontweight='bold')
            ax2.set_xlabel("Tyre Age")
            ax2.set_ylabel("Lap Time (Sec)")
            ax2.legend()
            ax2.grid(True, linestyle='--', alpha=0.4)

            # ==========================================
            # BIỂU ĐỒ 3 (DƯỚI): RACE TRACE / GAP TO LEADER
            # ==========================================
            # Dùng dữ liệu TẤT CẢ các vòng (kể cả pit stop) để tính gap tích lũy chính xác
            all_laps = self.current_session.laps
            leader = top_drivers[0]
            leader_laps = all_laps.pick_drivers(leader)[['LapNumber', 'Time']].set_index('LapNumber')
            
            for drv, color in zip(top_drivers, colors):
                curr_drv_laps = all_laps.pick_drivers(drv)[['LapNumber', 'Time']].set_index('LapNumber')
                # Nối bảng dữ liệu dựa trên vòng đua (inner join)
                merged = curr_drv_laps.join(leader_laps, lsuffix='_drv', rsuffix='_leader', how='inner')
                # Gap = Tổng thời gian của tay đua - Tổng thời gian của Leader
                gap = (merged['Time_drv'] - merged['Time_leader']).dt.total_seconds()
                ax3.plot(merged.index, gap, label=drv, color=color, linewidth=2)

            ax3.set_title("Race Trace (Gap to Leader) - Top 5", fontweight='bold')
            ax3.set_xlabel("Lap Number")
            ax3.set_ylabel("Gap to Leader (Seconds)")
            # Đảo ngược trục Y để Leader (0s) luôn nằm ở trên cùng, các xe bị dẫn trước nằm ở dưới
            ax3.invert_yaxis()
            ax3.legend()
            ax3.grid(True, linestyle='--', alpha=0.4)

            # Tinh chỉnh lại layout để không đè chữ
            self.fig_strategy.tight_layout()
            self.canvas_strategy.draw()
            
        except Exception as e:
            QMessageBox.warning(self, "Lỗi vẽ Strategy", f"Không thể vẽ dữ liệu: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    fastf1.plotting.setup_mpl(mpl_timedelta_support=False) 
    window = F1Dashboard()
    window.show()
    sys.exit(app.exec())