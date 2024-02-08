from __future__ import annotations
from som_gui.core import attribute_table as core
from som_gui import tool
import som_gui
from PySide6.QtWidgets import QTableWidget

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui import AttributeTable


def connect():
    core.add_basic_attribute_columns(tool.Attribute, tool.AttributeTable)
    som_gui.MainUi.ui.table_attribute.itemDoubleClicked.connect(
        lambda item: core.attribute_double_clicked(item, tool.Attribute, tool.PropertySet))


def connect_table(table: AttributeTable):
    table.customContextMenuRequested.connect(
        lambda pos: core.context_menu(table, pos, tool.PropertySet, tool.AttributeTable))


def on_new_project():
    pass


def table_paint_event(table: QTableWidget):
    core.paint_attribute_table(table, tool.AttributeTable)
