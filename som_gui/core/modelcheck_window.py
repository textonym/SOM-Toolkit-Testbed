from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Type
import os

from PySide6.QtWidgets import QDialogButtonBox

import SOMcreator
from PySide6.QtCore import Qt

from som_gui.module.project.constants import CLASS_REFERENCE
from som_gui.module.modelcheck.constants import ISSUE_PATH

if TYPE_CHECKING:
    from som_gui import tool
    from PySide6.QtGui import QStandardItem
    from PySide6.QtCore import QItemSelectionModel, QModelIndex
    from som_gui.tool.ifc_importer import IfcImportRunner

def open_window(modelcheck_window: Type[tool.ModelcheckWindow], util: Type[tool.Util], project: Type[tool.Project]):
    if modelcheck_window.is_window_allready_build():
        modelcheck_window.get_window().show()
        return

    proj = project.get()
    window = modelcheck_window.create_window()
    main_pset_name, main_attribute_name = proj.get_main_attribute()
    util.fill_main_attribute(window.ui.main_attribute_widget, main_pset_name, main_attribute_name)
    util.fill_file_selector(window.ui.widget_import, "IFC Pfad", "IFC Files (*.ifc *.IFC);;", "modelcheck_files")
    util.fill_file_selector(window.ui.widget_export, "Export Pfad", "Excel FIle (*xlsx);;", "modelcheck_export",
                            request_save=True)
    modelcheck_window.connect_buttons()
    modelcheck_window.connect_object_tree(window.ui.object_tree)
    modelcheck_window.set_progressbar_visible(False)
    modelcheck_window.reset_butons()
    window.show()


def cancel_clicked(modelcheck_window: Type[tool.ModelcheckWindow]):
    modelcheck_window.close_window()


def abort_clicked(modelcheck_window: Type[tool.ModelcheckWindow], modelcheck: Type[tool.Modelcheck],
                  ifc_importer: Type[tool.IfcImporter]):
    import_pool = ifc_importer.get_threadpool()
    check_pool = modelcheck_window.get_modelcheck_threadpool()
    logging.debug(f"Cancel clicked. Active threads: {import_pool.activeThreadCount()}|{check_pool.activeThreadCount()}")

    if ifc_importer.import_is_running():
        for runner in modelcheck_window.get_properties().ifc_import_runners:
            runner.is_aborted = True
    if modelcheck_window.modelcheck_is_running() or ifc_importer.import_is_running():
        modelcheck_window.set_progressbar_visible(False)
        modelcheck.abort()
        modelcheck_window.reset_butons()


def run_clicked(modelcheck_window: Type[tool.ModelcheckWindow],
                modelcheck: Type[tool.Modelcheck], modelcheck_results: Type[tool.ModelcheckResults],
                ifc_importer: Type[tool.IfcImporter], project: Type[tool.Project], util: Type[tool.Util]):
    ifc_paths, export_path, main_pset, main_attribute = modelcheck_window.read_inputs()
    inputs_are_valid = ifc_importer.check_inputs(ifc_paths, main_pset, main_attribute)
    export_path_is_valid = modelcheck_window.check_export_path(export_path)

    if not inputs_are_valid or not export_path_is_valid:
        return

    modelcheck_window.show_buttons(QDialogButtonBox.StandardButton.Abort)
    modelcheck.reset_abort()
    modelcheck.set_main_pset_name(main_pset)
    modelcheck.set_main_attribute_name(main_attribute)
    modelcheck_results.set_export_path(export_path)

    pool = ifc_importer.create_thread_pool()
    pool.setMaxThreadCount(3)
    modelcheck.init_sql_database(util.create_tempfile(".db"))
    modelcheck.reset_guids()
    modelcheck.build_ident_dict(set(project.get().get_objects(filter=True)))
    modelcheck_window.set_progress(0)
    modelcheck_window.set_progressbar_visible(True)
    for path in ifc_paths:
        modelcheck_window.set_status(f"Import '{os.path.basename(path)}'")
        runner = modelcheck_window.create_import_runner(path)
        modelcheck_window.connect_ifc_import_runner(runner)
        pool.start(runner)


