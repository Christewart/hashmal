from collections import defaultdict
import os
import time

from PyQt4.QtGui import *
from PyQt4 import QtCore

from hashmal_lib.core import chainparams
from config import Config
from plugin_handler import PluginHandler
from settings_dialog import SettingsDialog, ChainparamsComboBox, LayoutChanger
from widgets.script import ScriptEditor
from help_widgets import QuickTips
from gui_utils import script_file_filter, hashmal_style, floated_buttons, monospace_font
from plugin_manager import PluginManager
from plugins import BaseDock
from downloader import DownloadController

known_script_formats = ['Human', 'Hex']

class HashmalMain(QMainWindow):
    # Signals
    # Emitted when the list of user's layouts changes.
    layoutsChanged = QtCore.pyqtSignal()

    def __init__(self, app):
        super(HashmalMain, self).__init__()
        self.app = app
        self.app.setStyleSheet(hashmal_style)
        self.changes_saved = True
        # {Qt.DockWidgetArea: [dock0, dock1, ...], ...}
        self.dock_orders = defaultdict(list)
        self.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)

        self.config = Config()

        QtCore.QCoreApplication.setOrganizationName('mazaclub')
        QtCore.QCoreApplication.setApplicationName('hashmal')
        self.qt_settings = QtCore.QSettings()

        active_params = self.config.get_option('chainparams', 'Bitcoin')
        chainparams.set_to_preset(active_params)

        self.download_controller = DownloadController()

        self.setDockNestingEnabled(True)
        # Plugin Handler loads plugins and handles their dock widgets.
        self.plugin_handler = PluginHandler(self)
        self.plugin_handler.load_plugins()
        self.plugin_handler.do_default_layout()

        # Filename of script being edited.
        self.filename = ''
        # The last text that we saved.
        self.last_saved = ''
        self.create_script_editor()
        # Set up script editor font.
        script_font = self.qt_settings.value('editor/font', defaultValue=QtCore.QVariant('default')).toString()
        if script_font == 'default':
            font = monospace_font
        else:
            font = QFont()
            font.fromString(script_font)
        self.script_editor.setFont(font)

        self.create_menubar()
        self.create_toolbar()
        self.create_actions()
        self.new_script()
        self.statusBar().setVisible(True)
        self.statusBar().messageChanged.connect(self.change_status_bar)

        self.restoreState(self.qt_settings.value('toolLayout/default/state').toByteArray())
        self.restoreGeometry(self.qt_settings.value('toolLayout/default/geometry').toByteArray())
        self.script_editor.setFocus()

        if self.qt_settings.value('quickTipsOnStart', defaultValue=QtCore.QVariant(True)).toBool():
            QtCore.QTimer.singleShot(500, self.do_quick_tips)

    def sizeHint(self):
        return QtCore.QSize(800, 500)

    def create_menubar(self):
        menubar = QMenuBar()

        file_menu = menubar.addMenu('&File')
        file_menu.addAction('&New', self.new_script).setShortcut(QKeySequence.New)
        file_menu.addAction('Save As...', self.save_script_as).setShortcut(QKeySequence.SaveAs)
        file_menu.addAction('&Open', self.open_script).setShortcut(QKeySequence.Open)
        file_menu.addAction('&Save', self.save_script).setShortcut(QKeySequence.Save)
        file_menu.addAction('&Quit', self.close)

        # Script actions
        script_menu = menubar.addMenu('&Script')
        script_menu.addAction('&Evaluate', self.plugin_handler.evaluate_current_script)
        script_menu.addAction('&Copy Hex', self.script_editor.copy_hex)

        # Settings and tool toggling
        tools_menu = menubar.addMenu('&Tools')
        tools_menu.addAction('&Settings', lambda: SettingsDialog(self).exec_())
        tools_menu.addAction('&Plugin Manager', lambda: PluginManager(self).exec_())
        tools_menu.addSeparator()
        self.plugin_handler.create_menu(tools_menu)

        help_menu = menubar.addMenu('&Help')
        help_menu.addAction('&About', self.do_about)
        help_menu.addAction('&Quick Tips', self.do_quick_tips)

        self.setMenuBar(menubar)

    def show_status_message(self, msg, error=False):
        self.statusBar().showMessage(msg, 3000)
        if error:
            self.statusBar().setProperty('hasError', True)
        else:
            self.statusBar().setProperty('hasError', False)
        self.style().polish(self.statusBar())

    def change_status_bar(self, new_msg):
        # Unset hasError if an error is removed.
        if not new_msg and self.statusBar().property('hasError'):
            self.statusBar().setProperty('hasError', False)
        self.style().polish(self.statusBar())

    def on_text_changed(self):
        s = str(self.script_editor.toPlainText())
        saved = False
        if s == self.last_saved and self.filename:
            saved = True

        title = ''.join(['Hashmal - ', self.filename])
        if not saved:
            title = ''.join([title, ' *'])
        self.setWindowTitle(title)
        self.changes_saved = saved

    def closeEvent(self, event):
        # Save layout if configured to.
        if self.qt_settings.value('saveLayoutOnExit', defaultValue=QtCore.QVariant(False)).toBool():
            self.qt_settings.setValue('toolLayout/default', self.saveState())

        if self.close_script():
            event.accept()
        else:
            event.ignore()

    def close_script(self):
        # Confirm discarding changes if an unsaved file is open.
        if str(self.script_editor.toPlainText()) and not self.changes_saved:
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle('Hashmal - Save Changes')
            text = 'Do you want to save this script before closing?'
            if self.filename:
                text = 'Do you want to save your changes to ' + self.filename + ' before closing?'
            msgbox.setText(text)
            msgbox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            msgbox.setDefaultButton(QMessageBox.Save)
            msgbox.setIcon(QMessageBox.Question)
            result = msgbox.exec_()
            if result == QMessageBox.Save:
                self.save_script()
            elif result == QMessageBox.Cancel:
                return False
        self.filename = ''
        self.changes_saved = True
        self.script_editor.clear()
        return True

    def new_script(self, filename=''):
        if not self.close_script():
            return
        if not filename:
            base_name = ''.join(['Untitled-', str(time.time()), '.coinscript'])
            filename = os.path.expanduser(base_name)
        self.load_script(filename)

    def save_script(self):
        filename = self.filename
        if not filename:
            filename = str(QFileDialog.getSaveFileName(self, 'Save script', filter=script_file_filter))
            if not filename: return

        if not filename.endswith('.coinscript'):
            filename += '.coinscript'

        self.filename = filename
        with open(self.filename, 'w') as file:
            file.write(str(self.script_editor.toPlainText()))
        self.last_saved = str(self.script_editor.toPlainText())
        self.on_text_changed()

    def save_script_as(self):
        filename = str(QFileDialog.getSaveFileName(self, 'Save script as', filter=script_file_filter))
        if not filename: return

        if not filename.endswith('.coinscript'):
            filename += '.coinscript'
        self.filename = filename
        self.save_script()

    def open_script(self):
        filename = str(QFileDialog.getOpenFileName(self, 'Open script', '.', filter=script_file_filter))
        if not filename:
            return
        if self.close_script():
            self.load_script(filename)

    def load_script(self, filename):
        if os.path.exists(filename):
            self.filename = filename
            with open(self.filename,'r') as file:
                self.script_editor.setPlainText(file.read())
        else:
            self.script_editor.clear()
        self.last_saved = str(self.script_editor.toPlainText())
        self.on_text_changed()


    def create_script_editor(self):
        vbox = QVBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.setWhatsThis('Use this to change the format that script editor displays and writes scripts in.')
        self.format_combo.addItems(known_script_formats)
        self.script_editor = ScriptEditor(self)
        self.script_editor.textChanged.connect(self.on_text_changed)
        self.script_editor.setWhatsThis('The script editor lets you write transaction scripts in a human-readable format. You can also write and edit scripts in their raw, hex-encoded format if you prefer.')

        self.format_combo.currentIndexChanged.connect(lambda index: self.script_editor.set_format(known_script_formats[index]))

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel('Format: '))
        hbox.addWidget(self.format_combo)
        hbox.addStretch(1)
        vbox.addLayout(hbox)
        vbox.addWidget(self.script_editor)

        w = QWidget()
        w.setLayout(vbox)
        self.setCentralWidget(w)

    def create_toolbar(self):
        toolbar = QToolBar('Toolbar')
        toolbar.setObjectName('Toolbar')

        whats_this_button = QPushButton('&?')
        whats_this_button.setMaximumWidth(20)
        whats_this_button.setWhatsThis('This button activates What\'s This? mode.\n\nIn What\'s This? mode, you can click something you are not familiar with and a description of it will be shown if one exists.')
        whats_this_button.clicked.connect(lambda: QWhatsThis.enterWhatsThisMode())
        toolbar.addWidget(whats_this_button)
        toolbar.addSeparator()

        params_combo = ChainparamsComboBox(self.config)
        params_combo.setWhatsThis('Use this to change the chainparams preset. Chainparams presets are described in the settings dialog.')
        params_combo.setMinimumWidth(120)
        params_form = QFormLayout()
        params_form.setContentsMargins(0, 0, 0, 0)
        params_form.addRow('Chainparams:', params_combo)
        params_selector = QWidget()
        params_selector.setLayout(params_form)
        params_selector.setToolTip('Change chainparams preset')

        toolbar.addWidget(params_selector)
        toolbar.addSeparator()

        layout_changer = LayoutChanger(self)
        layout_changer.setWhatsThis('Use this to load or save layouts. Layouts allow you to quickly access the tools you need for a given purpose.')
        layout_changer.layout_combo.setMinimumWidth(120)
        layout_changer.delete_button.setVisible(False)
        for i in [layout_changer.load_button, layout_changer.save_button]:
            i.setMaximumWidth(50)
            i.setMaximumHeight(23)
        layout_form = QFormLayout()
        layout_form.setContentsMargins(0, 0, 0, 0)
        layout_form.addRow('Layout:', layout_changer)
        layout_widget = QWidget()
        layout_widget.setLayout(layout_form)
        layout_widget.setToolTip('Load or save a layout')
        toolbar.addWidget(layout_widget)

        self.addToolBar(toolbar)

    def create_actions(self):
        hide_dock = QAction('Hide Dock', self)
        hide_dock.setShortcut(QKeySequence(QKeySequence.Close))
        hide_dock.triggered.connect(self.hide_current_dock)
        self.addAction(hide_dock)

        move_left_dock = QAction('Move Left', self)
        move_left_dock.setShortcut(QKeySequence(QKeySequence.Back))
        move_left_dock.triggered.connect(lambda: self.move_one_dock(reverse=True))
        self.addAction(move_left_dock)

        move_right_dock = QAction('Move Right', self)
        move_right_dock.setShortcut(QKeySequence(QKeySequence.Forward))
        move_right_dock.triggered.connect(self.move_one_dock)
        self.addAction(move_right_dock)

    def move_one_dock(self, reverse=False):
        """Move focus to the next or previous dock."""
        w = get_active_dock()
        if not w: return
        docks = filter(lambda dock: dock.isVisible(), self.dock_orders[self.dockWidgetArea(w)])
        index = docks.index(w)
        if reverse:
            if index == 0:
                index = len(docks)
            docks[index - 1].needsFocus.emit()
        else:
            if index >= len(docks) - 1:
                index = -1
            docks[index + 1].needsFocus.emit()

    def tabifyDockWidget(self, bottom, top):
        """Overloaded method for purposes of remembering dock positions."""
        docks = self.dock_orders[self.dockWidgetArea(bottom)]
        area = self.dockWidgetArea(bottom)
        if len(docks) == 0:
            docks.append(bottom)
        super(HashmalMain, self).tabifyDockWidget(bottom, top)
        idx = docks.index(bottom)
        docks.insert(idx + 1, top)

    def do_about(self):
        d = QDialog(self)
        vbox = QVBoxLayout()
        about_label = QLabel()
        about_label.setWordWrap(True)

        txt = []
        txt.append(' '.join([
                'Hashmal is an IDE for Bitcoin transaction scripts.',
                'Its purpose is to make it easier to write, evaluate, and learn about transaction scripts.'
        ]))
        txt.append('Hashmal is intended for cryptocurrency developers and power users.')
        txt.append('Use at own risk!')
        txt = '\n\n'.join(txt)

        about_label.setText(txt)

        close_button = QPushButton('Close')
        close_button.clicked.connect(d.close)
        btn_box = floated_buttons([close_button])

        vbox.addWidget(about_label)
        vbox.addLayout(btn_box)
        d.setLayout(vbox)
        d.setWindowTitle('About Hashmal')
        d.exec_()

    def do_quick_tips(self):
        QuickTips(self).exec_()

    def hide_current_dock(self):
        w = get_active_dock()
        if not w: return
        docks = filter(lambda dock: dock.isVisible(), self.tabifiedDockWidgets(w))
        w.toggleViewAction().trigger()
        if docks:
            docks[0].needsFocus.emit()

def get_active_dock():
    """Get the dock widget that currently has focus."""
    w = QApplication.focusWidget()
    while w and w.__class__:
        if issubclass(w.__class__, BaseDock):
            return w
        w = w.parentWidget()
