from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from time import time, sleep
from typing import TYPE_CHECKING,Type

import ifcopenshell
import openpyxl
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem, QWidget
from SOMcreator import classes
from SOMcreator import constants as som_constants
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.dimensions import ColumnDimension, DimensionHolder
from openpyxl.worksheet.table import Table, TableStyleInfo

from ..icons import get_icon
from ..ifc_modification import modelcheck, sql, issues
from ..qt_designs import ui_modelcheck
from ..settings import get_ifc_path, get_issue_path, set_ifc_path, set_issue_path
if TYPE_CHECKING:
    from ..main_window import MainWindow

FILE_SPLIT = "; "


class IfcWindow(QWidget):
    def __init__(self, main_window: MainWindow):
        super(IfcWindow, self).__init__()
        self.main_window = main_window
        self.widget = ui_modelcheck.Ui_Form()
        self.widget.setupUi(self)
        self.setWindowIcon(get_icon())
        self.widget.button_ifc.clicked.connect(self.ifc_file_dialog)
        self.widget.button_export.clicked.connect(self.export_file_dialog)
        pset, attribute = self.get_main_attribute()
        self.widget.line_edit_ident_pset.setText(pset)
        self.widget.line_edit_ident_attribute.setText(attribute)
        self.widget.label_ifc_missing.hide()
        self.widget.label_export_missing.hide()
        self.widget.label_export_missing.setStyleSheet("QLabel { color : red; }")
        self.widget.label_ifc_missing.setStyleSheet("QLabel { color : red; }")
        self.widget.line_edit_ifc.textEdited.connect(self.widget.label_ifc_missing.hide)
        self.widget.line_edit_export.textEdited.connect(self.widget.label_export_missing.hide)
        self.widget.progress_bar.hide()
        self.widget.label_status.hide()

        if get_ifc_path():
            self.widget.line_edit_ifc.setText(get_ifc_path())
        if get_issue_path():
            self.widget.line_edit_export.setText(get_issue_path())

        self.active_threads = 0
        self.thread_pool = QThreadPool()
        self.widget.button_run.clicked.connect(self.accept)
        self.widget.button_close.clicked.connect(self.close_button_clicked)
        self.show()
        self.start_time = None
        self.end_time = None
        self.task_is_running = False

    def connect_runner(self,runner: IfcRunner):
        runner.signaller.started.connect(self.on_started)
        runner.signaller.finished.connect(self.on_finished)
        runner.signaller.progress.connect(self.update_progress_bar)
        runner.signaller.status.connect(self.update_status)
        self.widget.button_close.clicked.connect(runner.abort)


    def close_button_clicked(self):
        if not self.task_is_running:
            self.hide()

    def accept(self) -> None:
        allow = True
        if not self.get_ifc_path():
            if self.widget.line_edit_ifc.text():
                self.widget.label_ifc_missing.setText("Path doesn't exist!")
            else:
                self.widget.label_ifc_missing.setText("IFC File Path is missing!")
            self.widget.label_ifc_missing.show()
            allow = False
        export_path = self.widget.line_edit_export.text()
        if not export_path:
            self.widget.label_export_missing.setText("Export Path is missing!")
            self.widget.label_export_missing.show()
            allow = False

        elif not os.path.exists(os.path.dirname(export_path)):
            self.widget.label_export_missing.setText("Path doesn't exist!")
            self.widget.label_export_missing.show()
            allow = False

        if allow:
            self.start_task()

    def ifc_file_dialog(self):
        file_text = "IFC Files (*.ifc *.IFC);;"
        path = QFileDialog.getOpenFileNames(self, "IFC-Files", get_ifc_path(), file_text)[0]
        if not path:
            return
        set_ifc_path(path)
        self.widget.line_edit_ifc.setText(FILE_SPLIT.join(path))

    def export_file_dialog(self):
        file_text = "Excel File (*.xlsx);;"
        path = QFileDialog.getSaveFileName(self, "Issue-Excel", get_issue_path(), file_text)[0]
        if not path:
            return
        set_issue_path(path)
        self.widget.line_edit_export.setText(path)

    def get_ifc_path(self) -> list[str]:
        paths = self.widget.line_edit_ifc.text().split(FILE_SPLIT)
        result = list()
        for path in paths:
            if not os.path.exists(path):
                logging.error(f"IFC-File does not exist: '{path}'")
            else:
                result.append(path)
        return result

    def get_main_attribute(self) -> (str, str):
        proj = self.main_window.project
        ident_attributes = dict()
        ident_psets = dict()
        for obj in proj.objects:
            ident_pset = obj.ident_attrib.property_set.name
            ident_attribute = obj.ident_attrib.name
            if not ident_pset in ident_psets:
                ident_psets[ident_pset] = 0
            if not ident_attribute in ident_attributes:
                ident_attributes[ident_attribute] = 0
            ident_psets[ident_pset] += 1
            ident_attributes[ident_attribute] += 1

        ident_attribute = (sorted(ident_attributes.items(), key=lambda x: x[1]))
        ident_pset = (sorted(ident_psets.items(), key=lambda x: x[1]))
        if ident_attribute and ident_pset:
            return ident_pset[0][0], ident_attribute[0][0]
        else:
            return "", ""

    def on_started(self, path):
        logging.info(f"Start {path}")
        self.active_threads += 1

    def on_finished(self, path):
        self.active_threads -= 1
        logging.info(f"Finish {path}")
        logging.info(f"active Threads: {self.active_threads}")
        if self.active_threads == 0:
            self.end_task()

    def start_task(self) -> tuple:
        self.task_is_running = True
        self.start_time = time()
        self.widget.button_run.setEnabled(False)
        self.widget.button_close.setText("Abort")
        proj = self.main_window.project
        ifc = self.get_ifc_path()
        pset = self.widget.line_edit_ident_pset.text()
        attribute = self.widget.line_edit_ident_attribute.text()
        export_path = self.widget.line_edit_export.text()
        self.widget.label_status.show()
        self.widget.progress_bar.show()
        self.widget.progress_bar.reset()
        self.thread_pool.clear()
        return proj,ifc,pset,attribute,export_path

    def end_task(self):
        logging.info("Task Done")
        self.end_time = time()
        logging.info(f"{self.end_time - self.start_time}")

        self.widget.button_run.setEnabled(True)
        self.widget.button_close.setText("Close")
        self.task_is_running = False

    def update_progress_bar(self, value):
        self.widget.progress_bar.setValue(value)

    def update_status(self, value):
        self.widget.label_status.setText(value)

