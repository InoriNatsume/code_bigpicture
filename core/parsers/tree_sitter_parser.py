import os
import importlib
from typing import Optional, Dict, List
from core.symbol_node import SymbolNode
from core.parsers.base_parser import BaseParser
from utils.logger import logger

# Tree-sitter 라이브러리 임포트
try:
    from tree_sitter import Parser, Language
    HAS_TREESITTER = True
except ImportError:
    HAS_TREESITTER = False
    logger.warning("Tree-sitter library not found. Please install 'tree-sitter'.")

class TreeSitterParser(BaseParser):
    """
    Tree-sitter를 사용하여 다국어 코드를 분석하는 파서.
    (Tree-sitter 0.22+ 최신 API 대응: set_language 제거됨)
    """

    # 언어별 노드 타입 매핑
    NODE_TYPE_MAP = {
        'python': {
            'class': ['class_definition'],
            'function': ['function_definition', 'async_function_definition']
        },
        'javascript': {
            'class': ['class_declaration'],
            'function': ['function_declaration', 'method_definition', 'arrow_function', 'generator_function']
        },
        'typescript': {
            'class': ['class_declaration', 'interface_declaration', 'enum_declaration'],
            'function': ['function_declaration', 'method_definition', 'function_signature']
        },
        'java': {
            'class': ['class_declaration', 'interface_declaration', 'enum_declaration'],
            'function': ['method_declaration', 'constructor_declaration']
        },
        'go': {
            'class': ['type_declaration'],
            'function': ['function_declaration', 'method_declaration']
        },
        'cpp': {
            'class': ['class_specifier', 'struct_specifier', 'concept_definition'],
            'function': ['function_definition', 'template_function']
        },
        'cuda': {
            'class': ['class_specifier', 'struct_specifier'],
            'function': ['function_definition', 'kernel_definition']
        },
        'c_sharp': {
            'class': ['class_declaration', 'struct_declaration', 'interface_declaration', 'enum_declaration'],
            'function': ['method_declaration', 'constructor_declaration']
        },
        'rust': {
            'class': ['struct_item', 'enum_item', 'trait_item', 'impl_item'], 
            'function': ['function_item']
        },
        'vue': {
            'class': [], 
            'function': [] 
        },
        'svelte': {
            'class': [],
            'function': []
        }
    }

    # 파일 확장자 -> (Tree-sitter 언어 이름, 패키지 모듈 이름)
    EXT_TO_LANG = {
        '.py': ('python', 'tree_sitter_python'),
        '.js': ('javascript', 'tree_sitter_javascript'),
        '.jsx': ('javascript', 'tree_sitter_javascript'),
        '.ts': ('typescript', 'tree_sitter_typescript'),
        '.tsx': ('typescript', 'tree_sitter_typescript'),
        '.java': ('java', 'tree_sitter_java'),
        '.go': ('go', 'tree_sitter_go'),
        '.cpp': ('cpp', 'tree_sitter_cpp'),
        '.c': ('cpp', 'tree_sitter_cpp'),
        '.cc': ('cpp', 'tree_sitter_cpp'),
        '.h': ('cpp', 'tree_sitter_cpp'),
        '.hpp': ('cpp', 'tree_sitter_cpp'),
        '.cu': ('cuda', 'tree_sitter_cuda'),
        '.cuh': ('cuda', 'tree_sitter_cuda'),
        '.cs': ('c_sharp', 'tree_sitter_c_sharp'),
        '.rs': ('rust', 'tree_sitter_rust'),
        '.vue': ('vue', 'tree_sitter_vue'),
        '.svelte': ('svelte', 'tree_sitter_svelte'),
    }

    def __init__(self):
        # [수정됨] 최신 버전에서는 여기서 Parser()를 미리 생성하지 않습니다.
        self._loaded_languages = {}

    def _get_language_info(self, file_path: str):
        _, ext = os.path.splitext(file_path)
        return self.EXT_TO_LANG.get(ext.lower(), (None, None))

    def _load_language(self, lang_name: str, package_name: str):
        if lang_name in self._loaded_languages:
            return self._loaded_languages[lang_name]

        try:
            lang_module = importlib.import_module(package_name)
            # Tree-sitter 0.22+ 방식: Language(capsule)
            language = Language(lang_module.language())
            self._loaded_languages[lang_name] = language
            return language
        except ImportError:
            # 패키지가 없을 경우 조용히 무시 (혹은 로깅)
            logger.debug(f"Skipping import: {package_name} not installed.")
            return None
        except Exception as e:
            logger.error(f"Error loading language {lang_name}: {e}")
            return None

    def parse(self, file_path: str, project_root: str = "") -> Optional[SymbolNode]:
        if not HAS_TREESITTER:
            return None

        lang_name, pkg_name = self._get_language_info(file_path)
        if not lang_name:
            return None

        code_text = self._read_file_safe(file_path)
        if not code_text:
            return None

        try:
            language = self._load_language(lang_name, pkg_name)
            if not language:
                return None

            # [핵심 수정] Parser 생성 시 언어 객체를 직접 전달해야 함 (API 변경 대응)
            parser = Parser(language)
            
            tree = parser.parse(bytes(code_text, "utf8"))
            
            root_node = SymbolNode(
                name=os.path.basename(file_path),
                kind="file",
                start_line=1,
                end_line=len(code_text.splitlines()),
                path=file_path
            )

            self._traverse_tree(tree.root_node, root_node, lang_name, code_text.splitlines())
            
            return root_node

        except Exception as e:
            logger.error(f"Tree-sitter parse error in {file_path}: {e}")
            return None

    def _traverse_tree(self, ts_node, parent_symbol: SymbolNode, lang_name: str, source_lines: List[str]):
        """AST 순회"""
        symbol_kind = self._check_node_kind(ts_node.type, lang_name)
        current_symbol = parent_symbol

        if symbol_kind:
            name = self._extract_name(ts_node, source_lines)
            
            start_row = ts_node.start_point[0]
            if 0 <= start_row < len(source_lines):
                signature = source_lines[start_row].strip()
            else:
                signature = name

            new_node = SymbolNode(
                name=name,
                kind=symbol_kind,
                start_line=ts_node.start_point[0] + 1,
                end_line=ts_node.end_point[0] + 1,
                path=parent_symbol.path,
                signature=signature
            )
            parent_symbol.add_child(new_node)
            current_symbol = new_node

        for child in ts_node.children:
            self._traverse_tree(child, current_symbol, lang_name, source_lines)

    def _check_node_kind(self, node_type: str, lang_name: str) -> Optional[str]:
        config = self.NODE_TYPE_MAP.get(lang_name, {})
        
        # Vue/Svelte 대응
        if lang_name in ['vue', 'svelte']:
            if node_type in self.NODE_TYPE_MAP['javascript']['function'] or \
               node_type in self.NODE_TYPE_MAP['typescript']['function']:
                return 'function'
            if node_type in self.NODE_TYPE_MAP['javascript']['class'] or \
               node_type in self.NODE_TYPE_MAP['typescript']['class']:
                return 'class'

        if node_type in config.get('class', []):
            return 'class'
        if node_type in config.get('function', []):
            return 'function'
        return None

    def _extract_name(self, node, source_lines: List[str]) -> str:
        for child in node.children:
            if child.type in ('identifier', 'name', 'type_identifier', 'function_declarator', 'field_identifier'):
                if child.type == 'function_declarator':
                     for subchild in child.children:
                         if subchild.type in ('identifier', 'field_identifier'):
                             child = subchild
                             break
                
                r1, c1 = child.start_point
                r2, c2 = child.end_point
                if r1 < len(source_lines):
                    return source_lines[r1][c1:c2]
        return "anonymous"