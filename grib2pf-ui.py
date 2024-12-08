#!/usr/bin/env python3
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QGridLayout, \
        QLineEdit, QCheckBox, QSpinBox, QHBoxLayout, QVBoxLayout, QToolButton, \
        QPushButton, QFileDialog, QTableView, QMessageBox, QInputDialog, \
        QComboBox, QDialog, QTreeView
from PySide6.QtCore import Qt, Signal, QModelIndex, QAbstractTableModel, \
        QMimeData, QSortFilterProxyModel, QThread
from PySide6.QtGui import QKeySequence, QClipboard, QIcon, QStandardItemModel, \
        QStandardItem

from jsonc_parser.parser import JsoncParser
import json

import sys
import os
import random
import subprocess

location = os.path.split(__file__)[0]

MIME_TYPE = "application/x.grib2pf-placefile"

class ProductsDialog(QDialog):
    def __init__(self):
        QDialog.__init__(self)

        self.selectedProduct = ""

        self.products = {}
        with open(os.path.join(location, "products.txt")) as file:
            for line in file.readlines():
                line = line.strip()
                loc, _, product = line.partition("/")
                self.products.setdefault(loc, dict())[product[:-1]] = line

        self.mainLayout = QVBoxLayout(self)
        self.bottomLayout = QHBoxLayout()

        self.model = QStandardItemModel()
        self.proxyModel = QSortFilterProxyModel()

        self.proxyModel.setSourceModel(self.model)
        self.proxyModel.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxyModel.setFilterKeyColumn(1)
        self.proxyModel.setSortCaseSensitivity(Qt.CaseInsensitive)

        self.infoBox          = QLabel()
        self.locationComboBox = QComboBox()
        self.mainView         = QTreeView()
        self.searchBar        = QLineEdit()
        self.selectButton     = QPushButton("Select")
        self.cancelButton     = QPushButton("Cancel")

        self.locationComboBox.currentTextChanged.connect(self.location_selected)
        self.selectButton.clicked.connect(self.select_pressed)
        self.cancelButton.clicked.connect(self.reject)
        self.searchBar.textChanged.connect(self.update_search)

        self.infoBox.setTextFormat(Qt.RichText)
        self.infoBox.setOpenExternalLinks(True)
        self.infoBox.setText("""
        <table>
            <tr>
                <td>MRMS Table</td>
                <td><a href="https://www.nssl.noaa.gov/projects/mrms/operational/tables.php">https://www.nssl.noaa.gov/projects/mrms/operational/tables.php</a></td>
            </tr>
        </table>
        """)

        self.mainView.setModel(self.proxyModel)
        self.mainView.setSortingEnabled(True)
        self.mainView.sortByColumn(0, Qt.AscendingOrder)

        self.mainLayout.addWidget(self.infoBox)
        self.mainLayout.addWidget(self.locationComboBox)
        self.mainLayout.addWidget(self.mainView)

        self.bottomLayout.addWidget(self.searchBar)
        self.bottomLayout.addWidget(self.selectButton)
        self.bottomLayout.addWidget(self.cancelButton)

        self.mainLayout.addLayout(self.bottomLayout)

        for loc in self.products.keys():
            self.locationComboBox.addItem(loc)
        self.locationComboBox.setCurrentText("CONUS")

        self.setMinimumWidth(600)
        self.setMinimumHeight(600)
        self.setSizeGripEnabled(True)

    def update_search(self, *args):
        self.proxyModel.setFilterWildcard(self.searchBar.text())

    def select_pressed(self, *args):
        indexes = self.mainView.selectedIndexes()
        if len(indexes) == 0:
            self.reject()
            return

        index = self.proxyModel.mapToSource(indexes[0])

        self.selectedProduct = self.model.item(index.row(), 1).text()
        self.accept()

    def location_selected(self, *args):
        self.model.clear()
        data = self.products.get(self.locationComboBox.currentText(), {})

        root = self.model.invisibleRootItem()

        for name, path in data.items():
            name = QStandardItem(name)
            path = QStandardItem(path)
            name.setEditable(False)
            path.setEditable(False)
            root.appendRow([name, path])

        self.model.setHorizontalHeaderLabels(["Product Name", "Product Path"])
        self.mainView.resizeColumnToContents(0)

