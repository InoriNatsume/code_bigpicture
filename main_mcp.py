import os
import sys
import argparse
from typing import List, Dict, Any, Optional

# FastMCP 라이브러리 임포트
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("Error: 'mcp' library not found. Please install it using 'pip install mcp'.")
    sys.exit(1)

from core.parser_factory import parser_factory
from core.symbol_node import SymbolNode
from utils.logger import logger
from utils.file_utils import read_file_safe

# MCP 서버 초기화
mcp = FastMCP("Code-Context-Bridge")

# 전역 프로젝트 루트 경로 (명령행 인자 또는 환경 변수로 설정)
_project_root: Optional[str] = None

def get_project_root() -> Optional[str]:
    """전역 프로젝트 루트 경로를 반환합니다."""
    return _project_root

def set_project_root(path: str) -> None:
    """전역 프로젝트 루트 경로를 설정합니다."""
    global _project_root
    if os.path.exists(path) and os.path.isdir(path):
        _project_root = os.path.abspath(path)
        logger.info(f"Project root set to: {_project_root}")
    else:
        logger.warning(f"Invalid project root path: {path}")

# --- Helper Functions ---

def _generate_skeleton_string(node: SymbolNode, indent: int = 0) -> str:
    """
    SymbolNode 트리를 텍스트 형태의 스켈레톤으로 변환
    v4.2: 데코레이터와 베이스 클래스 정보 포함
    """
    spaces = "  " * indent
    result = ""
    
    # 파일 노드는 이름만 출력, 그 외(클래스/함수)는 시그니처 출력
    if node.kind == "file":
        result += f"{spaces}[File] {node.name}\n"
    else:
        # 데코레이터가 있으면 먼저 출력
        if node.decorators:
            for decorator in node.decorators:
                result += f"{spaces}{decorator}\n"
        
        # 시그니처가 있으면 시그니처를, 없으면 이름만
        display = node.signature if node.signature else f"{node.kind} {node.name}"
        result += f"{spaces}{display} (Lines: {node.start_line}-{node.end_line})"
        
        # 베이스 클래스가 있으면 표시
        if node.base_classes:
            result += f" -> Inherits: {', '.join(node.base_classes)}"
        
        result += "\n"

    for child in node.children:
        result += _generate_skeleton_string(child, indent + 1)
    
    return result

def _search_recursive(node: SymbolNode, query: str) -> List[Dict]:
    """(Design Doc 5.2) 재귀적 심볼 검색 - 이름만 검색"""
    results = []
    # 검색어 매칭 (대소문자 무시)
    if query.lower() in node.name.lower():
        results.append(node.to_dict())
    
    for child in node.children:
        results.extend(_search_recursive(child, query))
    return results

def _search_recursive_with_signature(node: SymbolNode, query: str) -> List[Dict]:
    """재귀적 심볼 검색 - 이름과 시그니처 모두 검색"""
    results = []
    # 검색 대상: 이름 + 시그니처
    search_target = (node.name + (node.signature or "")).lower()
    if query.lower() in search_target:
        results.append(node.to_dict())
    
    for child in node.children:
        results.extend(_search_recursive_with_signature(child, query))
    return results

# --- MCP Tools (Exposed to AI) ---

@mcp.tool()
def get_project_structure(path: Optional[str] = None, depth: int = 2) -> str:
    """
    프로젝트의 폴더 구조와 파일 목록을 트리 형태로 리턴합니다.
    Args:
        path: 분석할 루트 디렉토리 경로 (지정하지 않으면 전역 설정 사용)
        depth: 탐색할 폴더 깊이 (기본값: 2)
    """
    # 경로가 지정되지 않으면 전역 설정 사용
    if path is None:
        path = get_project_root()
        if path is None:
            return "Error: Project root not set. Please specify 'path' parameter or set PROJECT_ROOT environment variable."
    
    logger.info(f"[MCP] Tool called: get_project_structure(path={path}, depth={depth})")
    
    if not os.path.exists(path):
        return f"Error: Path not found: {path}"

    output = []
    base_depth = path.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(path):
        curr_depth = root.count(os.sep) - base_depth
        if curr_depth > depth:
            # 하위 디렉토리는 탐색 중지 (os.walk 최적화를 위해 dirs 비움)
            dirs[:] = []
            continue

        # 무시할 폴더들
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.idea', '.vscode'}]
        
        indent = "  " * curr_depth
        folder_name = os.path.basename(root) or path
        output.append(f"{indent}📂 {folder_name}/")
        
        for f in files:
            output.append(f"{indent}  📄 {f}")
            
    return "\n".join(output)

@mcp.tool()
def read_skeleton(file_path: str) -> str:
    """
    [Core] 파일의 전체 코드를 읽지 않고, 클래스와 함수 정의부(Signature)만 추출하여 리턴합니다.
    토큰을 절약하면서 코드 구조를 파악할 때 사용합니다.
    """
    logger.info(f"[MCP] Tool called: read_skeleton({file_path})")
    
    if not os.path.exists(file_path):
        return "Error: File not found."

    parser = parser_factory.get_parser(file_path)
    if not parser:
        return f"Error: No parser available for this file type ({os.path.basename(file_path)})."

    # 파싱 실행
    root_node = parser.parse(file_path)
    if not root_node:
        return "Error: Failed to parse file or file is empty."

    # 트리 -> 문자열 변환
    return _generate_skeleton_string(root_node)

