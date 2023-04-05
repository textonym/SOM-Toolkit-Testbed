from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QMessageBox
from SOMcreator import constants, filehandling
from lxml import etree

from ..windows import popups, graphs_window
from .. import settings

if TYPE_CHECKING:
    from ..main_window import MainWindow


def add_node_pos(tree: etree.ElementTree):
    xml_group_nodes = tree.find(constants.NODES)
    node_dict = {node.aggregation.uuid: node for node in graphs_window.Node.registry}
    for xml_node in xml_group_nodes:
        uuid = xml_node.attrib.get(constants.IDENTIFIER)
        node = node_dict[uuid]
        xml_node.set(constants.X_POS, str(node.x()))
        xml_node.set(constants.Y_POS, str(node.y()))


def save_clicked(main_window: MainWindow) -> str:
    path = settings.get_file_path()
    if not os.path.exists(path) or not path.endswith("json"):
        path = save_as_clicked(main_window)
    else:
        logging.info(f"Saved project to {path}")
        main_window.project.save_json(path)
    return path


def save_as_clicked(main_window: MainWindow) -> str:
    path = settings.get_file_path()
    if not os.path.exists(path):
        path = \
            QFileDialog.getSaveFileName(main_window, "Save Project", "", constants.FILETYPE)[0]
    else:
        path = os.path.splitext(path)[0]
        path = QFileDialog.getSaveFileName(main_window, "Save Project", path, constants.FILETYPE)[0]

    if path:
        main_window.project.save_json(path)
        settings.set_file_path(path)
    return path


def close_event(main_window: MainWindow):
    status = main_window.project.changed
    if status:
        reply = popups.msg_close()
        if reply == QMessageBox.StandardButton.Save:
            path = save_clicked(main_window)
            if not path or path is None:
                return False
            else:
                return True
        elif reply == QMessageBox.StandardButton.No:
            return True
        else:
            return False
    else:
        return True
