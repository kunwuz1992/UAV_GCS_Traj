import ctypes
import struct

from python_qt_binding import QtCore, QtWidgets

from rqt_multi_uav_gcs import qnode
from rqt_multi_uav_gcs.lib import (
    ArrayDisplayGroupBox,
    BoundedLineEdit,
    StatusLabel,
    StyledGroupBox,
)


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        layout = QtWidgets.QGridLayout()

        prefix_label = QtWidgets.QLabel("Vehicle Prefix")
        layout.addWidget(prefix_label, 0, 0)

        self._prefix_editor = QtWidgets.QLineEdit()
        self._prefix_editor.setPlaceholderText(
            "If prefix is empty, node will subscribe to `/mavros/...`"
        )
        layout.addWidget(self._prefix_editor, 0, 1)

        self._add_uav_button = QtWidgets.QPushButton("Connect")
        layout.addWidget(self._add_uav_button, 0, 2)
        self._add_uav_button.clicked.connect(self.add_vehicle)

        spacer = QtWidgets.QSpacerItem(
            60, 40, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        layout.addItem(spacer, 0, 3)

        self._tabs = QtWidgets.QTabWidget()
        self._tabs.setStyleSheet(
            """QTabWidget {
    font-size: 20px;
}"""
        )
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self.remove_tab)
        self._pages = []
        self._trajectory_progress_all = {}
        # team_mgmt_group_box = self.make_team_mgmt_box()

        self._node = qnode.QNode()
        for tab_title, tab_receiver in self._node.vehicles.items():
            self.make_tab(tab_title, tab_receiver)
        layout.addWidget(self._tabs, 1, 0, 1, 4)
        # layout.addWidget(team_mgmt_group_box)

        self.setLayout(layout)

    # def make_team_mgmt_box(self):
    #     team_mgmt_group_box = QtWidgets.QGroupBox("Team Management")
    #     layout = QtWidgets.QGridLayout()
    #     self.toggle_all_trajectory_button = QtWidgets.QPushButton(
    #         "Start Trajectory for all"
    #     )

    #     def _toggle_all_trajectory(_):
    #         for it in self._pages:
    #             it.toggle_trajectory_exec.emit(
    #                 self.toggle_all_trajectory_button.text().startswith("Start")
    #             )

    #     self.toggle_all_trajectory_button.clicked.connect(_toggle_all_trajectory)
    #     layout.addWidget(self.toggle_all_trajectory_button)
    #     team_mgmt_group_box.setLayout(layout)
    #     return team_mgmt_group_box

    def make_tab(self, name, receiver):
        page = Page(receiver)

        if not name:
            pretty_title = "Main UAV"
        else:
            pretty_title = "Multi UAV: %s" % name
        self._tabs.addTab(page, pretty_title)
        page.update_traj_progress_to_mw.connect(
            lambda progress: self.update_traj_progress(progress, pretty_title)
        )
        self._pages.append(page)

    def remove_tab(self, idx):
        pretty_title = self._tabs.tabText(idx)
        if pretty_title == "Main UAV":
            key = ""
        else:
            key = pretty_title.split(":")[1].strip()
        # Shutdown explicitly to ensure no subscribers will trigger callbacks
        # dependent on the expiring objects
        self._node.vehicles.pop(key).shutdown()
        self._tabs.removeTab(idx)

    def add_vehicle(self, _):
        name = self._prefix_editor.text()
        title, receiver = self._node.add_vehicle(name)
        if title is None:
            return
        self.make_tab(title, receiver)
        self._prefix_editor.clear()

    def shutdown(self):
        # Shutdown explicitly to ensure no subscribers will trigger callbacks
        # dependent on the expiring objects
        for it in list(self._node.vehicles):
            self._node.vehicles.pop(it).shutdown()

    def update_traj_progress(self, progress, title):
        self._trajectory_progress_all[title] = progress
        prog_all = self._trajectory_progress_all.values()
        all_enabled = all(it < 0 for it in prog_all)
        self.toggle_all_trajectory_button.setDisabled(all_enabled)

        all_startable = all(it <= 0 for it in prog_all)
        self.toggle_all_trajectory_button.setText(
            "%s trajectory" % ("Start" if all_startable else "Stop")
        )
        self.toggle_all_trajectory_button.setStyleSheet(
            """QPushButton {
    color : %s;
    background-color: %s;
    font-weight: bold;
}"""
            % (("black", "white") if all_startable else ("white", "red"))
        )


