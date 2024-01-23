from __future__ import annotations
from typing import TYPE_CHECKING, Type

import som_gui

if TYPE_CHECKING:
    from som_gui.tool import MainWindow, Popups, Project


def set_main_window(window, main_window_tool: Type[MainWindow]):
    main_window_tool.set(window)


def create_menus(main_window_tool: Type[MainWindow]):
    menu_dict = main_window_tool.get_menu_dict()
    menu_bar = main_window_tool.get_menu_bar()
    menu_dict["menu"] = menu_bar
    for menu in menu_dict["submenu"]:
        main_window_tool.create_actions(menu, menu_bar)


def fill_old_menus(main_window_tool: Type[MainWindow]):
    """
    fill menus of functions / windows that aren't refactored
    """
    from som_gui.filehandling import export as fh_export
    from som_gui.windows.modelcheck import modelcheck_window
    from som_gui.windows.project_phases import gui as project_phase_window
    main_window = som_gui.MainUi.window
    main_window_tool.add_action("Datei/Export/Vestra", lambda: fh_export.export_vestra_mapping(main_window))
    main_window_tool.add_action("Datei/Export/Card1", lambda: fh_export.export_card_1(main_window))
    main_window_tool.add_action("Datei/Export/Excel", lambda: fh_export.export_excel(main_window))
    main_window_tool.add_action("Datei/Export/Allplan", lambda: fh_export.export_allplan_excel(main_window))
    main_window_tool.add_action("Datei/Export/Abkürzungen", lambda: fh_export.export_desite_abbreviation(main_window))
    main_window_tool.add_action("Datei/Mappings", lambda: main_window.open_mapping_window())
    main_window_tool.add_action("Datei/Leistungsphasen", lambda: project_phase_window.ProjectPhaseWindow(main_window))
    main_window_tool.add_action("Modelle/Modellprüfung", lambda: modelcheck_window.ModelcheckWindow(main_window))
    main_window_tool.add_action("Modelle/Gruppen Generieren", lambda: main_window.open_grouping_window())
    main_window_tool.add_action("Modelle/Modellprüfung", lambda: modelcheck_window.ModelcheckWindow(main_window))
    main_window_tool.add_action("Modelle/Informationen einlesen", lambda: main_window.open_attribute_import_window())
    main_window_tool.add_action("Vordefinierte Psets/Anzeigen", lambda: main_window.open_predefined_pset_window())
    main_window_tool.add_action("Bauwerksstruktur/Anzeigen", lambda: main_window.open_aggregation_window)

    main_window_tool.add_action("Desite/Lesezeichen", lambda: fh_export.export_bookmarks(main_window))
    main_window_tool.add_action("Desite/Mapping Script", lambda: fh_export.export_mapping_script(main_window))
