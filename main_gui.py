import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, 
                             QSplitter, QTreeView, QLabel, QHeaderView, QPushButton, 
                             QFileDialog, QComboBox, QListWidget, QListWidgetItem,
                             QProgressBar, QMessageBox, QMenu, QTreeWidgetItemIterator)
from PyQt6.QtGui import QColor, QBrush, QFileSystemModel, QAction, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QDir

from core.parser_factory import parser_factory
from core.symbol_node import SymbolNode
from utils.logger import logger

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Code-Context-Bridge v2.2 (Copy & Search Added)")
        self.resize(1300, 850)
        
        self.current_symbol_root = None
        self.project_root_path = ""
        
        self.init_ui()
        self.setup_shortcuts()
        logger.info("GUI Started.")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 1. Top Bar ---
        top_bar = QHBoxLayout()
        
        self.btn_open = QPushButton("📂 Open Project")
        self.btn_open.setFixedWidth(120)
        self.btn_open.clicked.connect(self.open_directory_dialog)
        
        self.path_label = QLabel(" Target: (None)")
        self.path_label.setStyleSheet("color: #555; font-weight: bold; margin-right: 10px;")
        
        self.search_scope_combo = QComboBox()
        self.search_scope_combo.addItems(["Current File", "Entire Project"])
        self.search_scope_combo.setFixedWidth(110)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search symbols... (Press Enter for Global Search)")
        self.search_input.returnPressed.connect(self.on_search_enter_pressed)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        
        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.path_label)
        top_bar.addStretch()
        top_bar.addWidget(self.search_scope_combo)
        top_bar.addWidget(self.search_input, 2)
        
        main_layout.addLayout(top_bar)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # --- 2. Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: File Explorer
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(QDir.rootPath())
        self.file_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs | QDir.Filter.Files)

        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        cwd = os.getcwd()
        self.file_tree.setRootIndex(self.file_model.index(cwd))
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setColumnHidden(1, True)
        self.file_tree.setColumnHidden(2, True)
        self.file_tree.setColumnHidden(3, True)
        self.file_tree.clicked.connect(lambda idx: self.on_file_clicked(idx))
        
        splitter.addWidget(self.file_tree)

        # Right: Widget Container
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1) Symbol Tree
        self.symbol_tree = QTreeWidget()
        self.symbol_tree.setHeaderLabels(["Symbol Signature", "Kind", "Line"])
        self.symbol_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.symbol_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.symbol_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        # [NEW] Context Menu 설정
        self.symbol_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.symbol_tree.customContextMenuRequested.connect(self.open_context_menu)
        
        # 2) Global Search Results List
        self.global_result_list = QListWidget()
        self.global_result_list.setVisible(False)
        self.global_result_list.itemClicked.connect(self.on_global_result_clicked)
        
        right_layout.addWidget(self.symbol_tree)
        right_layout.addWidget(self.global_result_list)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 950])
        
        main_layout.addWidget(splitter)

    def setup_shortcuts(self):
        """[NEW] Ctrl+C 단축키 설정"""
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.symbol_tree)
        self.copy_shortcut.activated.connect(self.copy_selected_item_name)

    def open_context_menu(self, position):
        """[NEW] 우클릭 메뉴 구현"""
        item = self.symbol_tree.itemAt(position)
        if not item:
            return

        menu = QMenu()
        
        # 메뉴 액션 생성
        action_copy_name = QAction("📋 Copy Name Only", self)
        action_copy_sig = QAction("📑 Copy Full Signature", self)
        action_search = QAction("🔍 Send to Search Bar", self)
        
        menu.addAction(action_copy_name)
        menu.addAction(action_copy_sig)
        menu.addSeparator()
        menu.addAction(action_search)

        # 액션 연결
        action_copy_name.triggered.connect(lambda: self.copy_to_clipboard(item, 'name'))
        action_copy_sig.triggered.connect(lambda: self.copy_to_clipboard(item, 'signature'))
        action_search.triggered.connect(lambda: self.send_to_search(item))
        
        menu.exec(self.symbol_tree.viewport().mapToGlobal(position))

    def copy_to_clipboard(self, item, mode):
        """클립보드 복사 로직"""
        if mode == 'name':
            # UserRole에 저장된 순수 이름 가져오기
            text = item.data(0, Qt.ItemDataRole.UserRole)
        else:
            # 트리에 표시된 전체 텍스트 (시그니처 포함)
            # 아이콘 제거를 위해 2번째 글자부터 가져오거나, 툴팁을 활용
            text = item.toolTip(0) # 툴팁에 전체 시그니처가 저장되어 있음
            if not text:
                text = item.text(0)[2:] # 아이콘 제거 (간이 방식)

        if text:
            QApplication.clipboard().setText(text)
            logger.info(f"Copied to clipboard: {text}")

    def copy_selected_item_name(self):
        """Ctrl+C 눌렀을 때 실행"""
        item = self.symbol_tree.currentItem()
        if item:
            self.copy_to_clipboard(item, 'name')

    def send_to_search(self, item):
        """선택한 심볼 이름을 검색창으로 보내고 즉시 검색"""
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if name:
            self.search_input.setText(name)
            self.search_input.setFocus()
            # Current File 모드라면 자동 필터링됨 (textChanged 연결됨)
            # Entire Project 모드라면 엔터를 눌러줘야 하므로 알림만 줌 (혹은 자동 실행 가능)

    # --- 기존 로직 유지 ---

    def open_directory_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Project Root Folder")
        if folder:
            self.project_root_path = folder
            logger.info(f"Project root changed to: {folder}")
            self.path_label.setText(f" Target: {os.path.basename(folder)}")
            root_index = self.file_model.index(folder)
            self.file_tree.setRootIndex(root_index)

    def on_file_clicked(self, index, target_line=None):
        self.global_result_list.setVisible(False)
        self.symbol_tree.setVisible(True)
        
        file_path = self.file_model.filePath(index)
        if os.path.isdir(file_path):
            return

        logger.info(f"File selected: {file_path}")
        if self.search_scope_combo.currentIndex() == 0:
            self.search_input.clear()
        
        parser = parser_factory.get_parser(file_path)
        if not parser:
            self.symbol_tree.clear()
            self.symbol_tree.addTopLevelItem(QTreeWidgetItem(["No parser for this file type", "", ""]))
            return

        try:
            root_node = parser.parse(file_path)
            if root_node:
                self.current_symbol_root = root_node
                self.render_tree(root_node)
                if target_line:
                    self.highlight_node_by_line(target_line)
            else:
                self.symbol_tree.clear()
                self.symbol_tree.addTopLevelItem(QTreeWidgetItem(["Parsing failed or empty", "", ""]))
        except Exception as e:
            logger.error(f"Error parsing file: {e}")

    def render_tree(self, root_node: SymbolNode):
        self.symbol_tree.clear()
        
        def add_items(node: SymbolNode, parent_item):
            display_text = node.signature if node.signature else node.name
            
            kind_icon = "📄 " if node.kind == 'file' else ("📦 " if node.kind == 'class' else ("ƒ " if 'function' in node.kind or 'method' in node.kind else "🔹 "))
            
            if node.kind == 'file':
                full_display = f"{kind_icon} {node.name}"
            else:
                full_display = f"{kind_icon} {display_text}"
            
            item = QTreeWidgetItem(parent_item)
            item.setText(0, full_display)
            item.setText(1, node.kind)
            item.setText(2, str(node.start_line))
            
            # 검색 및 복사용 데이터 저장
            item.setData(0, Qt.ItemDataRole.UserRole, node.name)
            item.setData(2, Qt.ItemDataRole.UserRole, node.start_line)
            
            if node.signature:
                item.setToolTip(0, node.signature)

            for child in node.children:
                add_items(child, item)
            return item

        root_item = add_items(root_node, self.symbol_tree)
        root_item.setExpanded(True)

    def highlight_node_by_line(self, target_line):
        iterator = QTreeWidgetItemIterator(self.symbol_tree)
        best_item = None
        min_dist = 999999
        
        while iterator.value():
            item = iterator.value()
            line_data = item.data(2, Qt.ItemDataRole.UserRole)
            if line_data is not None:
                line = int(line_data)
                if line == target_line:
                    best_item = item
                    break
                if 0 < target_line - line < min_dist:
                    min_dist = target_line - line
                    best_item = item
            iterator += 1
            
        if best_item:
            self.symbol_tree.scrollToItem(best_item)
            self.symbol_tree.setCurrentItem(best_item)
            parent = best_item.parent()
            while parent:
                parent.setExpanded(True)
                parent = parent.parent()
            
            best_item.setBackground(0, QBrush(QColor(255, 242, 204)))
            best_item.setForeground(0, QBrush(Qt.GlobalColor.black))

    def on_search_text_changed(self, text):
        if self.search_scope_combo.currentIndex() == 0:
            self.symbol_tree.setVisible(True)
            self.global_result_list.setVisible(False)
            self.filter_tree_recursive(text)

    def on_search_enter_pressed(self):
        query = self.search_input.text().strip()
        if not query:
            return

        mode = self.search_scope_combo.currentIndex()
        if mode == 0:
            self.filter_tree_recursive(query)
        else:
            self.perform_global_search(query)

    def filter_tree_recursive(self, query):
        if not self.symbol_tree.topLevelItemCount():
            return
        root_item = self.symbol_tree.topLevelItem(0)
        
        if not query:
            self.reset_visuals(root_item)
            return

        self._apply_filter(root_item, query.lower())

    def _apply_filter(self, item: QTreeWidgetItem, query: str) -> bool:
        name_data = item.data(0, Qt.ItemDataRole.UserRole)
        name = str(name_data) if name_data else ""
        
        is_match = query in name.lower()
        child_match = False
        
        for i in range(item.childCount()):
            if self._apply_filter(item.child(i), query):
                child_match = True
        
        should_show = is_match or child_match
        item.setHidden(not should_show)
        
        if should_show:
            item.setExpanded(True)
            if is_match:
                item.setBackground(0, QBrush(QColor(255, 242, 204)))
            else:
                item.setBackground(0, QBrush(Qt.GlobalColor.transparent))
        else:
            item.setExpanded(False)
        return should_show

    def reset_visuals(self, item: QTreeWidgetItem):
        item.setHidden(False)
        item.setBackground(0, QBrush(Qt.GlobalColor.transparent))
        item.setExpanded(item.parent() is None)
        for i in range(item.childCount()):
            self.reset_visuals(item.child(i))

    def perform_global_search(self, query):
        if not self.project_root_path:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return

        self.symbol_tree.setVisible(False)
        self.global_result_list.setVisible(True)
        self.global_result_list.clear()
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        QApplication.processEvents()

        logger.info(f"Starting global search for: {query}")
        
        results = []
        for root, dirs, files in os.walk(self.project_root_path):
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.vs', 'Library', 'Temp'}]
            
            for file in files:
                full_path = os.path.join(root, file)
                parser = parser_factory.get_parser(full_path)
                if parser:
                    try:
                        node = parser.parse(full_path)
                        if node:
                            matches = self._search_node_recursive(node, query)
                            results.extend(matches)
                    except:
                        pass
                QApplication.processEvents()

        self.progress_bar.setVisible(False)
        
        if not results:
            self.global_result_list.addItem("No results found.")
            return

        self.global_result_list.addItem(f"Found {len(results)} matches for '{query}':")
        for res in results:
            item_text = f"[{res['kind']}] {res['name']} \n   📍 {res['path']} (Line {res['line']})"
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.ItemDataRole.UserRole, res['path'])
            list_item.setData(Qt.ItemDataRole.UserRole + 1, res['line'])
            self.global_result_list.addItem(list_item)

    def _search_node_recursive(self, node: SymbolNode, query: str):
        matches = []
        if query.lower() in node.name.lower():
            if node.kind != 'file':
                matches.append({
                    'name': node.name,
                    'kind': node.kind,
                    'path': node.path,
                    'line': node.start_line
                })
        
        for child in node.children:
            matches.extend(self._search_node_recursive(child, query))
        return matches

    def on_global_result_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        line = item.data(Qt.ItemDataRole.UserRole + 1)
        
        if not path: return

        idx = self.file_model.index(path)
        if idx.isValid():
            self.file_tree.setCurrentIndex(idx)
            self.file_tree.scrollTo(idx)
            self.on_file_clicked(idx, target_line=line)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = app.font()
    font.setPointSize(10)
    font.setFamily("Segoe UI")
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())