@mcp.tool()
def search_symbol(query: str, project_root: Optional[str] = None) -> str:
    """
    프로젝트 전체에서 특정 함수/클래스 이름을 검색합니다.
    이름만 검색하므로 정확하고 빠릅니다.
    주의: 파일이 많을 경우 시간이 소요될 수 있습니다.
    Args:
        query: 검색할 심볼 이름
        project_root: 프로젝트 루트 경로 (지정하지 않으면 전역 설정 사용)
    """
    # 경로가 지정되지 않으면 전역 설정 사용
    if project_root is None:
        project_root = get_project_root()
        if project_root is None:
            return "Error: Project root not set. Please specify 'project_root' parameter or set PROJECT_ROOT environment variable."
    
    logger.info(f"[MCP] Tool called: search_symbol(query='{query}', root='{project_root}')")
    
    results = []
    
    # 프로젝트 전체 순회
    for root, _, files in os.walk(project_root):
        for file in files:
            full_path = os.path.join(root, file)
            
            # 파서가 지원하는 파일인지 확인
            parser = parser_factory.get_parser(full_path)
            if parser:
                try:
                    # 파싱
                    node = parser.parse(full_path)
                    if node:
                        # 메모리 내 검색
                        matches = _search_recursive(node, query)
                        if matches:
                            results.extend(matches)
                except Exception as e:
                    logger.error(f"Error searching file {full_path}: {e}")

    if not results:
        return "No symbols found matching the query."

    # 결과 포맷팅
    output = [f"Found {len(results)} matches for '{query}':"]
    for res in results:
        output.append(f"- [{res['kind']}] {res['name']} in {res['path']} (Line: {res['range']['start']})")
    
    return "\n".join(output)

@mcp.tool()
def search_symbol_with_signature(query: str, project_root: Optional[str] = None) -> str:
    """
    프로젝트 전체에서 심볼 이름과 시그니처를 모두 검색합니다.
    이름만으로 찾기 어려운 경우(예: 파라미터 이름으로 검색)에 유용합니다.
    주의: 검색 범위가 넓어져 결과가 많을 수 있고, 파일이 많을 경우 시간이 소요될 수 있습니다.
    Args:
        query: 검색할 키워드 (심볼 이름 또는 시그니처 내의 문자열)
        project_root: 프로젝트 루트 경로 (지정하지 않으면 전역 설정 사용)
    """
    # 경로가 지정되지 않으면 전역 설정 사용
    if project_root is None:
        project_root = get_project_root()
        if project_root is None:
            return "Error: Project root not set. Please specify 'project_root' parameter or set PROJECT_ROOT environment variable."
    
    logger.info(f"[MCP] Tool called: search_symbol_with_signature(query='{query}', root='{project_root}')")
    
    results = []
    
    # 프로젝트 전체 순회
    for root, _, files in os.walk(project_root):
        for file in files:
            full_path = os.path.join(root, file)
            
            # 파서가 지원하는 파일인지 확인
            parser = parser_factory.get_parser(full_path)
            if parser:
                try:
                    # 파싱
                    node = parser.parse(full_path)
                    if node:
                        # 메모리 내 검색 (시그니처 포함)
                        matches = _search_recursive_with_signature(node, query)
                        if matches:
                            results.extend(matches)
                except Exception as e:
                    logger.error(f"Error searching file {full_path}: {e}")

    if not results:
        return "No symbols found matching the query."

    # 결과 포맷팅
    output = [f"Found {len(results)} matches for '{query}' (including signatures):"]
    for res in results:
        sig_info = f" - {res['signature']}" if res.get('signature') else ""
        output.append(f"- [{res['kind']}] {res['name']}{sig_info} in {res['path']} (Line: {res['range']['start']})")
    
    return "\n".join(output)

@mcp.tool()
def read_full_code(file_path: str, start_line: int = 1, end_line: int = -1) -> str:
    """
    특정 파일의 실제 코드를 읽어옵니다. 줄 번호를 지정하여 부분 조회가 가능합니다.
    """
    logger.info(f"[MCP] Tool called: read_full_code({file_path}, {start_line}-{end_line})")
    
    if not os.path.exists(file_path):
        return "Error: File not found."

    # 공통 파일 읽기 유틸리티 사용 (다중 인코딩 지원)
    content = read_file_safe(file_path)
    if not content:
        return "Error: Failed to read file (binary or unsupported encoding)."
    
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    if end_line == -1 or end_line > total_lines:
        end_line = total_lines
    
    # 1-based index adjustment
    selected_lines = lines[start_line-1 : end_line]
    return "".join(selected_lines)

if __name__ == "__main__":
    # 명령행 인자 파싱
    parser = argparse.ArgumentParser(description="Code-Context-Bridge MCP Server")
    parser.add_argument(
        "--project-root",
        type=str,
        help="프로젝트 루트 디렉토리 경로 (환경 변수 PROJECT_ROOT로도 설정 가능)"
    )
    args = parser.parse_args()
    
    # 프로젝트 루트 설정 우선순위: 명령행 인자 > 환경 변수
    project_root = None
    if args.project_root:
        project_root = args.project_root
    elif "PROJECT_ROOT" in os.environ:
        project_root = os.environ["PROJECT_ROOT"]
    
    if project_root:
        set_project_root(project_root)
        logger.info(f"Project root configured: {_project_root}")
    else:
        logger.info("Project root not set. Tools will require 'project_root' parameter.")
    
    # FastMCP는 기본적으로 stdio 방식을 지원합니다.
    logger.info("Starting Code-Context-Bridge MCP Server...")
    mcp.run()