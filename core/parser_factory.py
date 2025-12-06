import os
from typing import Optional
from core.parsers.base_parser import BaseParser
from core.parsers.tree_sitter_parser import TreeSitterParser
from utils.logger import logger

class ParserFactory:
    """
    파일 확장자에 따라 적절한 파서 인스턴스를 반환하는 팩토리 클래스.
    """
    
    def __init__(self):
        # TreeSitterParser 하나로 여러 언어 처리
        self._tree_sitter_parser = TreeSitterParser()

    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        """
        파일 경로(확장자)를 보고 처리 가능한 파서를 반환.
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        # TreeSitterParser가 지원하는 확장자인지 확인
        if ext in TreeSitterParser.EXT_TO_LANG:
            return self._tree_sitter_parser
        
        return None

# 전역 싱글톤
parser_factory = ParserFactory()