class ProductsSelect(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        self.mainLayout = QHBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)

        self.display = QLineEdit()
        self.dialog  = ProductsDialog()
        self.dialogButton = QToolButton()

        self.dialogButton.setText("...")
        self.dialogButton.clicked.connect(self.run_dialog)

        self.mainLayout.addWidget(self.display)
        self.mainLayout.addWidget(self.dialogButton)

        self.set_product("")

    def set_product(self, text):
        self.dialog.selectedProduct = text
        self.display.setText(text)

    def get_product(self):
        return self.display.text()

    def run_dialog(self, *args):
        self.dialog.exec()
        self.set_product(self.dialog.selectedProduct)


class FileInput(QWidget):
    def __init__(self, *args, fileFilter, save, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        self.fileFilter = fileFilter
        self.save = save

        self.mainLayout = QHBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)

        self.lineEdit     = QLineEdit()
        self.dialogButton = QToolButton()

        self.dialogButton.setText("...")

        self.mainLayout.addWidget(self.lineEdit)
        self.mainLayout.addWidget(self.dialogButton)

        self.dialogButton.clicked.connect(self.file_dialog)

    def file_dialog(self):
        if self.save:
            fileName, fil = QFileDialog.getSaveFileName(self, "Select File",
                                                        self.lineEdit.text(),
                                                        self.fileFilter)
        else:
            fileName, fil = QFileDialog.getOpenFileName(self, "Select File",
                                                        self.lineEdit.text(),
                                                        self.fileFilter)
        if len(fil) == 0:
            return
        self.lineEdit.setText(fileName)

    def set_text(self, text):
        text = text.replace("{_internal}", location)
        text = os.path.normpath(text)

        self.lineEdit.setText(text)

