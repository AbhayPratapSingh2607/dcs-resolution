from PySide6.QtWidgets import QTabWidget

from game.theater import ControlPoint, DynamicFarp, Fob
from qt_ui.models import GameModel
from qt_ui.windows.basemenu.DepartingConvoysMenu import DepartingConvoysMenu
from qt_ui.windows.basemenu.airfield.QAirfieldCommand import QAirfieldCommand
from qt_ui.windows.basemenu.farp.QFarpCommand import QFarpCommand
from qt_ui.windows.basemenu.ground_forces.QGroundForcesHQ import QGroundForcesHQ
from qt_ui.windows.basemenu.intel.QIntelInfo import QIntelInfo


class QBaseMenuTabs(QTabWidget):
    def __init__(self, cp: ControlPoint, game_model: GameModel):
        super(QBaseMenuTabs, self).__init__()

        if cp.captured.is_red:
            self.intel = QIntelInfo(cp)
            self.addTab(self.intel, "Intel")

            self.departing_convoys = DepartingConvoysMenu(cp, game_model)
            self.addTab(self.departing_convoys, "Departing Convoys")
            return

        if isinstance(cp, DynamicFarp) and cp.is_rescue_king:
            # Nothing to buy or park: just its helicopters.
            self.farp_command = QFarpCommand(cp, game_model)
            self.addTab(self.farp_command, "Rescue King")
        elif isinstance(cp, DynamicFarp):
            self.farp_command = QFarpCommand(cp, game_model)
            self.addTab(self.farp_command, "FARP")
            self.airfield_command = QAirfieldCommand(cp, game_model)
            self.addTab(self.airfield_command, "Heliport")
        elif isinstance(cp, Fob):
            self.ground_forces_hq = QGroundForcesHQ(cp, game_model)
            self.addTab(self.ground_forces_hq, "Ground Forces HQ")
            if cp.has_ground_spawns:
                self.airfield_command = QAirfieldCommand(cp, game_model)
                self.addTab(self.airfield_command, "Airfield Command")
            elif cp.has_helipads:
                self.airfield_command = QAirfieldCommand(cp, game_model)
                self.addTab(self.airfield_command, "Heliport")
        else:
            self.airfield_command = QAirfieldCommand(cp, game_model)
            self.addTab(self.airfield_command, "Airfield Command")
            if cp.can_deploy_ground_units:
                self.ground_forces_hq = QGroundForcesHQ(cp, game_model)
                self.addTab(self.ground_forces_hq, "Ground Forces HQ")