class IfcRunner(QRunnable):

    def __init__(self, ifc_paths:str, project:classes.Project, main_pset:str, main_attribute:str,export_path:str,function_name:str):
        self.signaller = Signaller()
        super(IfcRunner, self).__init__()
        self.ifc_paths = ifc_paths
        self.project = project
        self.main_pset = main_pset
        self.main_attribute = main_attribute
        self.export_path = export_path

        self.is_aborted = False
        self.object_count: int = 0
        self.checked_objects: int = 0
        self.function_name = function_name

    def increment_progress(self,text= "",increment_value = 1):
        if self.is_aborted:
            print(f"Is Aborted")
            self.set_abort_status()
            return
        self.checked_objects += increment_value
        progress = int(self.checked_objects / self.object_count * 100)
        self.signaller.progress.emit(progress)
        self.signaller.status.emit(f"{text} [{self.checked_objects}/{self.object_count}]")

    def get_check_file_list(self) -> set[str]:
        check_list = set()
        if not isinstance(self.ifc_paths, list):
            if not isinstance(self.ifc_paths, str):
                return check_list
            if not os.path.isfile(self.ifc_paths):
                return check_list
            check_list.add(self.ifc_paths)

        else:
            for path in self.ifc_paths:
                if os.path.isdir(path):
                    for file in os.listdir(path):
                        file_path = os.path.join(path, file)
                        check_list.add(file_path)
                else:
                    check_list.add(path)

        return set(file for file in check_list if file.lower().endswith(".ifc"))

    def set_abort_status(self):
        self.signaller.status.emit(f"{self.function_name} abgebrochen")
        self.signaller.progress.emit(0)

    def abort(self):
        self.is_aborted = True
        self.set_abort_status()


    def run(self) -> None:
        self.signaller.started.emit(self.ifc_paths)
        files = self.get_check_file_list()
        for file in files:
            if self.is_aborted:
                continue
            self.run_file_function(file)

        if self.is_aborted:
            self.signaller.finished.emit("ABORT")
            return
        self.signaller.finished.emit(self.ifc_paths)
        self.signaller.status.emit(f"{self.function_name} Abgeschlossen!")

    def run_file_function(self, file_path) -> ifcopenshell.file:
        self.base_name = os.path.basename(file_path)
        self.signaller.status.emit(f"Import {self.base_name}")
        self.signaller.progress.emit(0)
        sleep(0.1)

        ifc = ifcopenshell.open(file_path)
        self.signaller.status.emit(f"Import Done!")
        sleep(0.1)
        return ifc

class Signaller(QObject):
    started = Signal(str)
    finished = Signal(str)
    progress = Signal(int)
    status = Signal(str)
