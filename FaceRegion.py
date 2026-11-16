"""FaceRegion - Fusion 360 add-in. THIS FILE IS THE SHELL, NOT THE WORK.

Lifecycle, the toolbar button and event wiring. All the real code lives in fr_core.py
and is RE-IMPORTED FRESH on every command, so editing it takes effect on the next
click. Only changes to this file need the add-in stopped and run again.
"""

import adsk.core
import adsk.fusion

import importlib
import os
import sys
import time
import traceback

CMD_ID = 'FaceRegion_FitCylinder'
CMD_NAME = 'Fit Cylinder to Faces'
CMD_TOOLTIP = (
    'Fit the best cylinder to a marked area of a bone and create it.\n\n'
    'Mark the diaphysis by clicking where it starts and ends (any body, including '
    'organic NURBS), or by selecting faces on a faceted body. The cylinder\'s axis is the '
    'anatomical axis (Dlab-IT007, 5.4). Then use Construct > Axis Through Cylinder.'
)

ADDIN_DIR = os.path.dirname(os.path.realpath(__file__))
RES_DIR = os.path.join(ADDIN_DIR, 'resources', 'FaceRegion')
LOG_PATH = os.path.join(ADDIN_DIR, 'FaceRegion.log')

_app = None
_ui = None
_handlers = []
_controls = []


def _log(msg):
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as fh:
            fh.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass


OWN_MODULES = ('fr_core', 'fr_fit', 'fr_validate')


def _core():
    """Fresh import of the worker module. This is the hot reload.

    Fusion runs every add-in and script in ONE Python, so a module of the same name
    imported from elsewhere (e.g. a bridge job importing the source folder) would be
    picked up and reloaded from THERE. Drop any such copy, and keep this folder first
    on sys.path, so the add-in always runs its own installed files."""
    while ADDIN_DIR in sys.path:
        sys.path.remove(ADDIN_DIR)
    sys.path.insert(0, ADDIN_DIR)
    here = os.path.normcase(ADDIN_DIR)
    for name in OWN_MODULES:
        mod = sys.modules.get(name)
        if mod and os.path.normcase(os.path.dirname(os.path.realpath(mod.__file__))) != here:
            del sys.modules[name]
    if 'fr_core' in sys.modules:
        return importlib.reload(sys.modules['fr_core'])
    return importlib.import_module('fr_core')


def _fail(where):
    tb = traceback.format_exc()
    _log('%s\n%s' % (where, tb))
    if _ui:
        _ui.messageBox('%s\n\n%s\n\nFull traceback in\n%s'
                       % (where, tb.strip().splitlines()[-1], LOG_PATH), CMD_NAME)


# --------------------------------------------------------------------------- #
# command handlers - thin, they only delegate
# --------------------------------------------------------------------------- #

class _Created(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            _core().on_created(_app, cmd)
            for h, ev in ((_Execute(), cmd.execute),
                          (_Preview(), cmd.executePreview),
                          (_Changed(), cmd.inputChanged),
                          (_Validate(), cmd.validateInputs),
                          (_PreSelect(), cmd.preSelect),
                          (_Destroy(), cmd.destroy)):
                ev.add(h)
                _handlers.append(h)
        except Exception:
            _fail('Fit Cylinder could not open its dialog.')


class _Execute(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            sys.modules['fr_core'].on_execute(_app, _ui, args.command)
        except Exception:
            _fail('Fit Cylinder failed.')


class _Preview(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            sys.modules['fr_core'].on_preview(_app, args.command)
        except Exception:
            _log(traceback.format_exc())


class _Changed(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            # args.inputs may be a group's children - always go via the command
            sys.modules['fr_core'].on_input_changed(
                _app, args.input.parentCommand.commandInputs, args.input.id)
        except Exception:
            _log(traceback.format_exc())


class _Validate(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            args.areInputsValid = sys.modules['fr_core'].on_validate(args.inputs)
        except Exception:
            args.areInputsValid = False


class _PreSelect(adsk.core.SelectionEventHandler):
    def notify(self, args):
        try:
            args.isSelectable = sys.modules['fr_core'].on_pre_select(
                args.activeInput.parentCommand.commandInputs, args.selection.entity,
                args.activeInput.id)
        except Exception:
            _log(traceback.format_exc())


class _Destroy(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            sys.modules['fr_core'].on_destroy(_app)
        except Exception:
            _log(traceback.format_exc())


# --------------------------------------------------------------------------- #
# add-in entry points
# --------------------------------------------------------------------------- #

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        old = _ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_TOOLTIP, RES_DIR)
        h = _Created()
        cmd_def.commandCreated.add(h)
        _handlers.append(h)
        _controls[:] = _core().place_button(_ui, cmd_def)
        _log('started, button in %d panel(s)' % len(_controls))
    except Exception:
        _fail('FaceRegion failed to start.')


def stop(context):
    try:
        for ctrl in _controls:
            try:
                ctrl.deleteMe()
            except Exception:
                pass
        _controls[:] = []
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        _handlers[:] = []
        _log('stopped')
    except Exception:
        _fail('FaceRegion failed to stop.')
