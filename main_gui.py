import sys
import os
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, 
                             QSplitter, QTreeView, QLabel, QHeaderView, QPushButton, 
                             QFileDialog, QComboBox, QListWidget, QListWidgetItem,
                             QProgressBar, QMessageBox, QMenu, QTreeWidgetItemIterator,
                             QGroupBox, QProgressDialog)
from PyQt6.QtGui import QColor, QBrush, QFileSystemModel, QAction, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QDir, QThread, pyqtSignal

from core.parser_factory import parser_factory
from core.symbol_node import SymbolNode
from core.call_graph import call_graph
from utils.logger import logger

# --- Indexing Worker (Call Graph Build) ---
class IndexingWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, root_path):
        super().__init__()
        self.root_path = root_path
        self._is_cancelled = False

    def cancel(self):
        """인덱싱 취소 요청"""
        self._is_cancelled = True

    def run(self):
        # Call Graph 구축 (시간이 좀 걸릴 수 있음)
        try:
            call_graph.build_graph(self.root_path, self.report_progress, self.check_cancelled)
            if self._is_cancelled:
                self.cancelled.emit()
            else:
                self.finished.emit()
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            self.finished.emit()

    def check_cancelled(self):
        """취소 여부 확인"""
        return self._is_cancelled

    def report_progress(self, current, total, filename):
        if not self._is_cancelled:
            self.progress.emit(current, total, filename)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Code-Context-Bridge v4.1 (Call Graph with Snippets)")
        self.resize(1500, 950)
        
        self.current_symbol_root = None
        self.project_root_path = ""
        self.indexer = None
        
        self.init_ui()
        self.setup_shortcuts()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Top Bar ---
        top_bar = QHBoxLayout()
        self.btn_open = QPushButton("📂 Open Project")
        self.btn_open.setFixedWidth(120)
        self.btn_open.clicked.connect(self.open_directory_dialog)
        
        self.path_label = QLabel(" Target: (None)")
        self.path_label.setStyleSheet("font-weight: bold; margin-right: 10px;")
        
        self.search_scope_combo = QComboBox()
        self.search_scope_combo.addItems(["Current File", "Entire Project"])
        self.search_scope_combo.setFixedWidth(110)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search symbols...")
        self.search_input.returnPressed.connect(self.on_search_enter_pressed)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        
        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.path_label)
        top_bar.addStretch()
        top_bar.addWidget(self.search_scope_combo)
        top_bar.addWidget(self.search_input, 2)
        main_layout.addLayout(top_bar)
        
        # --- Splitter ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Files
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(QDir.rootPath())
        self.file_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs | QDir.Filter.Files)

        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        self.file_tree.setRootIndex(self.file_model.index(os.getcwd()))
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setColumnHidden(1, True)
        self.file_tree.setColumnHidden(2, True)
        self.file_tree.setColumnHidden(3, True)
        self.file_tree.clicked.connect(lambda idx: self.on_file_clicked(idx))
        main_splitter.addWidget(self.file_tree)

        # Right: Symbols + Call Graph
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Right Top: Symbol Tree
        self.right_top_widget = QWidget()
        rt_layout = QVBoxLayout(self.right_top_widget)
        rt_layout.setContentsMargins(0, 0, 0, 0)
        
        self.symbol_tree = QTreeWidget()
        self.symbol_tree.setHeaderLabels(["Symbol / Signature", "Kind", "Line"])
        self.symbol_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) 
        self.symbol_tree.header().resizeSection(0, 500)
        
        self.symbol_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.symbol_tree.customContextMenuRequested.connect(self.open_context_menu)
        self.symbol_tree.itemClicked.connect(self.on_symbol_clicked) # Graph update
        
        self.global_result_list = QListWidget()
        self.global_result_list.setVisible(False)
        self.global_result_list.itemClicked.connect(self.on_global_result_clicked)
        
        rt_layout.addWidget(self.symbol_tree)
        rt_layout.addWidget(self.global_result_list)
        right_splitter.addWidget(self.right_top_widget)
        
        # Right Bottom: Call Graph (Incoming | Outgoing)
        graph_widget = QWidget()
        graph_layout = QHBoxLayout(graph_widget)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        
        self.graph_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Incoming (Callers) - Tree Widget
        self.grp_incoming = QGroupBox("Incoming References (Who calls me?)")
        vbox_in = QVBoxLayout(self.grp_incoming)
        self.tree_incoming = QTreeWidget()
        self.tree_incoming.setHeaderHidden(True)
        self.tree_incoming.itemClicked.connect(self.on_ref_item_clicked)
        vbox_in.addWidget(self.tree_incoming)
        
        # Outgoing (Callees) - Tree Widget
        self.grp_outgoing = QGroupBox("Outgoing References (Who I call?)")
        vbox_out = QVBoxLayout(self.grp_outgoing)
        self.tree_outgoing = QTreeWidget()
        self.tree_outgoing.setHeaderHidden(True)
        self.tree_outgoing.itemClicked.connect(self.on_outgoing_item_clicked)
        vbox_out.addWidget(self.tree_outgoing)
        
        self.graph_splitter.addWidget(self.grp_incoming)
        self.graph_splitter.addWidget(self.grp_outgoing)
        self.graph_splitter.setSizes([500, 500])
        
        graph_layout.addWidget(self.graph_splitter)
        right_splitter.addWidget(graph_widget)
        
        right_splitter.setSizes([600, 300]) # 2:1 ratio
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([300, 1200])
        main_layout.addWidget(main_splitter)

    # --- Indexing & Project Opening ---
    def open_directory_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Project Root Folder")
        if folder:
            self.project_root_path = folder
            self.path_label.setText(f" Target: {os.path.basename(folder)}")
            self.file_tree.setRootIndex(self.file_model.index(folder))
            self.start_indexing()

    def start_indexing(self):
        self.pd = QProgressDialog("Indexing Project Call Graph...", "Cancel", 0, 100, self)
        self.pd.setWindowModality(Qt.WindowModality.WindowModal)
        self.pd.canceled.connect(self.cancel_indexing)
        self.pd.show()
        
        # 인덱싱 중 Call Graph 기능 비활성화
        self.set_call_graph_enabled(False)
        
        self.indexer = IndexingWorker(self.project_root_path)
        self.indexer.progress.connect(self.update_indexing_progress)
        self.indexer.finished.connect(self.indexing_finished)
        self.indexer.cancelled.connect(self.indexing_cancelled)
        self.indexer.start()

    def cancel_indexing(self):
        """인덱싱 취소 처리"""
        if self.indexer:
            self.indexer.cancel()
            logger.info("Indexing cancelled by user.")

    def update_indexing_progress(self, current, total, filename):
        self.pd.setMaximum(total)
        self.pd.setValue(current)
        self.pd.setLabelText(f"Indexing: {os.path.basename(filename)}")

    def indexing_finished(self):
        self.pd.cancel()
        # 인덱싱 완료 후 Call Graph 기능 활성화
        self.set_call_graph_enabled(True)
        logger.info("Call Graph Indexing Completed.")

    def indexing_cancelled(self):
        """인덱싱 취소 완료 처리"""
        self.pd.cancel()
        self.set_call_graph_enabled(True)
        logger.info("Call Graph Indexing Cancelled.")

    def set_call_graph_enabled(self, enabled: bool):
        """Call Graph 관련 UI 활성화/비활성화"""
        self.symbol_tree.setEnabled(enabled)
        self.tree_incoming.setEnabled(enabled)
        self.tree_outgoing.setEnabled(enabled)
        if not enabled:
            self.tree_incoming.clear()
            self.tree_outgoing.clear()
            self.grp_incoming.setTitle("Incoming References (Indexing...)")
            self.grp_outgoing.setTitle("Outgoing References (Indexing...)")
        else:
            # 인덱싱 완료 시 제목을 기본 형식으로 복원
            self.grp_incoming.setTitle("Incoming References (Who calls me?)")
            self.grp_outgoing.setTitle("Outgoing References (Who I call?)")

    # --- Symbol Click & Call Graph Rendering ---
    def on_symbol_clicked(self, item, column):
        symbol_name = item.data(0, Qt.ItemDataRole.UserRole)
        # 현재 열려있는 파일 경로
        current_file_idx = self.file_tree.currentIndex()
        current_file_path = self.file_model.filePath(current_file_idx)
        
        if not symbol_name: return
        
        # 파일 경로 유효성 검사
        if not current_file_path or not os.path.exists(current_file_path):
            # 파일이 선택되지 않았거나 존재하지 않는 경우
            self.tree_incoming.clear()
            self.tree_outgoing.clear()
            self.grp_incoming.setTitle(f"Incoming References to '{symbol_name}'")
            self.grp_outgoing.setTitle(f"Outgoing Calls inside '{symbol_name}'")
            return
        
        # 1. Incoming Calls (Caller) - Tree Structure
        self.tree_incoming.clear()
        self._build_incoming_tree(symbol_name, None, set())
        
        # 2. Outgoing Calls (Callee) - Tree Structure
        self.tree_outgoing.clear()
        self._build_outgoing_tree(current_file_path, symbol_name, None, set())
        
        self.grp_incoming.setTitle(f"Incoming References to '{symbol_name}'")
        self.grp_outgoing.setTitle(f"Outgoing Calls inside '{symbol_name}'")
    
    def _build_incoming_tree(self, target_func, parent_item, visited, depth=0, max_depth=10):
        """재귀적으로 Incoming 호출 체인을 트리로 구성"""
        if depth > max_depth:
            return
        
        callers = call_graph.get_incoming(target_func)
        
        if not callers:
            if parent_item is None:
                root = QTreeWidgetItem(self.tree_incoming)
                root.setText(0, "(No incoming calls detected)")
            return
        
        for c in callers:
            rel_path = os.path.relpath(c['path'], self.project_root_path) if self.project_root_path else c['path']
            caller_name = c['caller']
            
            # 순환 참조 방지: 이미 방문한 함수는 건너뛰기
            caller_path_key = f"{c['path']}:{caller_name}"
            if caller_path_key in visited:
                continue
            visited.add(caller_path_key)
            
            # 트리 아이템 생성
            if parent_item is None:
                item = QTreeWidgetItem(self.tree_incoming)
            else:
                item = QTreeWidgetItem(parent_item)
            
            # 표시 텍스트: 함수명, 호출 위치, 파일 경로
            file_name = os.path.basename(c['path'])
            txt = f"{caller_name}  [Line {c['line']}]  📄 {file_name}"
            item.setText(0, txt)
            item.setToolTip(0, f"File: {rel_path}\nFull Path: {c['path']}\nCaller: {caller_name}\nLine: {c['line']}\nSnippet: {c['snippet']}")
            
            # 클릭 시 이동할 정보 저장
            item.setData(0, Qt.ItemDataRole.UserRole, c['path'])
            item.setData(0, Qt.ItemDataRole.UserRole + 1, c['line'])
            item.setData(0, Qt.ItemDataRole.UserRole + 2, caller_name)
            
            # 재귀적으로 상위 호출자 탐색 (순환 참조 방지)
            if caller_name != target_func:
                self._build_incoming_tree(caller_name, item, visited.copy(), depth + 1, max_depth)
        
        # 루트 아이템이면 확장
        if parent_item is None and self.tree_incoming.topLevelItemCount() > 0:
            for i in range(self.tree_incoming.topLevelItemCount()):
                self.tree_incoming.topLevelItem(i).setExpanded(True)
    
    def _build_outgoing_tree(self, file_path, caller_func, parent_item, visited, depth=0, max_depth=10):
        """재귀적으로 Outgoing 호출 체인을 트리로 구성"""
        if depth > max_depth:
            return
        
        callees = call_graph.get_outgoing(file_path, caller_func)
        
        if not callees:
            if parent_item is None:
                root = QTreeWidgetItem(self.tree_outgoing)
                root.setText(0, "(No outgoing calls detected)")
            return
        
        for call_info in callees:
            target = call_info['called']
            
            # 순환 참조 방지
            callee_key = f"{file_path}:{caller_func}:{target}"
            if callee_key in visited:
                continue
            visited.add(callee_key)
            
            # 트리 아이템 생성
            if parent_item is None:
                item = QTreeWidgetItem(self.tree_outgoing)
            else:
                item = QTreeWidgetItem(parent_item)
            
            # 정의 파일 경로 찾기
            defs = call_graph.definitions.get(target, [])
            target_path = None
            if defs:
                target_path = defs[0]
            
            # 외부 라이브러리 함수 판단 (snippet에 모듈 접두사가 있는 경우)
            snippet = call_info.get('snippet', '')
            is_external = False
            if snippet and '.' in snippet:
                # snippet에서 함수 호출 부분 추출 (예: "F.silu(x1)" -> "F.silu")
                # 함수 호출 패턴 찾기 (예: F.silu, torch.nn.functional.silu)
                match = re.search(r'([a-zA-Z_][a-zA-Z0-9_.]*)\s*\(', snippet)
                if match:
                    full_call = match.group(1)
                    # 모듈 접두사가 있고, 정의를 찾을 수 없는 경우 외부 라이브러리로 판단
                    if '.' in full_call and not (target_path and os.path.exists(target_path)):
                        is_external = True
            
            # 표시 텍스트: 함수명, 호출 위치, 정의 파일 경로
            if target_path and os.path.exists(target_path):
                rel_def_path = os.path.relpath(target_path, self.project_root_path) if self.project_root_path else target_path
                file_name = os.path.basename(target_path)
                txt = f"{target}  [Line {call_info['line']}]  📄 {file_name}"
                item.setToolTip(0, f"Callee: {target}\nDefined in: {rel_def_path}\nFull Path: {target_path}\nCalled at Line: {call_info['line']}\nSnippet: {call_info['snippet']}")
            elif is_external:
                txt = f"{target}  [Line {call_info['line']}]  📦 (External library)"
                item.setToolTip(0, f"Callee: {target}\nLine: {call_info['line']}\nSnippet: {call_info['snippet']}\n📦 External library function (not in project)")
            else:
                txt = f"{target}  [Line {call_info['line']}]  ⚠ (Definition not found)"
                item.setToolTip(0, f"Callee: {target}\nLine: {call_info['line']}\nSnippet: {call_info['snippet']}\n⚠ Definition file not found")
            
            item.setText(0, txt)
            
            # 클릭 시 이동할 정보 저장
            item.setData(0, Qt.ItemDataRole.UserRole, target)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, call_info['line'])
            
            # 재귀적으로 하위 호출 탐색
            if target_path and target != caller_func:  # 무한 루프 방지
                self._build_outgoing_tree(target_path, target, item, visited.copy(), depth + 1, max_depth)
        
        # 루트 아이템이면 확장
        if parent_item is None and self.tree_outgoing.topLevelItemCount() > 0:
            for i in range(self.tree_outgoing.topLevelItemCount()):
                self.tree_outgoing.topLevelItem(i).setExpanded(True)

    # --- Navigation ---
    def on_ref_item_clicked(self, item, column):
        # Incoming 아이템 클릭
        path = item.data(0, Qt.ItemDataRole.UserRole)
        line = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if path and os.path.exists(path):
            idx = self.file_model.index(path)
            self.file_tree.setCurrentIndex(idx)
            self.file_tree.scrollTo(idx)
            self.on_file_clicked(idx, target_line=line)

    def on_outgoing_item_clicked(self, item, column):
        # Outgoing 아이템 클릭 (정의로 이동)
        callee_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not callee_name: return
        
        defs = call_graph.definitions.get(callee_name, [])
        if defs:
            target_path = defs[0]
            if os.path.exists(target_path):
                idx = self.file_model.index(target_path)
                self.file_tree.setCurrentIndex(idx)
                self.file_tree.scrollTo(idx)
                self.on_file_clicked(idx, highlight_symbol=callee_name)
        else:
            QMessageBox.information(self, "Info", f"Definition for '{callee_name}' not found.")

    # --- Basic File & Search Logic ---
    def setup_shortcuts(self):
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.symbol_tree)
        self.copy_shortcut.activated.connect(self.copy_selected_item_name)

    def open_context_menu(self, position):
        item = self.symbol_tree.itemAt(position)
        if not item: return
        menu = QMenu()
        menu.addAction("📋 Copy Name Only", lambda: self.copy_to_clipboard(item, 'name'))
        menu.addAction("📑 Copy Full Signature", lambda: self.copy_to_clipboard(item, 'signature'))
        menu.addSeparator()
        menu.addAction("🔍 Send to Search Bar", lambda: self.send_to_search(item))
        menu.exec(self.symbol_tree.viewport().mapToGlobal(position))

    def copy_to_clipboard(self, item, mode):
        text = item.data(0, Qt.ItemDataRole.UserRole) if mode == 'name' else (item.toolTip(0) or item.text(0))
        if text: QApplication.clipboard().setText(text)

    def copy_selected_item_name(self):
        item = self.symbol_tree.currentItem()
        if item: self.copy_to_clipboard(item, 'name')

    def send_to_search(self, item):
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if name:
            self.search_input.setText(name)
            self.search_input.setFocus()

    def on_file_clicked(self, index, target_line=None, highlight_symbol=None):
        self.global_result_list.setVisible(False)
        self.symbol_tree.setVisible(True)
        file_path = self.file_model.filePath(index)
        if os.path.isdir(file_path): return

        if self.search_scope_combo.currentIndex() == 0:
            self.search_input.clear()
        
        parser = parser_factory.get_parser(file_path)
        if not parser:
            self.symbol_tree.clear()
            return

        try:
            root_node = parser.parse(file_path)
            if root_node:
                self.render_tree(root_node)
                if target_line:
                    self.highlight_node_by_line(target_line)
                elif highlight_symbol:
                    self.highlight_node_by_name(highlight_symbol)
        except Exception as e:
            logger.error(f"Error: {e}")

    def render_tree(self, root_node: SymbolNode):
        self.symbol_tree.clear()
        def add_items(node: SymbolNode, parent_item):
            display_text = node.signature if node.signature else node.name
            kind_icon = "📄 " if node.kind == 'file' else ("📦 " if node.kind == 'class' else ("ƒ " if 'function' in node.kind else "🔹 "))
            
            item = QTreeWidgetItem(parent_item)
            item.setText(0, f"{kind_icon} {display_text}")
            item.setText(1, node.kind)
            item.setText(2, str(node.start_line))
            
            item.setData(0, Qt.ItemDataRole.UserRole, node.name)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, node.signature)
            item.setData(2, Qt.ItemDataRole.UserRole, node.start_line)
            if node.signature: item.setToolTip(0, node.signature)

            for child in node.children: add_items(child, item)
            return item

        root_item = add_items(root_node, self.symbol_tree)
        root_item.setExpanded(True)
        # 컬럼 자동 조절
        self.symbol_tree.resizeColumnToContents(0)
        if self.symbol_tree.columnWidth(0) > 600:
            self.symbol_tree.header().resizeSection(0, 600)

    def highlight_node_by_line(self, target_line):
        iterator = QTreeWidgetItemIterator(self.symbol_tree)
        best_item = None
        min_dist = 999999
        while iterator.value():
            item = iterator.value()
            line = int(item.data(2, Qt.ItemDataRole.UserRole) or 0)
            if line == target_line: best_item = item; break
            if 0 < target_line - line < min_dist: min_dist = target_line - line; best_item = item
            iterator += 1
        if best_item:
            self.symbol_tree.scrollToItem(best_item)
            self.symbol_tree.setCurrentItem(best_item)
            best_item.setBackground(0, QBrush(QColor(255, 242, 204)))
            best_item.setForeground(0, QBrush(Qt.GlobalColor.black))

    def highlight_node_by_name(self, name):
        iterator = QTreeWidgetItemIterator(self.symbol_tree)
        while iterator.value():
            item = iterator.value()
            node_name = item.data(0, Qt.ItemDataRole.UserRole)
            if node_name == name:
                self.symbol_tree.scrollToItem(item)
                self.symbol_tree.setCurrentItem(item)
                item.setBackground(0, QBrush(QColor(255, 242, 204)))
                item.setForeground(0, QBrush(Qt.GlobalColor.black))
                # Update Graphs
                self.on_symbol_clicked(item, 0)
                break
            iterator += 1

    def on_search_text_changed(self, text):
        if self.search_scope_combo.currentIndex() == 0:
            self.symbol_tree.setVisible(True)
            self.global_result_list.setVisible(False)
            self.filter_tree_recursive(text)

    def on_search_enter_pressed(self):
        query = self.search_input.text().strip()
        if not query: return
        if self.search_scope_combo.currentIndex() == 0: self.filter_tree_recursive(query)
        else: self.perform_global_search(query)

    def filter_tree_recursive(self, query):
        if not self.symbol_tree.topLevelItemCount(): return
        root_item = self.symbol_tree.topLevelItem(0)
        if not query:
            self.reset_visuals(root_item)
            return
        self._apply_filter(root_item, query.lower())

    def _apply_filter(self, item: QTreeWidgetItem, query: str) -> bool:
        name = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        sig = str(item.data(0, Qt.ItemDataRole.UserRole + 1) or "")
        is_match = (query in name.lower()) or (query in sig.lower())
        child_match = False
        for i in range(item.childCount()):
            if self._apply_filter(item.child(i), query): child_match = True
        should_show = is_match or child_match
        item.setHidden(not should_show)
        if should_show:
            item.setExpanded(True)
            item.setBackground(0, QBrush(QColor(255, 242, 204) if is_match else Qt.GlobalColor.transparent))
        else: item.setExpanded(False)
        return should_show

    def reset_visuals(self, item: QTreeWidgetItem):
        item.setHidden(False)
        item.setBackground(0, QBrush(Qt.GlobalColor.transparent))
        item.setExpanded(item.parent() is None)
        for i in range(item.childCount()): self.reset_visuals(item.child(i))

    def perform_global_search(self, query):
        if not self.project_root_path: return
        self.symbol_tree.setVisible(False)
        self.global_result_list.setVisible(True)
        self.global_result_list.clear()
        
        results = []
        escaped_query = re.escape(query)
        pattern = re.compile(rf"{escaped_query}", re.IGNORECASE)

        for root, dirs, files in os.walk(self.project_root_path):
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.vs'}]
            for file in files:
                full_path = os.path.join(root, file)
                parser = parser_factory.get_parser(full_path)
                if parser:
                    try:
                        node = parser.parse(full_path)
                        if node:
                            matches = self._search_node_recursive(node, pattern)
                            results.extend(matches)
                    except Exception as e:
                        logger.debug(f"Error searching in {full_path}: {e}")
        
        if not results:
            self.global_result_list.addItem("No results found.")
            return

        for res in results:
            item = QListWidgetItem(f"[{res['kind']}] {res['name']} \n   📍 {res['path']} (Line {res['line']})")
            item.setData(Qt.ItemDataRole.UserRole, res['path'])
            item.setData(Qt.ItemDataRole.UserRole + 1, res['line'])
            self.global_result_list.addItem(item)
            
    def _search_node_recursive(self, node: SymbolNode, pattern):
        matches = []
        target = (node.name + (node.signature or ""))
        if pattern.search(target):
            if node.kind != 'file':
                matches.append({'name': node.signature or node.name, 'kind': node.kind, 'path': node.path, 'line': node.start_line})
        for child in node.children: matches.extend(self._search_node_recursive(child, pattern))
        return matches

    def on_global_result_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        line = item.data(Qt.ItemDataRole.UserRole + 1)
        if path:
            idx = self.file_model.index(path)
            self.file_tree.setCurrentIndex(idx)
            self.file_tree.scrollTo(idx)
            self.on_file_clicked(idx, target_line=line)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())