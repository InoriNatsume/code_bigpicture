import os
import importlib
import re
from typing import Optional, Dict, List, Set
from core.symbol_node import SymbolNode
from core.parsers.base_parser import BaseParser
from utils.logger import logger

try:
    from tree_sitter import Parser, Language
    HAS_TREESITTER = True
except ImportError:
    HAS_TREESITTER = False
    logger.warning("Tree-sitter library not found.")

class TreeSitterParser(BaseParser):
    """
    v4.1: Call Graph 정확도 향상 (Snippet 및 Line Number 추출)
    v4.2: 데코레이터 및 클래스 상속 정보 추출 지원
    """
    
    CALL_TYPE_MAP = {
        'python': ['call'],
        'javascript': ['call_expression'],
        'typescript': ['call_expression'],
        'java': ['method_invocation', 'object_creation_expression'],
        'cpp': ['call_expression'],
        'c_sharp': ['invocation_expression'],
        'go': ['call_expression'],
        'rust': ['call_expression'],
        'vue': ['call_expression'],
        'svelte': ['call_expression'],
        'cuda': ['call_expression'],
    }

    NODE_TYPE_MAP = {
        'python': { 'class': ['class_definition'], 'function': ['function_definition', 'async_function_definition'], 'params': ['parameters'] },
        'javascript': { 'class': ['class_declaration'], 'function': ['function_declaration', 'method_definition', 'arrow_function'], 'params': ['formal_parameters'] },
        'typescript': { 'class': ['class_declaration'], 'function': ['function_declaration', 'method_definition'], 'params': ['formal_parameters', 'function_signature'] },
        'java': { 'class': ['class_declaration'], 'function': ['method_declaration'], 'params': ['formal_parameters'] },
        'cpp': { 'class': ['class_specifier'], 'function': ['function_definition'], 'params': ['parameter_list'] },
        'c_sharp': { 'class': ['class_declaration'], 'function': ['method_declaration'], 'params': ['parameter_list'] },
        'cuda': { 'class': ['class_specifier'], 'function': ['function_definition'], 'params': ['parameter_list'] },
    }

    EXT_TO_LANG = {
        '.py': ('python', 'tree_sitter_python'),
        '.js': ('javascript', 'tree_sitter_javascript'),
        '.jsx': ('javascript', 'tree_sitter_javascript'),
        '.ts': ('typescript', 'tree_sitter_typescript'),
        '.tsx': ('typescript', 'tree_sitter_typescript'),
        '.java': ('java', 'tree_sitter_java'),
        '.cpp': ('cpp', 'tree_sitter_cpp'),
        '.h': ('cpp', 'tree_sitter_cpp'),
        '.cs': ('c_sharp', 'tree_sitter_c_sharp'),
        '.go': ('go', 'tree_sitter_go'),
        '.rs': ('rust', 'tree_sitter_rust'),
        '.vue': ('vue', 'tree_sitter_vue'),
        '.svelte': ('svelte', 'tree_sitter_svelte'),
        '.cu': ('cuda', 'tree_sitter_cpp'),
        '.cuh': ('cuda', 'tree_sitter_cpp'),
    }

    def __init__(self):
        self._loaded_languages = {}

    def _get_language_info(self, file_path: str):
        _, ext = os.path.splitext(file_path)
        return self.EXT_TO_LANG.get(ext.lower(), (None, None))

    def _load_language(self, lang_name: str, package_name: str):
        if lang_name in self._loaded_languages: return self._loaded_languages[lang_name]
        try:
            mod = importlib.import_module(package_name)
            lang = Language(mod.language())
            self._loaded_languages[lang_name] = lang
            return lang
        except: return None

    def parse(self, file_path: str, project_root: str = "") -> Optional[SymbolNode]:
        if not HAS_TREESITTER: return None
        lang, pkg = self._get_language_info(file_path)
        if not lang: return None
        text = self._read_file_safe(file_path)
        if not text: return None
        
        try:
            language = self._load_language(lang, pkg)
            if not language: return None
            parser = Parser(language)
            tree = parser.parse(bytes(text, "utf8"))
            
            root = SymbolNode(os.path.basename(file_path), "file", 1, len(text.splitlines()), file_path)
            self._traverse_tree(tree.root_node, root, lang, text.splitlines(), bytes(text, "utf8"))
            return root
        except Exception as e:
            logger.error(f"Parse error {file_path}: {e}")
            return None

    def _traverse_tree(self, node, parent, lang, lines, b_text):
        kind = self._check_node_kind(node.type, lang)
        current = parent
        if kind:
            name = self._extract_name(node, lines)
            sig = self._extract_signature(node, b_text, lang, name)
            sig = re.sub(r'\s+', ' ', sig).strip()
            
            # 데코레이터 추출 (함수/클래스)
            decorators = self._extract_decorators(node, lines, lang)
            
            # 베이스 클래스 추출 (클래스만)
            base_classes = []
            if kind == 'class':
                base_classes = self._extract_base_classes(node, lines, lang)
            
            new_node = SymbolNode(
                name, kind, 
                node.start_point[0]+1, node.end_point[0]+1, 
                parent.path, sig,
                decorators=decorators,
                base_classes=base_classes
            )
            parent.add_child(new_node)
            current = new_node
        for child in node.children:
            self._traverse_tree(child, current, lang, lines, b_text)

    def _extract_decorators(self, node, lines, lang) -> List[str]:
        """
        함수나 클래스 정의 앞의 데코레이터들을 추출합니다.
        Python: decorated_definition -> decorator 노드들
        TypeScript/JavaScript: decorator 노드들
        """
        decorators = []
        
        if lang == 'python':
            # Python의 경우 부모 노드가 decorated_definition인지 확인
            parent = node.parent
            if parent and parent.type == 'decorated_definition':
                for child in parent.children:
                    if child.type == 'decorator':
                        # 데코레이터 전체 텍스트 추출 (@ 포함)
                        r1, c1 = child.start_point
                        r2, c2 = child.end_point
                        if r1 < len(lines):
                            if r1 == r2:
                                # 한 줄에 있는 경우
                                decorator_text = lines[r1][c1:c2].strip()
                            else:
                                # 여러 줄에 걸친 경우 (드물지만 가능)
                                decorator_text = lines[r1][c1:].strip()
                            decorators.append(decorator_text)
        
        elif lang in ['typescript', 'javascript']:
            # TypeScript/JavaScript decorator 지원
            # decorator 노드를 직접 찾기
            for child in node.children:
                if child.type == 'decorator':
                    r1, c1 = child.start_point
                    r2, c2 = child.end_point
                    if r1 < len(lines):
                        decorator_text = lines[r1][c1:c2].strip()
                        decorators.append(decorator_text)
        
        return decorators

    def _extract_base_classes(self, node, lines, lang) -> List[str]:
        """
        클래스 정의에서 상속받은 베이스 클래스들을 추출합니다.
        Python: argument_list 내의 식별자들
        TypeScript/JavaScript: class_heritage/extends_clause
        Java: superclass/super_interfaces
        """
        base_classes = []
        
        if lang == 'python':
            # Python: class ClassName(Base1, Base2): 형태
            # class_definition -> argument_list
            for child in node.children:
                if child.type == 'argument_list':
                    # argument_list 내부의 모든 식별자/속성 추출
                    base_classes = self._extract_identifiers_from_arguments(child, lines)
                    break
        
        elif lang in ['typescript', 'javascript']:
            # TypeScript/JavaScript: class ClassName extends BaseClass
            for child in node.children:
                if child.type in ['class_heritage', 'extends_clause']:
                    # 상속 표현식에서 클래스명 추출
                    base_classes = self._extract_identifiers_recursive(child, lines)
                    break
        
        elif lang == 'java':
            # Java: extends 및 implements
            for child in node.children:
                if child.type in ['superclass', 'super_interfaces']:
                    base_classes.extend(self._extract_identifiers_recursive(child, lines))
        
        return base_classes

    def _extract_identifiers_from_arguments(self, arg_node, lines) -> List[str]:
        """argument_list에서 식별자들을 추출 (Python 베이스 클래스용)"""
        identifiers = []
        for child in arg_node.children:
            if child.type == 'identifier':
                r1, c1 = child.start_point
                r2, c2 = child.end_point
                if r1 < len(lines):
                    identifiers.append(lines[r1][c1:c2])
            elif child.type == 'attribute':
                # 예: nn.Module 같은 속성 접근
                r1, c1 = child.start_point
                r2, c2 = child.end_point
                if r1 < len(lines):
                    identifiers.append(lines[r1][c1:c2])
        return identifiers

    def _extract_identifiers_recursive(self, node, lines) -> List[str]:
        """재귀적으로 노드에서 식별자들을 추출"""
        identifiers = []
        if node.type == 'identifier':
            r1, c1 = node.start_point
            r2, c2 = node.end_point
            if r1 < len(lines):
                identifiers.append(lines[r1][c1:c2])
        else:
            for child in node.children:
                identifiers.extend(self._extract_identifiers_recursive(child, lines))
        return identifiers


    # --- Improved Call Extraction ---
    def extract_calls(self, file_path: str) -> Dict[str, List[Dict]]:
        """
        Returns: { 'caller_func_name': [ {'called': 'target_func', 'line': 10, 'snippet': 'self.target()'} ] }
        """
        if not HAS_TREESITTER: return {}
        lang, pkg = self._get_language_info(file_path)
        if not lang: return {}
        text = self._read_file_safe(file_path)
        if not text: return {}
        
        try:
            language = self._load_language(lang, pkg)
            parser = Parser(language)
            tree = parser.parse(bytes(text, "utf8"))
            lines = text.splitlines()
            
            calls_map = {} # Key: Caller, Value: List of call details
            self._find_definitions_and_calls(tree.root_node, lang, lines, calls_map, "global")
            return calls_map
        except Exception as e:
            logger.error(f"Error extracting calls from {file_path}: {e}")
            return {}

    def extract_definitions(self, file_path: str) -> List[str]:
        """
        파일에서 정의된 모든 함수와 클래스 이름을 추출합니다.
        Returns: List of function/class names
        """
        if not HAS_TREESITTER: return []
        lang, pkg = self._get_language_info(file_path)
        if not lang: return []
        text = self._read_file_safe(file_path)
        if not text: return []
        
        try:
            language = self._load_language(lang, pkg)
            parser = Parser(language)
            tree = parser.parse(bytes(text, "utf8"))
            lines = text.splitlines()
            
            definitions = []
            self._extract_all_definitions(tree.root_node, lang, lines, definitions)
            return definitions
        except Exception as e:
            logger.error(f"Error extracting definitions from {file_path}: {e}")
            return []

    def _extract_all_definitions(self, node, lang, lines, definitions_list):
        """재귀적으로 모든 함수와 클래스 정의를 추출"""
        kind = self._check_node_kind(node.type, lang)
        if kind in ['function', 'class']:
            name = self._extract_name(node, lines)
            if name and name != "anonymous":
                definitions_list.append(name)
        
        for child in node.children:
            self._extract_all_definitions(child, lang, lines, definitions_list)

    def _find_definitions_and_calls(self, node, lang, lines, calls_map, current_scope):
        kind = self._check_node_kind(node.type, lang)
        new_scope = current_scope
        if kind == 'function':
            new_scope = self._extract_name(node, lines)
            if new_scope not in calls_map: calls_map[new_scope] = []

        if node.type in self.CALL_TYPE_MAP.get(lang, []):
            called_name = self._extract_called_name(node, lines)
            if called_name:
                # 전역 스코프 호출도 추적 (current_scope == "global"인 경우도 처리)
                scope_key = current_scope if current_scope != "global" else "__global__"
                if scope_key not in calls_map:
                    calls_map[scope_key] = []
                # Snippet 추출 (호출 구문 전체)
                r1, c1 = node.start_point
                r2, c2 = node.end_point
                if r1 < len(lines):
                    # 한 줄에 다 있으면 그 줄 전체, 여러 줄이면 첫 줄만
                    snippet = lines[r1].strip()
                    if r2 > r1: snippet = snippet + " ..."
                else: snippet = called_name
                
                # 중복 방지 (같은 라인에서 같은 함수 호출)
                # 이미 같은 라인에 같은 함수가 있는지 확인
                is_duplicate = False
                for existing_call in calls_map[scope_key]:
                    if existing_call['called'] == called_name and existing_call['line'] == r1 + 1:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    calls_map[scope_key].append({
                        'called': called_name,
                        'line': r1 + 1,
                        'snippet': snippet
                    })

        for child in node.children:
            self._find_definitions_and_calls(child, lang, lines, calls_map, new_scope)

    def _extract_called_name(self, node, lines) -> str:
        # Python: call -> function node
        func_node = node.child_by_field_name('function')
        if not func_node: func_node = node.child_by_field_name('name')
        if not func_node and node.child_count > 0: func_node = node.children[0]
        
        if not func_node: return ""

        # obj.method() 처리 -> method만 추출
        if func_node.type == 'attribute':
            # attribute 노드에서 attribute 필드(메서드 이름) 추출
            attr_node = func_node.child_by_field_name('attribute')
            if attr_node:
                r1, c1 = attr_node.start_point
                r2, c2 = attr_node.end_point
                if r1 < len(lines): return lines[r1][c1:c2]
            # attribute 필드가 없으면 전체를 반환
            r1, c1 = func_node.start_point
            r2, c2 = func_node.end_point
            if r1 < len(lines): 
                # "self.method"에서 "method"만 추출 시도
                text = lines[r1][c1:c2]
                if '.' in text:
                    return text.split('.')[-1]
                return text
        elif func_node.type == 'member_expression':
            prop_node = func_node.child_by_field_name('property')
            if prop_node:
                r1, c1 = prop_node.start_point
                r2, c2 = prop_node.end_point
                if r1 < len(lines): return lines[r1][c1:c2]
            
        r1, c1 = func_node.start_point
        r2, c2 = func_node.end_point
        if r1 < len(lines): return lines[r1][c1:c2]
        return ""

    def _extract_signature(self, node, b_text, lang, default):
        p_types = self.NODE_TYPE_MAP.get(lang, {}).get('params', [])
        p_node = None
        for c in node.children:
            if c.type in p_types: p_node = c; break
            if c.type == 'function_declarator':
                for sub in c.children: 
                    if sub.type in p_types: p_node = sub; break
        if p_node: return b_text[node.start_byte:p_node.end_byte].decode('utf-8', 'ignore')
        return default

    def _check_node_kind(self, ntype, lang):
        if lang in ['vue', 'svelte']:
             if ntype in ['function_declaration', 'method_definition']: return 'function'
        conf = self.NODE_TYPE_MAP.get(lang, {})
        if ntype in conf.get('class', []): return 'class'
        if ntype in conf.get('function', []): return 'function'
        return None

    def _extract_name(self, node, lines):
        for c in node.children:
            if c.type in ('identifier', 'name', 'function_declarator'):
                if c.type == 'function_declarator':
                    for sub in c.children:
                        if sub.type == 'identifier': c = sub; break
                r1, c1 = c.start_point
                r2, c2 = c.end_point
                if r1 < len(lines): return lines[r1][c1:c2]
        return "anonymous"