class PlacefileEditor(QWidget):
    DEFAULTS = {
        "aws":                  True,
        "product":              "",
        "url":                  "",
        "imageFile":            "{_internal}/image.png",
        "placeFile":            "{_internal}/placefile.txt",
        "palette":              "{_internal}/palettes",
        "title":                "",
        "refresh":              15,
        "imageURL":             "",
        "imageWidth":           1920,
        "imageHeight":          1080,
        "verbose":              False,
        "timeout":              30,
        "regenerateTime":       60,
        "pullPeriod":           10,
    }

    def _make_enabled_callback(self, widget, enabler):
        def callback(*args, **kwargs):
            widget.setEnabled(enabler.isChecked())
        return callback

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        self.setMinimumWidth(600)

        self.mainLayout = QGridLayout(self)

        self.dataWidgets = {
            "aws":              QCheckBox(),
            "product":          ProductsSelect(),
            "url":              QLineEdit(),
            "imageFile":        FileInput(fileFilter = "PNG File (*.png)", save = True),
            "placeFile":        FileInput(fileFilter = "Placefile (*)", save = True),
            "palette":          FileInput(fileFilter = "Color Table (*)", save = False),
            "title":            QLineEdit(),
            "refresh":          QSpinBox(),
            "imageURL":         QLineEdit(),
            "imageWidth":       QSpinBox(),
            "imageHeight":      QSpinBox(),
            "verbose":          QCheckBox(),
            "timeout":          QSpinBox(),
            "regenerateTime":   QSpinBox(),
            "pullPeriod":       QSpinBox(),
        }

        self.dataWidgets["refresh"].setMinimum(15)
        self.dataWidgets["refresh"].setMaximum(3600 * 24 * 365)

        self.dataWidgets["regenerateTime"].setMinimum(15)
        self.dataWidgets["regenerateTime"].setMaximum(3600 * 24 * 365)

        self.dataWidgets["pullPeriod"].setMinimum(1)
        self.dataWidgets["pullPeriod"].setMaximum(3600 * 24 * 365)

        self.dataWidgets["imageWidth"].setMinimum(100)
        self.dataWidgets["imageWidth"].setMaximum(2048)

        self.dataWidgets["imageHeight"].setMinimum(100)
        self.dataWidgets["imageHeight"].setMaximum(2048)

        self.dataWidgets["timeout"].setMinimum(1)
        self.dataWidgets["timeout"].setMaximum(60)

        self.dataWidgets["aws"].stateChanged.connect(self.aws_check_callback)

        self.enableWidgets = {}

        view = [
            ("Title", "title", False, "The title to be used in Supercell-Wx for this Placefile"),
            ("AWS", "aws", False, "Pull from AWS instead of a URL. Recommended."),
            ("Product", "product", False, "The product to pull from AWS."),
            ("URL", "url", False, "The URL to pull the GRIB/MRMS data from."),
            ("Image File", "imageFile", False, "The path to where the image (png) should be generated"),
            ("Place File", "placeFile", False, "The path to where the placefile should be generated"),
            ("Refresh (s)", "refresh", False, "How often Supercell-Wx should refresh the placefile. Often is OK for local files."),
            ("Regeneration Period", "regenerateTime", False, "How often the placefile should be regenerated."),
            ("Pull Period", "pullPeriod", False, "How often AWS should be pulled for new data."),
            ("Palette", "palette", True, "The path to a color-table to be used for this product."),
            ("Image URL", "imageURL", True, "Generally unneeded. The URL to the image file. Useful for hosting on a server"),
            ("Image Width", "imageWidth", True, "The width of the image in pixels"),
            ("Image Height", "imageHeight", True, "The height of the image in pixels"),
            ("Verbose", "verbose", False, "If grib2pf should 'print' out information"),
            ("Timeout", "timeout", True, "The time grib2pf should wait for a response from the URL."),
        ]

        for i, (text, name, optional, tooltip) in enumerate(view):
            widget = self.dataWidgets[name]

            label = QLabel(text)
            font = label.font()
            font.setUnderline(True)
            label.setFont(font)
            label.setToolTip(tooltip)

            self.mainLayout.addWidget(label, i, 0)
            self.mainLayout.addWidget(widget, i, 1)

            if optional:
                enabler = QCheckBox()

                self.enableWidgets[name] = enabler
                self.mainLayout.addWidget(enabler, i, 2)
                widget.setEnabled(enabler.isChecked())
                enabler.stateChanged.connect(self._make_enabled_callback(widget, enabler))
                enabler.setToolTip(f"Enable {text}")

        self.mainLayout.setRowStretch(len(view), 1)
        self.aws_check_callback()

    AWS_ONLY = {"product", "pullPeriod"}
    NOT_AWS_ONLY = {"url", "regenerateTime"}
    def aws_check_callback(self, *args):
        state = self.dataWidgets["aws"].isChecked()

        for name in self.AWS_ONLY:
            self.dataWidgets[name].setEnabled(state)

        for name in self.NOT_AWS_ONLY:
            self.dataWidgets[name].setEnabled(not state)

    def set_settings(self, settings):
        for name, widget in self.dataWidgets.items():
            enabled = name in settings

            value = settings[name] if enabled else self.DEFAULTS[name]

            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QSpinBox):
                widget.setValue(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, FileInput):
                widget.set_text(value)
            elif isinstance(widget, ProductsSelect):
                widget.set_product(value)

            if name in self.enableWidgets:
                self.enableWidgets[name].setChecked(enabled)

    def get_settings(self):
        settings = {}
        awsState = self.dataWidgets["aws"].isChecked()
        for name, widget in self.dataWidgets.items():
            if name in self.enableWidgets and \
               not self.enableWidgets[name].isChecked():
                continue
            elif awsState and name in self.NOT_AWS_ONLY:
                continue
            elif not awsState and name in self.AWS_ONLY:
                continue
            if isinstance(widget, QLineEdit):
                settings[name] = widget.text()
            elif isinstance(widget, QSpinBox):
                settings[name] = widget.value()
            elif isinstance(widget, QCheckBox):
                settings[name] = widget.isChecked()
            elif isinstance(widget, FileInput):
                settings[name] = widget.lineEdit.text()
            elif isinstance(widget, ProductsSelect):
                settings[name] = widget.get_product()
        return settings

