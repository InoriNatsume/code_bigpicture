import os
from abc import ABC, abstractmethod
from typing import Optional
from core.symbol_node import SymbolNode
from utils.logger import logger
from utils.file_utils import read_file_safe

class BaseParser(ABC):
    """
    모든 언어 파서의 기본 클래스.
    공통 파일 읽기 로직과 인터페이스를 정의합니다.
    """

    @abstractmethod
    def parse(self, file_path: str, project_root: str = "") -> Optional[SymbolNode]:
        """
        파일을 파싱하여 SymbolNode 트리를 반환해야 합니다.
        파싱 실패 시 None을 반환합니다.
        """
        pass

    def _read_file_safe(self, file_path: str) -> str:
        """
        파일을 안전하게 읽습니다. (Design Doc 6.4: Error Resilience)
        공통 유틸리티 함수를 사용합니다.
        """
        return read_file_safe(file_path)

    def _get_relative_path(self, file_path: str, project_root: str) -> str:
        """절대 경로를 프로젝트 루트 기준 상대 경로로 변환"""
        try:
            return os.path.relpath(file_path, project_root)
        except ValueError:
            return file_path