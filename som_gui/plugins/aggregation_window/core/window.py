from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Type
from PySide6.QtCore import Qt
from SOMcreator import Aggregation

if TYPE_CHECKING:
    from som_gui.plugins.aggregation_window import tool as aw_tool
    from som_gui import tool
from PySide6.QtCore import QCoreApplication


def create_main_menu_actions(window: Type[aw_tool.Window], main_window: Type[tool.MainWindow]):
    from som_gui.plugins.aggregation_window.module.window import trigger
    action = main_window.add_action2(None, "BSWindow", trigger.open_window)
    window.set_action("open_window", action)


def retranslate_ui(window: Type[aw_tool.Window],util:Type[tool.Util] ):
    action = window.get_action("open_window")
    action.setText(QCoreApplication.translate("Aggregation", "Building Structure"))

    aggregation_window = window.get_window()
    if not aggregation_window:
        return
    aggregation_window.ui.retranslateUi(aggregation_window)
    title = util.get_window_title(QCoreApplication.translate("Aggregation", "Building Structure"))
    aggregation_window.setWindowTitle(title)


def paint_event(window: Type[aw_tool.Window]) -> None:
    logging.debug(f"Paint Aggregation Window")
    status_bar = window.get_status_bar()
    new_status_bar_text = window.calculate_statusbar_text()
    if status_bar.currentMessage() != new_status_bar_text:
        status_bar.showMessage(new_status_bar_text)


def create_window(window: Type[aw_tool.Window], view: Type[aw_tool.View]) -> None:
    if window.get_window() is not None:
        aggregation_window = window.get_window()
        aggregation_window.show()
        return

    aggregation_window = window.create_window()
    view.set_view(aggregation_window.ui.graphicsView)
    window.connect_menu(aggregation_window)
    from ..module.window import trigger
    trigger.retranslate_ui()
    aggregation_window.show()


def remove_filter(window: Type[aw_tool.Window]):
    window.remove_filter()

def create_new_scene(window: Type[aw_tool.Window], view: Type[aw_tool.View]) -> None:
    name = QCoreApplication.translate("Aggregation", "Undefined")
    scene, scene_name = view.create_scene(name)
    update_combo_box(window, view)
    window.set_combo_box(scene_name)


def delete_active_scene(window: Type[aw_tool.Window], view: Type[aw_tool.View]) -> None:
    view.delete_scene(view.get_active_scene())
    update_combo_box(window, view)


def update_combo_box(window: Type[aw_tool.Window], view: Type[aw_tool.View]) -> None:
    combo_box = window.get_combo_box()
    if combo_box is None:
        return
    existing_texts = window.get_combo_box_texts()
    allowed_scenes = window.get_allowed_scenes()
    wanted_texts = [view.get_scene_name(scene) for scene in allowed_scenes if view.get_scene_name(scene) is not None]
    new_texts = set(wanted_texts).difference(set(existing_texts))
    delete_texts = set(existing_texts).difference(set(wanted_texts))
    if new_texts:
        combo_box.addItems(sorted(new_texts))
        combo_box.model().sort(0, Qt.AscendingOrder)
    if delete_texts:
        for delete_text in delete_texts:
            index = combo_box.findText(delete_text)
            if index < 0:
                continue
            combo_box.removeItem(index)


def combobox_changed(window: Type[aw_tool.Window], view: Type[aw_tool.View]) -> None:
    text = window.get_combo_box_text()
    scene = view.get_scene_by_name(text)
    logging.debug(f"Activate {scene}")
    if scene is None:
        name = QCoreApplication.translate("Aggregation", "Undefined")
        scene, scene_name = view.create_scene(name)
    view.activate_scene(scene)


def filter_scenes(window: Type[aw_tool.Window], view: Type[aw_tool.View], search: Type[tool.Search],
                  popup: Type[tool.Popups]) -> None:
    allowed_scenes = window.get_allowed_scenes()
    scene_list = view.get_all_scenes()
    filter_object = search.search_object()
    if filter_object is None:
        return
    for scene in scene_list:
        objects_in_scene = view.get_objects_in_scene(scene)
        if filter_object not in objects_in_scene:
            allowed_scenes.remove(scene)
    if not allowed_scenes:
        title = QCoreApplication.translate("Aggregation", "Object DNE")
        text = QCoreApplication.translate("Aggregation", "Object doesn't exist in any View")

        popup.create_warning_popup(text, title)
        return
    window.set_filter_object(filter_object)
    window.activate_filter()
    window.set_allowed_scenes(allowed_scenes)
    update_combo_box(window, view)


def search_aggregation(view: Type[aw_tool.View], search: Type[tool.Search], popup: Type[tool.Popups]) -> None:
    obj = search.search_object()
    if obj is None:
        return
    scene = view.get_active_scene()
    nodes = {node for node in view.get_nodes_in_scene(scene) if node.aggregation.object == obj}
    if not nodes:
        text = QCoreApplication.translate("Aggregation", "No Node linked to Object")
        popup.create_warning_popup(text)
        return
    scene.clearSelection()
    [n.setSelected(True) for n in nodes]
    view.zoom_to_selected()


def copy_selected_nodes(view: Type[aw_tool.View]) -> None:
    nodes = view.get_selected_nodes()
    bounding_box = view.get_bounding_box_of_nodes(nodes)
    copy_list = list()
    for node in nodes:
        pos = node.sceneBoundingRect().topLeft() - bounding_box.topLeft()
        copy_list.append((node.aggregation, pos))
    view.set_copy_list(copy_list)


def paste_nodes(view: Type[aw_tool.View]) -> None:
    scene = view.get_active_scene()
    cursor_pos = view.get_scene_cursor_pos()
    aggregation_dict: dict[Aggregation, Aggregation] = dict()

    for old_aggregation, local_pos in view.get_copy_list():
        new_aggregation = Aggregation(old_aggregation.object)
        aggregation_dict[old_aggregation] = new_aggregation
        node_pos = cursor_pos + local_pos
        view.add_aggregation_to_import_list(scene, new_aggregation, node_pos)

    for old_aggregation, new_aggregation in aggregation_dict.items():
        if old_aggregation.parent in aggregation_dict:
            aggregation_dict[old_aggregation.parent].add_child(new_aggregation, old_aggregation.parent_connection)
            new_aggregation.set_parent(aggregation_dict[old_aggregation.parent], old_aggregation.parent_connection)
    scene.update()


def request_scene_rename(window: Type[aw_tool.Window], view: Type[aw_tool.View], popups: Type[tool.Popups]):
    scene = view.get_active_scene()
    scene_name = view.get_scene_name(scene)
    title = QCoreApplication.translate("Aggregation", "Rename View")
    text = QCoreApplication.translate("Aggregation", "New Name:")
    new_name = popups._request_text_input(title, text, scene_name,
                                          window.get_window())
    if new_name:
        view.set_scene_name(scene, new_name)
    update_combo_box(window, view)
    window.get_combo_box().setCurrentText(new_name)
