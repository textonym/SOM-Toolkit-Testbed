from __future__ import annotations

import os.path
from typing import TYPE_CHECKING, Callable
from som_gui import tool
from PySide6.QtCore import QRunnable, Signal, QObject
from PySide6.QtWidgets import QLabel, QProgressBar
import tempfile

if TYPE_CHECKING:
    from som_gui.module.modelcheck.prop import ModelcheckProperties
import som_gui.core.tool
import SOMcreator
import datetime
import logging
import re
import sqlite3
from ifcopenshell import entity_instance
import ifcopenshell
from som_gui.module.modelcheck.constants import *
from ifcopenshell.util import element as ifc_el
from SOMcreator import value_constants
from som_gui.data import constants
from som_gui.module.modelcheck import trigger

rev_datatype_dict = {
    str:   "IfcText/IfcLabel",
    bool:  "IfcBoolean",
    int:   "IfcInteger",
    float: "IfcReal"
}


class ModelcheckRunner(QRunnable):
    def __init__(self, ifc_file: ifcopenshell.file):
        super().__init__()
        self.file = ifc_file
        self.signaller = Signaller()

    def run(self):
        trigger.start_modelcheck(self.file)
        self.signaller.finished.emit()


class Signaller(QObject):
    finished = Signal()
    status = Signal(str)
    progress = Signal(int)