class FilePicker(QWidget):
    save_file_s = Signal(str, bool)
    open_file_s = Signal(str, bool)
    run_s       = Signal()

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        self.mainLayout = QHBoxLayout(self)

        self.fileName = os.path.join(location, "settings.jsonc")

        self.fileCheck    = QCheckBox()
        self.openButton   = QPushButton()
        self.saveButton   = QPushButton()
        self.saveAsButton = QPushButton()
        self.presetButton = QPushButton()
        self.runButton    = QPushButton()

        self.openButton.setText("Open File")
        self.saveButton.setText("Save File")
        self.saveAsButton.setText("Save File As")
        self.presetButton.setText("Load Preset")
        self.runButton.setText("Run")

        self.fileCheck.setToolTip("Enable editing non-default settings files. Not necessary for normal usage.")

        self.fileCheck.stateChanged.connect(self.file_check_pressed)
        self.openButton.clicked.connect(self.open_button_pressed)
        self.saveButton.clicked.connect(self.save_button_pressed)
        self.saveAsButton.clicked.connect(self.save_as_button_pressed)
        self.presetButton.clicked.connect(self.preset_button_pressed)
        self.runButton.clicked.connect(self.run_s.emit)

        self.mainLayout.addWidget(self.fileCheck)
        self.mainLayout.addWidget(self.openButton)
        self.mainLayout.addWidget(self.saveAsButton)
        self.mainLayout.addWidget(self.saveButton)
        self.mainLayout.addWidget(self.presetButton)
        self.mainLayout.addWidget(self.runButton)
        #self.mainLayout.addStretch(1)

        self.mainLayout.setStretch(0, 0)
        self.mainLayout.setStretch(1, 1)
        self.mainLayout.setStretch(2, 1)
        self.mainLayout.setStretch(3, 1)
        self.mainLayout.setStretch(4, 1)
        self.mainLayout.setStretch(5, 1)

        self.file_check_pressed()

    def file_check_pressed(self):
        state = self.fileCheck.isChecked()
        self.openButton.setEnabled(state)
        self.saveAsButton.setEnabled(state)

    def open_button_pressed(self):
        fileName, fil = QFileDialog.getOpenFileName(self, "Open File", \
                self.fileName, "Json File (*.json, *.jsonc)")
        if len(fil) > 0:
            self.fileName = fileName
            self.open_file_s.emit(self.fileName, True)

    def save_button_pressed(self):
        self.save_file_s.emit(self.fileName, True)

    def save_as_button_pressed(self):
        fileName, fil = QFileDialog.getSaveFileName(self, "Save File", \
                self.fileName, "Json File (*.json, *.jsonc)")

        if len(fil) > 0:
            self.fileName = fileName
            self.save_file_s.emit(self.fileName, False)

    def preset_button_pressed(self):
        base = os.path.join(location, "presets")
        files = {}
        for file in os.listdir(base):
            if not file.endswith(".jsonc"):
                continue
            files[file.rpartition(".")[0]] = os.path.join(base, file)
        name, ok = QInputDialog.getItem(self, "Select a Preset", "", files.keys())
        if ok and name in files:
            self.open_file_s.emit(files[name], False)

class PlacefileList(QAbstractTableModel):
    def __init__(self, *args, **kwargs):
        self.placeFiles = []
        QAbstractTableModel.__init__(self, *args, **kwargs)
        self.id_ = random.randrange(0, 1<<64)
        self.loaded = json.dumps(self.placeFiles)

    def update_placefile(self, index, new):
        self.placeFiles[index] = new

        i = self.createIndex(index, 0)
        self.dataChanged.emit(i, i)

    def add_placefile(self, placefile = {}):
        index = self.rowCount()
        begin = self.createIndex(-1, -1)
        self.beginInsertRows(begin, index, index)
        self.placeFiles.append(placefile)
        self.endInsertRows()

    def del_placefile(self, index):
        if index >= self.rowCount():
            return
        begin = self.createIndex(-1, -1)

        if self.currentRow == index:
            self.currentRow = -1
        elif self.currentRow > index:
            self.currentRow -= 1

        self.beginRemoveRows(begin, index, index)
        self.placeFiles.pop(index)
        self.endRemoveRows()

    def get_placefile(self, index):
        return self.placeFiles[index]

    def load_file(self, fileName, updateLoaded):
        self.beginResetModel()
        data = JsoncParser.parse_file(fileName)
        if isinstance(data, dict):
            self.placeFiles = [data]
        else:
            self.placeFiles = data
        self.endResetModel()

        if updateLoaded:
            self.loaded = json.dumps(self.placeFiles)

    def save_file(self, fileName):
        self.loaded = json.dumps(self.placeFiles)
        with open(fileName, "w") as file:
            file.write(json.dumps(self.placeFiles, indent = 4))

    def rowCount(self, parent = QModelIndex()):
        return len(self.placeFiles)

    def columnCount(self, parent = QModelIndex()):
        return 1

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        return "Placefiles"

    def data(self, index, role = Qt.DisplayRole):
        if index.row()    >= self.rowCount() or \
           index.column() >= self.columnCount() or \
           role != Qt.DisplayRole:
            return None

        return self.placeFiles[index.row()].get("title", "[untitled]")

    def flags(self, index):
        flags = super().flags(index)
        flags |= Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsDropEnabled
        return flags

    def canDropMimeData(self, data, action, row, column, parent):
        return True

    def dropMimeData(self, data, action, row, column, parent):
        if action != Qt.MoveAction:
            return False

        oldRow, inId, inData = json.loads(data.text())
        newRow = parent.row()

        begin = self.createIndex(-1, -1)

        if self.id_ == inId:
            if newRow == -1:
                newRow = self.rowCount() - 1
            if newRow == oldRow:
                return True

            if self.currentRow == oldRow:
                self.currentRow = newRow
            elif newRow < oldRow and newRow <= self.currentRow and oldRow > self.currentRow:
                self.currentRow += 1
            elif newRow > oldRow and newRow >= self.currentRow and oldRow < self.currentRow:
                self.currentRow -= 1

            self.placeFiles.pop(oldRow)
            self.placeFiles.insert(newRow, inData)
            return True
        else:
            if newRow == -1:
                newRow = self.rowCount()
            self.beginInsertRows(begin, newRow, newRow)
            self.placeFiles.insert(newRow, inData)
            self.endInsertRows()
            return True

        return False

    def supportedDragActions(self):
        return Qt.MoveAction

    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeData(self, indices):
        if len(indices) != 1:
            return None
        index = indices[0].row()
        if index >= self.rowCount():
            return None

        data = QMimeData()
        data.setText(json.dumps([index, self.id_, self.placeFiles[index]]))
        return data

    def get_modified(self):
        return self.loaded != json.dumps(self.placeFiles)