def ifc_import_started(runner: IfcImportRunner, modelcheck_window: Type[tool.ModelcheckWindow]):
    modelcheck_window.set_progressbar_visible(True)
    modelcheck_window.set_status(f"Import '{os.path.basename(runner.path)}'")
    modelcheck_window.set_progress(0)


def ifc_import_finished(runner: IfcImportRunner, modelcheck_window: Type[tool.ModelcheckWindow],
                        modelcheck: Type[tool.Modelcheck]):
    """
    creates and runs Modelcheck Runnable
    """

    modelcheck_window.destroy_import_runner(runner)
    modelcheck_window.set_status(f"Import Abgeschlossen")

    modelcheck.set_ifc_name(os.path.basename(runner.path))
    modelcheck_runner = modelcheck.create_modelcheck_runner(runner.ifc)

    modelcheck_window.connect_modelcheck_runner(modelcheck_runner)
    modelcheck.set_current_runner(modelcheck_runner)
    modelcheck_window.get_modelcheck_threadpool().start(modelcheck_runner)


def modelcheck_finished(modelcheck_window: Type[tool.ModelcheckWindow], modelcheck: Type[tool.Modelcheck],
                        modelcheck_results: Type[tool.ModelcheckResults]):
    if modelcheck.is_aborted():
        modelcheck_window.reset_butons()
        return

    time.sleep(0.2)
    if not modelcheck_window.modelcheck_is_running():
        modelcheck_results.last_modelcheck_finished()
        modelcheck_window.reset_butons()
    else:
        logging.info(f"Prüfung von Datei abgeschlossen, nächste Datei ist dran.")



def paint_object_tree(modelcheck_window: Type[tool.ModelcheckWindow], project: Type[tool.Project]):
    logging.debug(f"Repaint Modelcheck Object Tree")
    root_objects = set(project.get_root_objects(True))
    tree = modelcheck_window.get_object_tree()
    invisible_root_entity = tree.model().invisibleRootItem()
    modelcheck_window.fill_object_tree(root_objects, invisible_root_entity, tree.model(), tree)
    if modelcheck_window.is_initial_paint:
        modelcheck_window.resize_object_tree()


def object_check_changed(item: QStandardItem, modelcheck_window: Type[tool.ModelcheckWindow]):
    obj = item.data(CLASS_REFERENCE)
    if item.column() != 0:
        return

    modelcheck_window.set_item_check_state(obj, item.checkState())
    paint_pset_tree(modelcheck_window)


def object_selection_changed(selection_model: QItemSelectionModel, modelcheck_window: Type[tool.ModelcheckWindow]):
    selected_indexes = selection_model.selectedIndexes()
    if not selected_indexes:
        return
    index: QModelIndex = selected_indexes[0]
    obj: SOMcreator.Object = index.data(CLASS_REFERENCE)
    modelcheck_window.set_selected_object(obj)
    paint_pset_tree(modelcheck_window)
    if obj.ident_value:
        text = f"{obj.name} [{obj.ident_value}]"
    else:
        text = obj.name
    modelcheck_window.set_pset_tree_title(text)
    modelcheck_window.show_pset_tree_title(True)


def paint_pset_tree(modelcheck_window: Type[tool.ModelcheckWindow]):
    logging.debug(f"Repaint Modelcheck Pset Tree")
    obj = modelcheck_window.get_selected_object()
    if obj is None:
        return
    cs = modelcheck_window.get_item_check_state(obj)
    enabled = True if cs == Qt.CheckState.Checked else False
    modelcheck_window.fill_pset_tree(set(obj.get_property_sets(filter=True)), enabled,
                                     modelcheck_window.get_pset_tree())


def object_tree_conect_menu_requested(pos, widget, modelcheck_window: Type[tool.ModelcheckWindow]):
    actions = [
        ["Ausklappen", lambda: modelcheck_window.expand_selection(widget)],
        ["Einklappen", lambda: modelcheck_window.collapse_selection(widget)],
        ["Aktivieren", lambda: modelcheck_window.check_selection(widget)],
        ["Deaktivieren", lambda: modelcheck_window.uncheck_selection(widget)]
    ]

    modelcheck_window.create_context_menu(pos, actions, widget)