class Page(QtWidgets.QWidget):
    arming = QtCore.pyqtSignal(bool)
    set_mode = QtCore.pyqtSignal(str)
    update_odom_topic = QtCore.pyqtSignal(str)
    send_refs = QtCore.pyqtSignal(float, float, float, float)
    set_home = QtCore.pyqtSignal(float, float, float)
    toggle_trajectory_exec = QtCore.pyqtSignal(bool)
    load_trajectory_file = QtCore.pyqtSignal(str)
    update_traj_progress_to_mw = QtCore.pyqtSignal(float)

    def __init__(self, receiver: qnode.VehicleNode):
        super().__init__()
        self._is_armed = False
        self._receiver = receiver

        self.setWindowTitle("multi_uav_gcs_window")

        layout = QtWidgets.QHBoxLayout()
        lhs_frame = QtWidgets.QFrame()
        lhs_layout = QtWidgets.QVBoxLayout()
        lhs_layout.addWidget(self.make_vehicle_state_groupbox())
        lhs_layout.addWidget(self.make_user_command_groupbox())
        lhs_frame.setLayout(lhs_layout)
        layout.addWidget(lhs_frame)

        rhs_frame = QtWidgets.QFrame()
        rhs_layout = QtWidgets.QVBoxLayout()
        rhs_layout.addWidget(self.make_command_state_groupbox())
        rhs_layout.addWidget(self.make_offboard_control_groupbox())
        rhs_layout.addItem(
            QtWidgets.QSpacerItem(
                0, 0, QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
            )
        )
        rhs_frame.setLayout(rhs_layout)
        layout.addWidget(rhs_frame)
        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

        # Setup Connections
        # ~~~~~~~~~~~~~~~~~
        self._receiver.update_rpy.connect(self.update_rpy)
        self._receiver.update_lla.connect(self.update_lla)
        self._receiver.update_state.connect(self.update_state)
        self._receiver.update_local_position.connect(self.update_local_position)
        self._receiver.update_local_velocity.connect(self.update_local_velocity)
        self._receiver.update_nsats.connect(self.update_nsats)
        self._receiver.update_setpoints.connect(self.update_setpoints)
        self._receiver.update_battery.connect(self.update_battery)
        self._receiver.update_traj_progress.connect(self.update_traj_progress)
        self.arming.connect(self._receiver.arming)
        self.set_mode.connect(self._receiver.set_mode)
        self.update_odom_topic.connect(self._receiver.update_odom_topic)
        self.send_refs.connect(self._receiver.send_refs)
        self.set_home.connect(self._receiver.set_home)
        self.toggle_trajectory_exec.connect(self._receiver.toggle_trajectory_exec)
        self.load_trajectory_file.connect(self._receiver.load_trajectory_file)

    # Group Box Definitions
    # ---------------------
    def make_vehicle_state_groupbox(self):
        layout = QtWidgets.QGridLayout()
        box = StyledGroupBox("UAV States")

        self._lla_box = ArrayDisplayGroupBox(
            "Global Position 🌐",
            ["lat (deg)", "lon (deg)", "alt (m-AGL)"],
            digits=(4, 4, 6),
            width=120,
            height=40,
        )
        self._enu_box = ArrayDisplayGroupBox(
            "Local Position ⤱",
            ["%s (m)" % it for it in "XYZ"],
            digits=5,
            width=120,
            height=40,
        )
        self._vel_box = ArrayDisplayGroupBox(
            "Local Velocity ⇶",
            ["v<sub>%s</sub> (ms<sup>-1</sup>)" % it for it in "XYZ"],
            width=120,
            height=40,
        )
        self._rpy_box = ArrayDisplayGroupBox(
            "Orientation ⭯",
            ["%s (°)" % it for it in ("roll", "pitch", "yaw")],
            width=120,
            height=40,
        )
        layout.addWidget(self._lla_box, 1, 0, 1, 2)
        layout.addWidget(self._rpy_box, 1, 3, 1, 2)
        layout.addWidget(QtWidgets.QLabel("Odometry Topic"), 2, 0)
        self._odometry_line_edit = QtWidgets.QLineEdit()
        if self._receiver.odom_topic:
            self._odometry_line_edit.setPlaceholderText(self._receiver.odom_topic)
        else:
            self._odometry_line_edit.setPlaceholderText("Odometry topic")
        layout.addWidget(self._odometry_line_edit, 2, 1, 1, 3)
        if "odom" in self._receiver.subs:
            self._odom_toggle_button = QtWidgets.QPushButton("Use local position")
        else:
            self._odom_toggle_button = QtWidgets.QPushButton("Use odometry")
        self._odom_toggle_button.clicked.connect(self._toggle_odom_topic)
        layout.addWidget(self._odom_toggle_button, 2, 4)

        layout.addWidget(self._enu_box, 3, 0, 1, 2)
        layout.addWidget(self._vel_box, 3, 3, 1, 2)
        box.setLayout(layout)
        return box

    def make_command_state_groupbox(self):
        box = StyledGroupBox("UAV Status")
        layout = QtWidgets.QGridLayout()

        self._connected_lbl = StatusLabel("Disconnected", "red", width=150)
        self._armed_lbl = StatusLabel("Disarmed", "green", width=100)
        self._mode_lbl = StatusLabel("Unknown", "black", width=200)

        layout.addWidget(self._connected_lbl, 0, 0)
        layout.addWidget(self._armed_lbl, 0, 1)
        layout.addWidget(self._mode_lbl, 0, 2)

        layout.addWidget(StatusLabel("# Sats", "black", width=80), 0, 3)
        self._nsat_box = QtWidgets.QLCDNumber(2)

        self._nsat_box.setMinimumHeight(30)
        self._nsat_box.setSegmentStyle(QtWidgets.QLCDNumber.Flat)
        layout.addWidget(self._nsat_box, 0, 4)

        self._battery_level = QtWidgets.QProgressBar()
        self._battery_level.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred
        )
        layout.addWidget(StatusLabel("Battery", "black"), 1, 0)
        layout.addWidget(self._battery_level, 1, 1, 1, 2)
        self._voltage_level = StatusLabel("N/A (V)", "black")
        layout.addWidget(self._voltage_level, 1, 3, 1, 2)
        box.setLayout(layout)
        return box

    def make_offboard_control_groupbox(self):
        box = StyledGroupBox("Offboard Control")
        layout = QtWidgets.QGridLayout()

        display_box = QtWidgets.QGroupBox("Setpoints feedback")
        self._setpoints = QtWidgets.QStackedLayout()

        self._sp_boxes = [
            ArrayDisplayGroupBox(
                "Attitude Setpoint",
                ["%s (°)" % it for it in ["roll", "pitch", "yaw"]] + ["Thrust"],
                width=80,
                height=40,
            ),
            ArrayDisplayGroupBox(
                "Body Rates Setpoint",
                ["ω<sub>%s</sub>" % it for it in "XYZ"] + ["Thrust"],
                width=80,
                height=40,
            ),
        ]
        for it in self._sp_boxes:
            self._setpoints.addWidget(it)

        display_box.setLayout(self._setpoints)
        layout.addWidget(display_box)

        refs_box = QtWidgets.QGroupBox("Send References")
        refs_layout = QtWidgets.QGridLayout()

        self._refs_line_edits = []
        refs_bounds_line_edits = []
        for idx, it in enumerate(list("xyz") + ["yaw"]):
            if it == "yaw":
                line_edit = BoundedLineEdit(0.0, (-180, 180))
                label = "yaw reference (°)"
            else:
                line_edit = BoundedLineEdit(0.0)
                label = "%s reference (m)" % it.upper()
            line_edit.setPlaceholderText(label)
            refs_layout.addWidget(QtWidgets.QLabel(label), 0, 2 * idx, 1, 2)
            refs_layout.addWidget(line_edit, 1, 2 * idx, 1, 2)
            self._refs_line_edits.append(line_edit)
            if it != "yaw":
                geofence_length = 10.0

                bounds = (
                    BoundedLineEdit(-geofence_length),
                    BoundedLineEdit(geofence_length),
                )
                line_edit.set_bounds(float(bounds[0].text()), float(bounds[1].text()))
                for v in bounds:
                    v.setEnabled(False)
                    v.setFixedWidth(80)
                bounds[0].textChanged.connect(
                    lambda lb_str, ub=bounds[1], target=line_edit: target.set_bounds(
                        float(lb_str) if lb_str and lb_str != "-" else 0.0,
                        float(ub.text()),
                    )
                )
                bounds[1].textChanged.connect(
                    lambda ub_str, lb=bounds[0], target=line_edit: target.set_bounds(
                        float(lb.text()),
                        float(ub_str) if ub_str and ub_str != "-" else 0.0,
                    )
                )

                refs_bounds_line_edits.extend(bounds)
                refs_layout.addWidget(
                    QtWidgets.QLabel("Min. %s (m)" % it.upper()), 2, 2 * idx, 1, 1
                )
                refs_layout.addWidget(
                    QtWidgets.QLabel("Max. %s (m)" % it.upper()), 2, 2 * idx + 1, 1, 1
                )
                refs_layout.addWidget(bounds[0], 3, 2 * idx, 1, 1)
                refs_layout.addWidget(bounds[1], 3, 2 * idx + 1, 1, 1)
            else:
                unlock_bounds_checkbox = QtWidgets.QCheckBox("Unlock bounds")

                unlock_bounds_checkbox.stateChanged.connect(
                    lambda s: [
                        bnd.setEnabled(s == QtCore.Qt.Checked)
                        for bnd in refs_bounds_line_edits
                    ]
                )
                refs_layout.addWidget(unlock_bounds_checkbox, 3, 7, 1, 1)

        copy_position_button = QtWidgets.QPushButton("Copy current position")
        copy_position_button.clicked.connect(self._copy_position)
        refs_layout.addWidget(copy_position_button, 4, 0, 1, 2)

        send_refs_button = QtWidgets.QPushButton("Send Reference")

        send_refs_button.clicked.connect(
            lambda: self.send_refs.emit(
                *[float(e.text()) for e in self._refs_line_edits]
            )
        )
        refs_layout.addWidget(send_refs_button, 4, 2, 1, 2)

        refs_box.setLayout(refs_layout)
        layout.addWidget(refs_box)
        box.setLayout(layout)

        return box

    def _set_arming_button_style(self):
        self._arming_button.setStyleSheet(
            """QPushButton {
    color : %s;
    background-color: %s;
    font-size: 25px;
    font-weight: bold;
}"""
            % (("black", "white") if self._is_armed else ("white", "red"))
        )

    def make_user_command_groupbox(self):
        box = StyledGroupBox("Commands")
        layout = QtWidgets.QGridLayout()

        self._arming_button = QtWidgets.QPushButton(
            "Disarm" if self._is_armed else "Arm"
        )
        self._set_arming_button_style()
        self._arming_button.clicked.connect(
            lambda: self.arming.emit(not self._is_armed)
        )
        layout.addWidget(self._arming_button, 0, 0)

        px4_modes = [
            "STABILIZED",
            "ALTCTL",
            "POSCTL",
            "OFFBOARD",
            "AUTO.LOITER",
            "AUTO.TAKEOFF",
            "AUTO.PRECLAND",
            "AUTO.FOLLOW_TARGET",
            "AUTO.RTGS",
            "AUTO.LAND",
            "AUTO.RTL",
            "AUTO.MISSION",
            "RATTITUDE",
            "AUTO.READY",
            "ACRO",
            "MANUAL",
        ]
        apm_modes = [
            "STABILIZE",
            "ALT_HOLD",
            "POSHOLD",
            "POSITION",
            "GUIDED",
            "LOITER",
            "GUIDED_NOGPS",
            "AVOID_ADSB",
            "THROW",
            "BRAKE",
            "AUTOTUNE",
            "FLIP",
            "SPORT",
            "DRIFT",
            "OF_LOITER",
            "LAND",
            "CIRCLE",
            "RTL",
            "AUTO",
            "ACRO",
        ]
        mode_menu = QtWidgets.QComboBox()
        mode_menu.addItems(px4_modes)
        mode_menu.setStyleSheet(
            """QComboBox {
    font-size: 25px;
    font-weight: bold;
}"""
        )
        mode_menu.currentIndexChanged.connect(
            lambda idx: self.set_mode.emit(mode_menu.itemText(idx))
        )
        layout.addWidget(mode_menu, 0, 1)
        mode_toggle = QtWidgets.QCheckBox("Use APM Modes")
        mode_toggle.setStyleSheet(
            """QCheckBox {
    font-size: 25px;
    font-weight: bold;
}"""
        )
        layout.addWidget(mode_toggle, 0, 2)

        def toggle_modeset(state):
            mode_menu.blockSignals(True)
            mode_menu.clear()
            if state == QtCore.Qt.Checked:
                mode_menu.addItems(apm_modes)
            else:
                mode_menu.addItems(px4_modes)
            mode_menu.blockSignals(False)

        mode_toggle.stateChanged.connect(toggle_modeset)

        layout.addWidget(self.make_home_location_subbox(), 1, 0, 1, 3)
        layout.addWidget(self.make_trajectory_subbox(), 2, 0, 1, 3)
        box.setLayout(layout)
        return box

    def make_home_location_subbox(self):
        box = QtWidgets.QGroupBox("Home Location")
        layout = QtWidgets.QHBoxLayout()

        home_location = []
        for idx, char in enumerate("xyz"):
            ith_home_location = QtWidgets.QLineEdit("0")
            ith_home_location.setPlaceholderText(f"{char} home position")

            layout.addWidget(ith_home_location)
            home_location.append(ith_home_location)

        set_home_button = QtWidgets.QPushButton("Set Home")

        def set_home_action(_):
            home_loc = [float(it.text()) for it in home_location]
            self.set_home.emit(*home_loc)

        set_home_button.clicked.connect(set_home_action)
        layout.addWidget(set_home_button)
        box.setLayout(layout)
        return box

    def make_trajectory_subbox(self):
        box = QtWidgets.QGroupBox("Trajectory Tracking")
        layout = QtWidgets.QGridLayout()

        # creat a button for starting the trajectory tracking controller, initially disable
        self._toggle_trajectory_button = QtWidgets.QPushButton("Start Trajectory")
        self._toggle_trajectory_button.setEnabled(False)

        self._toggle_trajectory_button.clicked.connect(self.toggle_trajectory)
        layout.addWidget(self._toggle_trajectory_button, 0, 0)

        # creat a button for starting the stabilization controller, initially enable
        self._toggle_stabilization_button = QtWidgets.QPushButton("Start stabilization")
        self._toggle_stabilization_button.setEnabled(True)

        self._toggle_stabilization_button.clicked.connect(self.toggle_stabilization)
        layout.addWidget(self._toggle_stabilization_button, 0, 1)

        # creat space to display the controller status
        layout.addWidget(QtWidgets.QLabel("Current Controller"), 1, 0)
        self._controller_name_line_edit = QtWidgets.QLineEdit()
        layout.addWidget(self._controller_name_line_edit, 1, 1)
        self._controller_name_line_edit.setText("Stabilization")

        # creat a button to load the ref trajectory
        load_trajectory_button = QtWidgets.QPushButton("Load Trajectory File")
        fd = QtWidgets.QFileDialog()

        self._file_name_line_edit = QtWidgets.QLineEdit()

        def load_trajectory_file(_):
            file_name, _ = fd.getOpenFileName(
                caption="Load Trajectory File",
                filter="Trajectory Specification (*.dat)",
            )
            try:
                with open(file_name, mode="rb") as f:
                    contents = f.read()
                    dobule_size = ctypes.sizeof(ctypes.c_double)
                    cols = int(
                        struct.unpack("d", contents[dobule_size : dobule_size * 2])[0]
                    )
                    if cols < 10:
                        self._file_name_line_edit.setText("Wrong Trajectory Size")

            except (
                FileNotFoundError,
                # json.JSONDecodeError,
                # KeyError,
                IndexError,
                ValueError,
            ):
                return

            file_name_ls = file_name.split("/")
            self._file_name_line_edit.setText(file_name_ls[-1])

        load_trajectory_button.clicked.connect(load_trajectory_file)
        layout.addWidget(load_trajectory_button, 0, 2)
        layout.addWidget(QtWidgets.QLabel("Current Trajectory"), 1, 2)
        layout.addWidget(self._file_name_line_edit, 1, 3)

        read_trajectory_button = QtWidgets.QPushButton("Send Trajectory")
        read_trajectory_button.setEnabled(False)
        self._file_name_line_edit.textChanged.connect(
            lambda str: read_trajectory_button.setEnabled(bool(str))
        )
        read_trajectory_button.clicked.connect(
            lambda _: self.load_trajectory_file.emit(self._file_name_line_edit.text())
        )
        layout.addWidget(read_trajectory_button, 0, 3)

        # self._trajectory_progress = QtWidgets.QProgressBar()
        # self._trajectory_progress.setEnabled(False)
        # layout.addWidget(load_trajectory_button, 0, 1)
        # layout.addWidget(self._file_name_line_edit, 0, 2)
        # layout.addWidget(read_trajectory_button, 0, 3)
        # layout.addWidget(QtWidgets.QLabel("Progress along trajectory"), 1, 0)
        # layout.addWidget(self._trajectory_progress, 1, 1, 1, 3)
        box.setLayout(layout)
        return box

    # Public Slot definitions
    # -----------------------------------
    #
    # Connected to signals defined by an outside class

    def toggle_trajectory(self):
        self._toggle_trajectory_button.setEnabled(False)
        self._controller_name_line_edit.setText("Trajectory")
        self._toggle_stabilization_button.setEnabled(True)

        return None

    def toggle_stabilization(self):
        self._toggle_trajectory_button.setEnabled(True)
        self._controller_name_line_edit.setText("Stabilization")
        self._toggle_stabilization_button.setEnabled(False)

        return None

    def update_local_position(self, *values):
        self._enu_box.display(*values)

    def update_local_velocity(self, *values):
        self._vel_box.display(*values)

    def update_lla(self, *values):
        self._lla_box.display(*values)

    def update_rpy(self, *values):
        self._rpy_box.display(*values)

    def update_state(self, connected, armed, mode):
        self._is_armed = armed
        connectivity_str = ["Disconnected", "Connected"]
        connectivity_colors = ["yellow", "green"]
        self._connected_lbl.setText(connectivity_str[int(connected)])
        self._connected_lbl.set_color(connectivity_colors[int(connected)])
        armed_str = ["Disarmed", "Armed"]
        armed_colors = ["Green", "Red"]
        self._armed_lbl.setText(armed_str[int(self._is_armed)])
        self._armed_lbl.set_color(armed_colors[int(self._is_armed)])
        self._arming_button.setText("Disarm" if self._is_armed else "Arm")
        self._set_arming_button_style()
        self._mode_lbl.setText(mode)

    def update_nsats(self, value):
        self._nsat_box.display(value)

    def update_battery(self, percentage, voltage):
        self._battery_level.setValue(percentage * 100)
        self._voltage_level.setText("Voltage : %4.1f" % voltage)

    def update_setpoints(self, index, *values):
        self._setpoints.setCurrentIndex(index)
        self._sp_boxes[index].display(*values)

    def update_traj_progress(self, progress):
        # progress < 0 signals no trajectory loaded
        self._trajectory_progress.setDisabled(progress < 0)
        self._toggle_trajectory_button.setDisabled(progress < 0)

        self._trajectory_progress.setValue(min(max(progress, 0), 100))
        self._toggle_trajectory_button.setText(
            "%s trajectory" % ("Start" if progress <= 0 else "Stop")
        )
        self._toggle_trajectory_button.setStyleSheet(
            """QPushButton {
    color : %s;
    background-color: %s;
    font-weight: bold;
}"""
            % (("black", "white") if progress <= 0 else ("white", "red"))
        )
        self.update_traj_progress_to_mw.emit(progress)

    # Private Slot Definitions
    # ------------------------
    #
    # These are connected to signals defined in this class

    def _toggle_odom_topic(self):
        if "odom" not in self._receiver.subs:
            topic = self._odometry_line_edit.text()
            if not topic:
                return
            self.update_odom_topic.emit(topic)
            self._odometry_line_edit.clear()
            self._odometry_line_edit.setPlaceholderText(topic)
            self._odom_toggle_button.setText("Use local position")
        else:
            self.update_odom_topic.emit("")
            self._odometry_line_edit.setPlaceholderText("")
            self._odom_toggle_button.setText("Use odometry")

    def _copy_position(self):
        values = self._enu_box.array_values
        yaw_value = self._rpy_box.array_values[-1]

        if values != 3:
            for e, v in zip(self._refs_line_edits, values):
                assert isinstance(e, QtWidgets.QLineEdit)
                e.setText("%.2f" % v)
        self._refs_line_edits[-1].setText("%.2f" % yaw_value)