class PlacefileTable(QTableView):
    selection_changed_s = Signal(int)
    clipboard = QClipboard()

    def selectionChanged(self, selected, deselected):
        QTableView.selectionChanged(self, selected, deselected)

        index = selected.constFirst()
        if index is None:
            return
        index = index.top()
        if index < 0:
            return

        self.selection_changed_s.emit(index)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            index = self.selectedIndexes()[0].row()
            if index < 0:
                super().keyPressEvent(event)
                return
            data = self.model().get_placefile(index)
            data = json.dumps(data, indent = 4)
            mime = QMimeData()
            mime.setData(MIME_TYPE, data.encode("utf-8"))
            mime.setText(data)
            self.clipboard.setMimeData(mime)
        elif event.matches(QKeySequence.Cut):
            index = self.selectedIndexes()[0].row()
            if index < 0:
                super().keyPressEvent(event)
                return
            data = self.model().get_placefile(index)
            data = json.dumps(data, indent = 4)
            mime = QMimeData()
            mime.setData(MIME_TYPE, data.encode("utf-8"))
            mime.setText(data)
            self.clipboard.setMimeData(mime)
            self.model().del_placefile(index)
        elif event.matches(QKeySequence.Paste):
            mime = self.clipboard.mimeData()
            data = mime.data(MIME_TYPE)
            if len(data) == 0:
                super().keyPressEvent(event)
                return
            data = JsoncParser.parse_str(data.data().decode("utf-8"))
            self.model().add_placefile(data)
        else:
            super().keyPressEvent(event)

