import os
from abc import ABC, abstractmethod
from typing import Optional
from core.symbol_node import SymbolNode
from utils.logger import logger

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
        UTF-8로 시도하고 실패하면 에러를 로깅하고 빈 문자열을 반환합니다.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return ""

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # 바이너리 파일이거나 인코딩 문제 시 스킵
            logger.warning(f"Skipping binary or non-utf8 file: {file_path}")
            return ""
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return ""

    def _get_relative_path(self, file_path: str, project_root: str) -> str:
        """절대 경로를 프로젝트 루트 기준 상대 경로로 변환"""
        try:
            return os.path.relpath(file_path, project_root)
        except ValueError:
            return file_path