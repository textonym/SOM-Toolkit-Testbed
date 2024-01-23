from __future__ import annotations
import som_gui.core.tool
import som_gui
from typing import TYPE_CHECKING, Callable
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMenuBar

if TYPE_CHECKING:
    from som_gui.module.main_window.prop import MainWindowProperties, MenuDict


class MainWindow(som_gui.core.tool.MainWindow):
    @classmethod
    def get_menu_bar(cls) -> QMenuBar:
        return cls.get().menubar

    @classmethod
    def test_call(cls):
        print("TEST")

    @classmethod
    def get_menu_dict(cls) -> MenuDict:
        prop = cls.get_main_menu_properties()
        return prop.menu_dict

    @classmethod
    def create_actions(cls, menu_dict: MenuDict):
        def iter_menus(d: MenuDict, parent: QMenu | QMenuBar):
            menu = d["menu"]
            parent.addMenu(menu)
            for action in d["actions"]:
                menu.addAction(action)
            for sd in d["submenu"]:
                iter_menus(sd, menu)

        menu_bar = cls.get_menu_bar()
        for action in menu_dict["actions"]:
            menu_bar.addAction(action)
        for sub_menu_dict in menu_dict["submenu"]:
            iter_menus(sub_menu_dict, menu_bar)

    @classmethod
    def add_menu(cls, menu_path: str) -> MenuDict:
        menu_steps = menu_path.split("/")
        menu_dict = cls.get_menu_dict()
        focus_dict = menu_dict
        parent = cls.get().menubar
        for index, menu_name in enumerate(menu_steps):
            if not menu_name in {menu["name"] for menu in focus_dict["submenu"]}:
                menu = QMenu(parent)
                menu.setTitle(menu.tr(menu_name))
                d = {
                    "name":    menu_name,
                    "submenu": list(),
                    "actions": list(),
                    "menu":    menu
                }
                focus_dict["submenu"].append(d)
            sub_menus = {menu["name"]: menu for menu in focus_dict["submenu"]}
            focus_dict = sub_menus[menu_name]
            parent = focus_dict["menu"]
        return focus_dict

    @classmethod
    def add_action(cls, menu_path: str, function: Callable):
        menu_steps = menu_path.split("/")
        menu_dict = cls.add_menu("/".join(menu_steps[:-1]))
        action = QAction(menu_dict["menu"])
        action.setText(action.tr(menu_steps[-1]))
        action.triggered.connect(function)
        menu_dict["actions"].append(action)

    @classmethod
    def get_main_menu_properties(cls) -> MainWindowProperties:
        return som_gui.MainWindowProperties

    @classmethod
    def get(cls):
        return som_gui.MainUi.ui

    @classmethod
    def set(cls, window):
        prop = cls.get_main_menu_properties()
        prop.active_main_window = window
