from __future__ import annotations
from typing import TYPE_CHECKING,Type
from PySide6.QtWidgets import QFileDialog, QMessageBox
from lxml import etree
import os

import desiteRuleCreator.Filehandling
from desiteRuleCreator import __version__ as project_version
from desiteRuleCreator.Windows import popups,graphs_window
from desiteRuleCreator.data import constants, classes

if TYPE_CHECKING:
    from desiteRuleCreator.main_window import MainWindow


def save_clicked(main_window:MainWindow) -> str:
    if main_window.save_path is None or not main_window.save_path.endswith("xml"):
        path = save_as_clicked(main_window)
    else:
        save(main_window.project, main_window.save_path)
        path = main_window.save_path
    return path


def save_as_clicked(main_window:MainWindow) -> str:
    if main_window.save_path is not None:
        base_path = os.path.dirname(main_window.save_path)
        path = \
            QFileDialog.getSaveFileName(main_window, "Save XML",base_path, "xml Files (*.DRCxml *.xml )")[0]
    else:
        path = QFileDialog.getSaveFileName(main_window, "Save XML", "", "xml Files ( *.DRCxml *.xml)")[0]

    if path:
        save(main_window.project,path)
        main_window.save_path = path
    return path


def save(project:classes.Project, path:str) -> None:
    def add_parent(xml_item:etree._Element, item: classes.Object|classes.PropertySet|classes.Attribute) -> None:
        if item.parent is not None:
            xml_item.set(constants.PARENT, str(item.parent.identifier))
        else:
            xml_item.set(constants.PARENT, constants.NONE)

    def add_predefined_property_sets() -> None:
        xml_grouping = etree.SubElement(xml_project, constants.PREDEFINED_PSETS)
        predefined_psets = [pset for pset in classes.PropertySet if pset.object == None]
        for predefined_pset in predefined_psets:
            add_property_set(predefined_pset,xml_grouping)

    def add_objects() -> None:

        def add_object(obj: classes.Object, xml_parent) -> None:
            def add_ifc_mapping():
                xml_ifc_mappings = etree.SubElement(xml_object, constants.IFC_MAPPINGS)
                for mapping in obj.ifc_mapping:
                    xml_ifc_mapping = etree.SubElement(xml_ifc_mappings, constants.IFC_MAPPING)
                    xml_ifc_mapping.text = mapping
                pass

            xml_object = etree.SubElement(xml_parent, constants.OBJECT)
            xml_object.set(constants.NAME, obj.name)
            xml_object.set(constants.IDENTIFIER, str(obj.identifier))
            xml_object.set("is_concept", str(obj.is_concept))
            add_parent(xml_object, obj)

            add_ifc_mapping()
            xml_property_sets = etree.SubElement(xml_object, constants.PROPERTY_SETS)
            for property_set in obj.property_sets:
                add_property_set(property_set, xml_property_sets)

            xml_scripts = etree.SubElement(xml_object, constants.SCRIPTS)
            for script in obj.scripts:
                script: classes.Script = script
                xml_script = etree.SubElement(xml_scripts, constants.SCRIPT)
                xml_script.set(constants.NAME, script.name)
                xml_script.text = script.code

        xml_grouping = etree.SubElement(xml_project,constants.OBJECTS)
        for obj in sorted(classes.Object,key=lambda x:x.name):
            add_object(obj,xml_grouping)

    def add_property_set(property_set: classes.PropertySet, xml_parent:etree._Element) -> None:
        def add_attribute(attribute: classes.Attribute, xml_pset: etree._Element) -> None:
            def add_value(attribute: classes.Attribute, xml_attribute: etree._Element) -> None:
                values = attribute.value
                for value in values:
                    xml_value = etree.SubElement(xml_attribute, "Value")
                    if attribute.value_type == constants.RANGE:
                        xml_from = etree.SubElement(xml_value, "From")
                        xml_to = etree.SubElement(xml_value, "To")
                        xml_from.text = str(value[0])
                        if len(value) > 1:
                            xml_to.text = str(value[1])
                    else:
                        xml_value.text = str(value)

            xml_attribute = etree.SubElement(xml_pset, constants.ATTRIBUTE)
            xml_attribute.set(constants.NAME, attribute.name)
            xml_attribute.set(constants.DATA_TYPE, attribute.data_type)
            xml_attribute.set(constants.VALUE_TYPE, attribute.value_type)
            xml_attribute.set(constants.IDENTIFIER, str(attribute.identifier))
            xml_attribute.set(constants.CHILD_INHERITS_VALUE, str(attribute.child_inherits_values))
            xml_attribute.set(constants.REVIT_MAPPING,str(attribute.revit_name))
            add_parent(xml_attribute, attribute)
            obj = attribute.property_set.object
            if obj is not None and attribute == obj.ident_attrib:
                ident = True
            else:
                ident = False

            xml_attribute.set(constants.IS_IDENTIFIER, str(ident))
            add_value(attribute, xml_attribute)

        xml_pset = etree.SubElement(xml_parent, constants.PROPERTY_SET)
        xml_pset.set(constants.NAME, property_set.name)
        xml_pset.set(constants.IDENTIFIER, str(property_set.identifier))
        add_parent(xml_pset, property_set)

        xml_attributes = etree.SubElement(xml_pset,constants.ATTRIBUTES)
        for attribute in property_set.attributes:
            add_attribute(attribute, xml_attributes)

    def add_node(node: graphs_window.Node,xml_nodes:etree._Element) -> None:
        xml_node = etree.SubElement(xml_nodes, constants.NODE)
        xml_node.set(constants.IDENTIFIER,str(node.uuid))
        xml_node.set(constants.OBJECT.lower(), str(node.object.identifier))
        if node.parent_node is not None:
            xml_node.set(constants.PARENT, str(node.parent_node.uuid))
        else:
            xml_node.set(constants.PARENT,constants.NONE)
        xml_node.set(constants.X_POS,str(node.x()))
        xml_node.set(constants.Y_POS,str(node.y()))
        xml_node.set(constants.IS_ROOT,str(node.is_root))
        connection_type = node.aggregation.connection_dict.get(node.aggregation.parent)
        if connection_type is not None:
            xml_node.set(constants.CONNECTION,str(connection_type))
        else:
            xml_node.set(constants.CONNECTION, constants.NONE)

    xml_project = etree.Element(constants.PROJECT)
    xml_project.set(constants.NAME, str(project.name))
    xml_project.set(constants.VERSION, str(project.version))
    xml_project.set(constants.AUTHOR,str(project.author))

    add_predefined_property_sets()
    add_objects()

    xml_nodes = etree.SubElement(xml_project, constants.NODES)

    for node in graphs_window.Node._registry:
        add_node(node,xml_nodes)

    tree = etree.ElementTree(xml_project)

    with open(path, "wb") as f:
        tree.write(f, pretty_print=True, encoding="utf-8", xml_declaration=True)

    project.reset_changed()


def close_event(main_window:MainWindow, event):
    status = main_window.project.changed
    if status:
        reply = popups.msg_close()
        if reply == QMessageBox.Save:
            path = desiteRuleCreator.Filehandling.save_file.save_clicked(main_window)
            if not path or path is None:
                return False
            else:
                return True
        elif reply == QMessageBox.No:
            return True
        else:
            return False
    else:
        return True
