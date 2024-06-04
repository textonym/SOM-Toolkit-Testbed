from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, QPointF

from som_gui.module.project.constants import CLASS_REFERENCE
import SOMcreator
from PySide6.QtWidgets import QTreeWidgetItem, QGraphicsRectItem
from PySide6.QtCore import QRectF
from SOMcreator.classes import Aggregation, Object
import som_gui.aggregation_window.core.tool
from som_gui.aggregation_window.module.node import ui as node_ui
from som_gui.aggregation_window.module.node import constants as node_constants
from som_gui.aggregation_window import tool as aw_tool

if TYPE_CHECKING:
    from som_gui.aggregation_window.module.node.prop import NodeProperties
    from som_gui.aggregation_window.module.view import ui as view_ui


class Node(som_gui.aggregation_window.core.tool.Node):
    @classmethod
    def set_z_level_of_node(cls, node: node_ui.NodeProxy, z_level: int) -> None:
        node.setZValue(z_level)
        node.frame.setZValue(z_level)
        node.header.setZValue(z_level)

    @classmethod
    def get_properties(cls) -> NodeProperties:
        return som_gui.NodeProperties

    @classmethod
    def increment_z_level(cls) -> int:
        cls.get_properties().z_level += 1
        return cls.get_properties().z_level

    @classmethod
    def get_z_level(cls) -> int:
        return cls.get_properties().z_level

    @classmethod
    def add_property_set_to_tree(cls, property_set: SOMcreator.PropertySet, tree_widget: node_ui.PropertySetTree):
        item = QTreeWidgetItem()
        item.setText(0, property_set.name)
        item.setData(0, CLASS_REFERENCE, property_set)
        tree_widget.addTopLevelItem(item)
        return item

    @classmethod
    def get_pset_subelement_dict(cls, item: QTreeWidgetItem):
        return {cls.get_linked_item(item.child(i)): item.child(i) for i in range(item.childCount())}

    @classmethod
    def add_attribute_to_property_set_tree(cls, attribute: SOMcreator.Attribute, property_set_item: QTreeWidgetItem):
        attribute_item = QTreeWidgetItem()
        attribute_item.setText(0, attribute.name)
        attribute_item.setData(0, CLASS_REFERENCE, attribute)
        property_set_item.addChild(attribute_item)
        return attribute_item

    @classmethod
    def create_tree_widget(cls, node: node_ui.NodeProxy) -> node_ui.PropertySetTree:
        obj = node.aggregation.object
        widget = node_ui.PropertySetTree()
        widget.setHeaderLabel("Name")
        widget.node = node
        return widget

    @classmethod
    def create_node(cls, aggregation: Aggregation):
        node = node_ui.NodeProxy()
        node_widget = node_ui.NodeWidget()
        node.setWidget(node_widget)
        node_widget.setMinimumSize(QSize(250, 150))
        node.aggregation = aggregation
        node.widget().layout().insertWidget(0, cls.create_tree_widget(node))
        cls.create_header(node)
        cls.create_frame(node)
        return node

    @classmethod
    def create_header(cls, node: node_ui.NodeProxy):
        header = node_ui.Header()
        line_width = header.pen().width()  # if ignore Linewidth: box of Node and Header won't match
        x = line_width / 2
        width = node.widget().width() - line_width
        height = node_constants.HEADER_HEIGHT
        header.setRect(QRectF(x, -height, width, height))
        node.header = header
        header.node = node

    @classmethod
    def create_frame(cls, node: node_ui.NodeProxy):
        frame = node_ui.Frame()
        rect = node.rect()
        rect.setWidth(rect.width() - frame.pen().width() / 2)
        rect.setY(rect.y() - node_constants.HEADER_HEIGHT)
        rect.setHeight(rect.height())
        rect.setX(frame.x() + frame.pen().width() / 2)
        frame.setRect(rect)
        node.frame = frame
        frame.node = node

    @classmethod
    def get_linked_item(cls, pset_tree_item: QTreeWidgetItem) -> SOMcreator.PropertySet | SOMcreator.Attribute:
        return pset_tree_item.data(0, CLASS_REFERENCE)

    @classmethod
    def get_node_from_header(cls, header: node_ui.Header) -> node_ui.NodeProxy:
        return header.node

    @classmethod
    def get_frame_from_node(cls, node: node_ui.NodeProxy) -> node_ui.Frame:
        return node.frame

    @classmethod
    def move_node(cls, node: node_ui.NodeProxy, dif: QPointF):
        node.moveBy(dif.x(), dif.y())
        frame = cls.get_frame_from_node(node)
        frame.moveBy(dif.x(), dif.y())

    @classmethod
    def get_title(cls, node: node_ui.NodeProxy, pset_name: str, attribute_name: str):
        aggregation = cls.get_aggregation_from_node(node)
        if not (pset_name and attribute_name):
            base_text = f"{aggregation.name} ({aggregation.object.abbreviation})"

            if aggregation.is_root:
                title = base_text
            else:
                title = f"{base_text}\nidGruppe: {aggregation.id_group()}"
            return title
        undef = f"{aggregation.name}\n{attribute_name}: undefined"
        obj = aggregation.object
        pset = obj.get_property_set_by_name(pset_name)
        if pset is None:
            return undef
        attribute = pset.get_attribute_by_name(attribute_name)
        if attribute is None:
            return undef

        if len(attribute.value) == 0:
            return undef
        return f"{aggregation.name}\n{attribute_name}: {attribute.value[0]}"

    @classmethod
    def get_aggregation_from_node(cls, node: node_ui.NodeProxy):
        return node.aggregation

    @classmethod
    def get_title_settings(cls):
        return cls.get_properties().title_pset, cls.get_properties().title_attribute

    @classmethod
    def set_title_settings(cls, pset_name, attribute_name):
        cls.get_properties().title_pset, cls.get_properties().title_attribute = pset_name, attribute_name

    @classmethod
    def reset_title_settings(cls):
        cls.get_properties().title_pset, cls.get_properties().title_attribute = None, None

    @classmethod
    def set_node_pos(cls, node: node_ui.NodeProxy, pos: QPointF):
        dif = pos - node.header.scenePos()
        node.header.moveBy(dif.x(), dif.y())
        cls.move_node(node, dif)

    @classmethod
    def get_node_from_tree_widget(cls, tree_widget: node_ui.PropertySetTree) -> node_ui.NodeProxy:
        return tree_widget.node

    @classmethod
    def is_node_connected_to_node(cls, node1: node_ui.NodeProxy, node2: node_ui.NodeProxy) -> bool:
        if node1.top_connection == node2:
            return True

        if node2.top_connection == node1:
            return True
        return False