class MainWindow(QWidget):
    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        self.process = None

        self.setWindowTitle("grib2pf UI")
        self.setWindowIcon(QIcon(os.path.join(location, "icon", "icon32.ico")))

        self.mainLayout     = QVBoxLayout(self)
        self.workAreaLayout = QHBoxLayout()
        self.placefileManagerLayout = QVBoxLayout()
        self.placefileManagerButtons = QHBoxLayout()

        self.placefilesModel = PlacefileList()

        self.placefilesModel.currentRow = -1

        self.saveDialog = QMessageBox()
        self.delDialog  = QMessageBox()
        self.endDialog  = QMessageBox()

        self.saveDialog.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)
        self.delDialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        self.endDialog.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)

        self.saveDialog.setDefaultButton(QMessageBox.Save)
        self.delDialog.setDefaultButton(QMessageBox.Yes)
        self.endDialog.setDefaultButton(QMessageBox.Save)

        self.infoBox         = QLabel()
        self.filePicker      = FilePicker()
        self.placefiles      = PlacefileTable()
        self.placefileEditor = PlacefileEditor()
        self.addButton       = QPushButton()
        self.delButton       = QPushButton()

        self.infoBox.setTextFormat(Qt.RichText)
        self.infoBox.setOpenExternalLinks(True)
        self.infoBox.setText("""
        Read The README.md for more information.
        <table>
            <tr>
                <td>MRMS data</td>
                <td><a href="https://mrms.ncep.noaa.gov/data">https://mrms.ncep.noaa.gov/data</a></td>
            </tr>
            <tr>
                <td>MRMS Table</td>
                <td><a href="https://www.nssl.noaa.gov/projects/mrms/operational/tables.php">https://www.nssl.noaa.gov/projects/mrms/operational/tables.php</a></td>
            </tr>
        </table>
        """)

        self.addButton.setText("Add")
        self.delButton.setText("Remove")

        self.placefiles.setSelectionMode(QTableView.SingleSelection)
        self.placefiles.setModel(self.placefilesModel)
        self.placefiles.setMinimumWidth(300)
        self.placefiles.setMaximumWidth(500)
        self.placefiles.horizontalHeader().setStretchLastSection(True)
        self.placefiles.setDragEnabled(True)
        self.placefiles.setDragDropMode(QTableView.DragDrop)

        self.mainLayout.addWidget(self.infoBox)
        self.mainLayout.addWidget(self.filePicker)
        self.placefileManagerLayout.addWidget(self.placefiles)
        self.placefileManagerButtons.addWidget(self.addButton)
        self.placefileManagerButtons.addWidget(self.delButton)
        self.placefileManagerLayout.addLayout(self.placefileManagerButtons)
        self.workAreaLayout.addLayout(self.placefileManagerLayout)
        self.workAreaLayout.addWidget(self.placefileEditor)
        self.mainLayout.addLayout(self.workAreaLayout)

        self.filePicker.save_file_s.connect(self.save_file)
        self.filePicker.open_file_s.connect(self.load_file)
        self.filePicker.run_s.connect(self.run_grib2pf)
        self.placefiles.selection_changed_s.connect(self.row_selected)
        self.addButton.clicked.connect(self.add_placefile)
        self.delButton.clicked.connect(self.del_placefile)

        if os.path.exists(self.filePicker.fileName):
            self.load_file(self.filePicker.fileName)
        else:
            self.load_file(os.path.join(location, "presets", "default.jsonc"))

    def row_selected(self, row):
        if self.placefilesModel.currentRow >= 0:
            self.placefilesModel.update_placefile(self.placefilesModel.currentRow, self.placefileEditor.get_settings())

        self.placefileEditor.set_settings(self.placefilesModel.get_placefile(row))
        self.placefilesModel.currentRow = row

    def save_file(self, fileName, conf):
        if conf:
            self.saveDialog.setText(f"Save To {fileName}")
            if self.saveDialog.exec() != QMessageBox.Save:
                return False

        if self.placefilesModel.currentRow >= 0:
            self.placefilesModel.update_placefile(self.placefilesModel.currentRow, self.placefileEditor.get_settings())
        self.placefilesModel.save_file(fileName)
        return True

    def load_file(self, fileName, updateLoaded = True):
        self.placefilesModel.currentRow = -1
        self.placefilesModel.load_file(fileName, updateLoaded)
        if self.placefilesModel.rowCount() > 0:
            self.placefileEditor.set_settings(self.placefilesModel.get_placefile(0))
            self.placefilesModel.currentRow = 0

    def run_grib2pf(self):
        if self.process is not None:
            self.process.kill()
            self.process.wait()
        if not self.save_file(self.filePicker.fileName, True):
            return

        path = location
        parts = os.path.split(path)
        if parts[1] == "_internal":
            path = os.path.join(parts[0], "grib2pf.exe")
        else:
            path = os.path.join(path, "grib2pf.py")

        self.process = subprocess.Popen([path, "--json", self.placefilesModel.loaded])

    def add_placefile(self):
        self.placefilesModel.add_placefile()

    def del_placefile(self):
        if self.placefilesModel.currentRow < 0:
            return

        self.delDialog.setText("Do you want to delete this placefile from the setting file?")
        if self.delDialog.exec() != QMessageBox.Yes:
            return

        self.placefilesModel.del_placefile(self.placefilesModel.currentRow)

    def closeEvent(self, event):
        if self.process is not None:
            self.process.kill()

        if self.placefilesModel.currentRow >= 0:
            self.placefilesModel.update_placefile(self.placefilesModel.currentRow, self.placefileEditor.get_settings())

        if not self.placefilesModel.get_modified():
            event.accept()
            return
        self.endDialog.setText(f"Settings have been modified. Save it?")
        ret = self.endDialog.exec()
        if ret == QMessageBox.Cancel:
            event.ignore()
            return
        elif ret == QMessageBox.Save:
            self.save_file(self.filePicker.fileName, False)

        event.accept()

def run():
    app = QApplication(sys.argv)
    app.setStyle("fusion")
    main = MainWindow()
    main.show()
    app.exec()

if __name__ == "__main__":
    run()