class Modelcheck(som_gui.core.tool.Modelcheck):
    @classmethod
    def get_group_count(cls) -> int:
        return len(cls.get_properties().group_parent_dict)

    @classmethod
    def increment_checked_items(cls):
        checked_count = cls.get_object_checked_count()
        object_count = tool.Modelcheck.get_object_count()
        old_progress_value = int(checked_count / object_count * 100)
        new_progress_value = int((checked_count + 1) / object_count * 100)
        cls.set_object_checked_count(checked_count + 1)
        if new_progress_value > old_progress_value:
            cls.set_progress(new_progress_value)

    @classmethod
    def set_status(cls, text: str):
        cls.get_properties().runner.signaller.status.emit(text)

    @classmethod
    def set_progress(cls, value: int):
        cls.get_properties().runner.signaller.progress.emit(value)

    @classmethod
    def entity_is_in_group(cls, entity: ifcopenshell.entity_instance):
        return bool([assignment for assignment in getattr(entity, "HasAssignments", []) if
                     assignment.is_a("IfcRelAssignsToGroup")])

    @classmethod
    def get_entities_without_group_assertion(cls, ifc: ifcopenshell.file) -> list[ifcopenshell.entity_instance]:
        return [entity for entity in ifc.by_type("IfcElement") if
                not [assignment for assignment in getattr(entity, "HasAssignments", []) if
                     assignment.is_a("IfcRelAssignsToGroup")]]

    @classmethod
    def get_element_count(cls) -> int:
        return len(cls.get_properties().group_parent_dict.keys())

    @classmethod
    def subelements_have_doubling_identifier(cls, entity: ifcopenshell):
        """Checks if there are multiple classes of subelements in a Group that have the same Matchkey"""
        sub_idents = [cls.get_ident_value(sub_group) for sub_group in cls.get_sub_entities(entity)]
        return len(set(sub_idents)) != len(sub_idents)

    @classmethod
    def get_sub_entities(cls, entity: ifcopenshell.entity_instance) -> set[ifcopenshell.entity_instance]:
        group_dict = cls.get_properties().group_dict
        return group_dict.get(entity) if entity in group_dict else set()

    @classmethod
    def set_sub_entities(cls, entity: ifcopenshell.entity_instance, sub_entities: set[ifcopenshell.entity_instance]):
        cls.get_properties().group_dict[entity] = sub_entities

    @classmethod
    def get_parent_entity(cls, entity: ifcopenshell.entity_instance) -> ifcopenshell.entity_instance | None:
        return cls.get_properties().group_parent_dict.get(entity)

    @classmethod
    def set_parent_entity(cls, entity: ifcopenshell.entity_instance,
                          parent_entity: ifcopenshell.entity_instance | None):
        cls.get_properties().group_parent_dict[entity] = parent_entity

    @classmethod
    def is_parent_allowed(cls, entity: ifcopenshell.entity_instance, parent_entity: ifcopenshell.entity_instance):
        object_rep = cls.get_object_representation(entity)
        parent_object_rep = cls.get_object_representation(parent_entity)
        allowed_parents = cls.get_allowed_parents(object_rep)
        return bool(parent_object_rep.aggregations.intersection(allowed_parents))

    @classmethod
    def get_allowed_parents(cls, obj: SOMcreator.Object):
        def _loop_parent(el: SOMcreator.classes.Aggregation) -> SOMcreator.classes.Aggregation:
            if el.parent_connection != value_constants.INHERITANCE:
                return el.parent
            else:
                return _loop_parent(el.parent)

        return set(_loop_parent(aggreg) for aggreg in obj.aggregations)

    @classmethod
    def entity_should_be_tested(cls, entity: ifcopenshell.entity_instance) -> bool:
        obj = cls.get_object_representation(entity)
        if obj is None:
            return False
        return obj in cls.get_data_dict()

    @classmethod
    def get_object_representation(cls, entity: ifcopenshell.entity_instance) -> SOMcreator.Object | None:
        identifier = cls.get_ident_value(entity)
        return cls.get_ident_dict().get(identifier)

    @classmethod
    def build_group_structure(cls, ifc: ifcopenshell.file):
        cls.get_properties().group_dict = dict()
        cls.get_properties().group_parent_dict = dict()

        for entity in cls.get_root_groups(ifc):
            cls.iterate_group_structure(entity)
            cls.set_parent_entity(entity, None)

    @classmethod
    def build_ident_dict(cls, objects: set[SOMcreator.Object]):
        cls.get_properties().ident_dict = {o.ident_value: o for o in objects}

    @classmethod
    def build_data_dict(cls, data: dict[SOMcreator.Object | SOMcreator.PropertySet | SOMcreator.Attribute, bool]):
        output_data_dict = dict()
        for obj in tool.Project.get_all_objects():

            if not data.get(obj):
                continue
            for property_set in obj.get_all_property_sets():
                if not data.get(property_set):
                    continue
                attribute_list = list()
                for attribute in property_set.get_all_attributes():
                    if not data.get(attribute):
                        continue
                    attribute_list.append(attribute)

                if not attribute_list:
                    continue
                if obj not in output_data_dict:
                    output_data_dict[obj] = {property_set: attribute_list}
                else:
                    output_data_dict[obj][property_set] = attribute_list
        cls.set_data_dict(output_data_dict)


    @classmethod
    def create_modelcheck_runner(cls, ifc_file) -> ModelcheckRunner:
        return ModelcheckRunner(ifc_file)

    @classmethod
    def is_root_group(cls, group: ifcopenshell.stream_entity) -> bool:
        parent_assignment = []
        for assignement in group.HasAssignments:
            if not assignement.is_a("IfcRelAssignsToGroup"):
                continue
            parent_assignment.append(assignement)

        if not parent_assignment:
            return True
        return False

    @classmethod
    def get_root_groups(cls, ifc: ifcopenshell.file) -> list[ifcopenshell.entity_instance]:
        return [group for group in ifc.by_type("IfcGroup") if cls.is_root_group(group)]

    @classmethod
    def iterate_group_structure(cls, entity: entity_instance):
        relationships = getattr(entity, "IsGroupedBy", [])
        for relationship in relationships:
            sub_entities: set[ifcopenshell.entity_instance] = set(se for se in relationship.RelatedObjects)
            cls.set_sub_entities(entity, sub_entities)
            for sub_entity in sub_entities:  # IfcGroup or IfcElement
                cls.set_parent_entity(sub_entity, entity)
                if sub_entity.is_a("IfcGroup"):
                    cls.iterate_group_structure(sub_entity)

    #######################################################################################
    ###############################Modelchecks#############################################
    #######################################################################################

    @classmethod
    def check_values(cls, value, attribute: SOMcreator.Attribute):
        check_dict = {value_constants.LIST:   cls.check_list, value_constants.RANGE: cls.check_range,
                      value_constants.FORMAT: cls.check_format, constants.GER_LIST: cls.check_list,
                      constants.GER_VALUE:    cls.check_values, constants.GER_FORMAT: cls.check_format,
                      constants.GER_RANGE:    cls.check_range}
        func = check_dict[attribute.value_type]
        func(value, attribute)
        cls.check_datatype(value, attribute)

    @classmethod
    def check_datatype(cls, value, attribute):
        guid = cls.get_active_guid()
        data_type = value_constants.DATATYPE_DICT[attribute.data_type]
        element_type = cls.get_active_element_type()
        if not isinstance(value, data_type):
            cls.datatype_issue(guid, attribute, element_type, rev_datatype_dict[type(value)], value)

    @classmethod
    def check_format(cls, value, attribute):
        element_type = cls.get_active_element_type()
        guid = cls.get_active_guid()
        is_ok = False
        for form in attribute.value:
            if re.match(form, value) is not None:
                is_ok = True
        if not is_ok:
            cls.format_issue(guid, attribute, element_type)

    @classmethod
    def check_list(cls, value, attribute):
        if not attribute.value:
            return
        element_type = cls.get_active_element_type()
        guid = cls.get_active_guid()
        if str(value) not in [str(v) for v in attribute.value]:
            cls.list_issue(guid, attribute, element_type, value)

    @classmethod
    def check_range(cls, value, attribute):
        is_ok = False
        element_type = cls.get_active_element_type()
        guid = cls.get_active_guid()
        for possible_range in attribute:
            if min(possible_range) <= value <= max(possible_range):
                is_ok = True
        if not is_ok:
            cls.range_issue(guid, attribute, element_type, value)

    @classmethod
    def check_for_attributes(cls, element, obj: SOMcreator.Object):

        element_type = cls.get_active_element_type()
        guid = cls.get_active_guid()
        data_dict = cls.get_data_dict()
        pset_dict = ifc_el.get_psets(element)

        for property_set in data_dict[obj]:
            pset_name = property_set.name
            if pset_name not in pset_dict:
                cls.property_set_issue(element.GlobalId, pset_name, element_type)
                continue

            for attribute in data_dict[obj][property_set]:
                attribute_name = attribute.name
                if attribute.name not in pset_dict[pset_name]:
                    cls.attribute_issue(element.GlobalId, pset_name, attribute_name, element_type)
                    continue

                value = pset_dict[pset_name][attribute_name]
                if value is None:
                    cls.empty_value_issue(guid, pset_name, attribute.name, element_type)
                else:
                    cls.check_values(value, attribute)

    ###################################################################################
    ################################ISSUES#############################################
    ###################################################################################

    @classmethod
    def datatype_issue(cls, guid, attribute, element_type, datatype: str, value):
        description = f"{element_type} besitzt den falschen Datentype ({datatype} nicht erlaubt)" \
                      f" {attribute.property_set.name}:{attribute.name}"
        issue_nr = DATATYPE_ISSUE
        cls.add_issues(guid, description, issue_nr, attribute, value=value)

    @classmethod
    def format_issue(cls, guid, attribute, element_type, value):
        description = f"{element_type} besitzt nicht das richtige Format für {attribute.property_set.name}:{attribute.name}"
        issue_nr = ATTRIBUTE_VALUE_ISSUES
        cls.add_issues(guid, description, issue_nr, attribute, value=value)

    @classmethod
    def list_issue(cls, guid, attribute, element_type, value):
        description = f"{element_type} besitzt nicht den richtigen Wert für {attribute.property_set.name}:{attribute.name}"
        issue_nr = ATTRIBUTE_VALUE_ISSUES
        cls.add_issues(guid, description, issue_nr, attribute, value=value)

    @classmethod
    def range_issue(cls, guid, attribute, element_type, value):
        description = f"""{element_type}  {attribute.property_set.name}:{attribute.name} 
                      ist nicht in den vorgegebenen Wertebereichen"""
        issue_nr = ATTRIBUTE_VALUE_ISSUES
        cls.add_issues(guid, description, issue_nr, attribute, value=value)

    @classmethod
    def property_set_issue(cls, guid, pset_name, element_type):
        description = f"{element_type} besitzt nicht das PropertySet {pset_name}"
        issue_nr = PROPERTY_SET_ISSUE
        cls.add_issues(guid, description, issue_nr, None, pset_name=pset_name)

    @classmethod
    def empty_value_issue(cls, guid, pset_name, attribute_name, element_type):
        description = f"{element_type} hat ein leeres Attribut {pset_name}:{attribute_name}"
        issue_nr = ATTRIBUTE_EXIST_ISSUE
        cls.add_issues(guid, description, issue_nr, None, pset_name=pset_name,
                       attribute_name=attribute_name)

    @classmethod
    def attribute_issue(cls, guid, pset_name, attribute_name, element_type):
        description = f"{element_type} besitzt nicht das Attribut {pset_name}:{attribute_name}"
        issue_nr = ATTRIBUTE_EXIST_ISSUE
        cls.add_issues(guid, description, issue_nr, None, pset_name=pset_name,
                       attribute_name=attribute_name)

    @classmethod
    def ident_issue(cls, guid, pset_name, attribute_name):
        element_type = cls.get_active_element_type()
        description = f"{element_type} besitzt nicht das Zuweisungsattribut {pset_name}:{attribute_name}"
        issue_nr = IDENT_ATTRIBUTE_ISSUE
        cls.add_issues(guid, description, issue_nr, None, pset_name=pset_name,
                       attribute_name=attribute_name)

    @classmethod
    def ident_pset_issue(cls, guid, pset_name):
        element_type = cls.get_active_element_type()
        description = f"{element_type}  besitzt nicht das PropertySet {pset_name}"
        issue_nr = IDENT_PROPERTY_SET_ISSUE
        cls.add_issues(guid, description, issue_nr, None, pset_name=pset_name)

    @classmethod
    def ident_unknown(cls, guid, pset_name, attribute_name, value):
        element_type = cls.get_active_element_type()
        description = f"""{element_type} Wert von Matchkey {pset_name}:{attribute_name}
                      konnte nicht in SOM gefunden werden"""
        issue_nr = IDENT_ATTRIBUTE_UNKNOWN
        cls.add_issues(guid, description, issue_nr, None, pset_name=pset_name,
                       attribute_name=attribute_name, value=value)

    @classmethod
    def guid_issue(cls, guid, file1, file2):
        description = f'GUID kommt in Datei "{file1}" und "{file2}" vor'
        issue_nr = GUID_ISSUE
        cls.add_issues(guid, description, issue_nr, None)

    # GROUP ISSUES
    @classmethod
    def subgroup_issue(cls, child_ident):
        description = f"Gruppensammler besitzt falsche Untergruppe ({child_ident} nicht erlaubt)"
        issue_nr = SUBGROUP_ISSUE
        cls.add_issues(cls.get_active_guid(), description, issue_nr, None)

    @classmethod
    def empty_group_issue(cls, element):
        description = f"Gruppe besitzt keine Subelemente "
        issue_nr = EMPTY_GROUP_ISSUE
        cls.add_issues(element.GlobalId, description, issue_nr, None)

    @classmethod
    def parent_issue(cls, element: entity_instance, parent_element: entity_instance):
        main_pset_name = cls.get_main_pset_name()
        main_attribute_name = cls.get_main_attribute_name()
        element_type = cls.get_active_element_type()
        ident_value = ifc_el.get_pset(parent_element, main_pset_name, main_attribute_name)
        description = f"{element_type} besitzt die falsche Elternklasse ({ident_value} nicht erlaubt)"
        issue_nr = PARENT_ISSUE
        cls.add_issues(element.GlobalId, description, issue_nr, None)

    @classmethod
    def no_group_issue(cls, element):
        description = f"Element hat keine Gruppenzuweisung"
        issue_nr = NO_GROUP_ISSUE
        cls.add_issues(element.GlobalId, description, issue_nr, None)

    @classmethod
    def repetetive_group_issue(cls, element):
        description = f"Gruppe besitzt mehrere Subelemente mit der selben Bauteilklassifikation"
        issue_nr = REPETETIVE_GROUP_ISSUE
        cls.add_issues(element.GlobalId, description, issue_nr, None)

    ################
    ###### SQL #####
    ################

    @classmethod
    def create_new_sql_database(cls) -> str:
        db_path = os.path.abspath(tempfile.NamedTemporaryFile(suffix=".db").name)
        cls.set_database_path(db_path)
        logging.info(f"Database: {db_path}")

        cls.connect_to_data_base(db_path)
        cls.create_tables()
        cls.disconnect_from_data_base()

        return db_path

    @classmethod
    def remove_existing_issues(cls, creation_date):
        cursor = cls.get_cursor()
        project_name = tool.Project.get().name
        file_name = cls.get_ifc_name()

        query = f"""
        DELETE FROM issues
        WHERE short_description in (
        SELECT short_description from issues
        INNER JOIN entities  on issues.GUID = entities.GUID
        where issues.creation_date = '{creation_date}'
        AND entities.Project = '{project_name}'
        AND entities.datei = '{file_name}')
        """
        cursor.execute(query)
        cls.commit_sql()

    @classmethod
    def create_tables(cls):
        cursor = cls.get_cursor()
        # entities
        cursor.execute('''
                  CREATE TABLE IF NOT EXISTS entities
                  ([GUID_ZWC] CHAR(64) PRIMARY KEY,[GUID] CHAR(64),[Name] CHAR(64),[Project] TEXT, [ifc_type] TEXT,[x_pos] DOUBLE,
                  [y_pos] DOUBLE,[z_pos] DOUBLE,[datei] TEXT,[bauteilKlassifikation] TEXT)
                  ''')
        cls.commit_sql()

        # issues
        cursor.execute('''
                  CREATE TABLE IF NOT EXISTS issues
                  ([creation_date] TEXT,[GUID] CHAR(64), [short_description] TEXT,[issue_type] INT,
                  [PropertySet] TEXT, [Attribut] TEXT, [Value] Text)
                  ''')
        cls.commit_sql()

    @classmethod
    def add_issues(cls, guid, description, issue_type, attribute, pset_name="", attribute_name="", value=""):
        cursor = cls.get_cursor()
        guid = cls.transform_guid(guid, True)
        date = datetime.date.today()
        if attribute is not None:
            pset_name = attribute.property_set.name
            attribute_name = attribute.name
        cursor.execute(f'''
              INSERT INTO issues (creation_date,GUID,short_description,issue_type,PropertySet,Attribut,Value)
                    VALUES
                    ('{date}','{guid}','{description}',{issue_type},'{pset_name}','{attribute_name}','{value}')
              ''')
        cls.commit_sql()

    @classmethod
    def transform_guid(cls, guid: str, add_zero_width: bool):
        """Fügt Zero Width Character ein weil PowerBI (WARUM AUCH IMMER FÜR EIN BI PROGRAMM?????) Case Insensitive ist"""
        if add_zero_width:
            return re.sub(r"([A-Z])", lambda m: m.group(0) + u"\u200B", guid)
        else:
            return guid

    @classmethod
    def db_create_entity(cls, element: entity_instance, bauteil_klasse):
        cursor = cls.get_cursor()
        file_name = cls.get_ifc_name()
        project = tool.Project.get_project_name()
        guid_zwc = cls.transform_guid(element.GlobalId, True)
        guid = cls.transform_guid(element.GlobalId, False)
        name = element.Name
        ifc_type = element.is_a()
        center = [0, 0, 0]
        guids = cls.get_guids()
        if guid in guids:
            if file_name != guids[guid]:
                cls.guid_issue(guid, file_name, guids[guid])
            return
        else:
            guids[guid] = file_name
        try:
            cursor.execute(f'''
                      INSERT INTO entities (GUID_ZWC,GUID,Name,Project,ifc_type,x_pos,y_pos,z_pos,datei,bauteilKlassifikation)
                            VALUES
                            ('{guid_zwc}','{guid}','{name}','{project}','{ifc_type}',{center[0]},{center[1]},{center[2]},'{file_name}','{bauteil_klasse}')
                      ''')
            cls.commit_sql()
        except sqlite3.IntegrityError:
            logging.warning("Integrity Error -> Element allready exists")
            pass

    ## Getter and Setter
    @classmethod
    def get_ident_value(cls, entity: entity_instance):
        return ifc_el.get_pset(entity, cls.get_main_pset_name(), cls.get_main_attribute_name())

    @classmethod
    def get_attribute_value(cls, entity: entity_instance, pset_name: str, attribute_name: str):
        psets = ifc_el.get_psets(entity)
        pset = psets.get(pset_name)
        if not pset:
            return None
        return pset.get(attribute_name)

    @classmethod
    def is_pset_existing(cls, entity: entity_instance, pset_name: str):
        psets = ifc_el.get_psets(entity)
        return psets.get(pset_name) is not None

    @classmethod
    def is_attribute_existing(cls, entity: entity_instance, pset_name: str, attribute_name: str) -> bool:
        psets = ifc_el.get_psets(entity)
        pset = psets.get(pset_name)
        if not pset:
            return False
        return attribute_name in pset

    @classmethod
    def get_active_guid(cls) -> str:
        return cls.get_active_element().GlobalId

    @classmethod
    def get_active_element(cls):
        return cls.get_properties().active_element

    @classmethod
    def set_active_element(cls, element: entity_instance):
        cls.get_properties().active_element = element

    @classmethod
    def get_active_element_type(cls):
        return cls.get_properties().active_element_type

    @classmethod
    def set_active_element_type(cls, value):
        cls.get_properties().active_element_type = value

    @classmethod
    def get_data_dict(cls):
        return cls.get_properties().data_dict

    @classmethod
    def set_data_dict(cls, value):
        cls.get_properties().data_dict = value

    @classmethod
    def get_ident_dict(cls) -> dict:
        return cls.get_properties().ident_dict

    @classmethod
    def get_ifc_name(cls):
        return cls.get_properties().ifc_name

    @classmethod
    def set_ifc_name(cls, value):
        cls.get_properties().ifc_name = value

    @classmethod
    def get_main_attribute_name(cls):
        return cls.get_properties().main_attribute_name

    @classmethod
    def get_main_pset_name(cls):
        return cls.get_properties().main_pset_name

    @classmethod
    def set_main_attribute_name(cls, value: str):
        cls.get_properties().main_attribute_name = value

    @classmethod
    def set_main_pset_name(cls, value: str):
        cls.get_properties().main_pset_name = value

    @classmethod
    def get_guids(cls):
        return cls.get_properties().guids

    @classmethod
    def get_properties(cls) -> ModelcheckProperties:
        return som_gui.ModelcheckProperties

    @classmethod
    def get_database_path(cls) -> str:
        return cls.get_properties().database_path

    @classmethod
    def set_database_path(cls, path: str):
        cls.get_properties().database_path = path

    @classmethod
    def get_current_runner(cls):
        return cls.get_properties().runner

    @classmethod
    def set_current_runner(cls, runner: QRunnable):
        cls.get_properties().runner = runner


    @classmethod
    def get_object_checked_count(cls) -> int:
        return cls.get_properties().object_checked_count

    @classmethod
    def set_object_checked_count(cls, value: int):
        cls.get_properties().object_checked_count = value

    @classmethod
    def get_object_count(cls) -> int:
        return cls.get_properties().object_count

    @classmethod
    def set_object_count(cls, value: int):
        cls.get_properties().object_count = value

    @classmethod
    def is_aborted(cls):
        return cls.get_properties().abort_modelcheck

    @classmethod
    def abort(cls):
        cls.get_properties().abort_modelcheck = True

    @classmethod
    def reset_abort(cls):
        cls.get_properties().abort_modelcheck = False

    @classmethod
    def connect_to_data_base(cls, path):
        print("Connect To Database")
        conn = sqlite3.connect(path)
        cls.get_properties().connection = conn

    @classmethod
    def disconnect_from_data_base(cls):
        print("Disconnect from Database")
        cls.get_properties().connection.commit()
        cls.get_properties().connection.close()
        cls.get_properties().connection = None

    @classmethod
    def get_cursor(cls):
        return cls.get_properties().connection.cursor()

    @classmethod
    def commit_sql(cls):
        con = cls.get_properties().connection
        if con is None:
            return
        con.commit()
