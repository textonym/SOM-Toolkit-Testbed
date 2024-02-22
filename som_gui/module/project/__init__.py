import logging

import som_gui
from . import ui, trigger, prop, window, window_merge


def register():
    som_gui.ProjectProperties = prop.ProjectProperties


def load_ui_triggers():
    logging.info(f"Load Project UI Triggers")
    trigger.connect()
