# Project Design Document: Code-Context-Bridge (CCB) v2.0
(Inc. MCP Server & Search Features)

## 1. 프로젝트 개요 (Overview)
본 프로젝트는 대규모 소스 코드의 **구조(Structure)**와 **심볼(Symbol)**을 분석하여, **1) 인간을 위한 GUI 뷰어**와 **2) AI를 위한 MCP(Model Context Protocol) 인터페이스**를 동시에 제공하는 "하이브리드 코드 분석 엔진"이다.

---

## 2. 시스템 아키텍처 (System Architecture)

핵심 파싱 로직을 공유 라이브러리 형태로 분리하여 GUI와 MCP 서버가 공유한다.

```mermaid
graph TD
    User[User] --> GUI[PyQt6 GUI]
    AI[LLM (Claude/GPT)] --> MCP[MCP Server]
    
    subgraph Core Engine (Library)
        GUI --> ParserFactory
        MCP --> ParserFactory
        ParserFactory --> TreeSitter[Tree-sitter Parsers]
        TreeSitter --> SymbolNode[Data Model]
    end
    
    TreeSitter --> FileSystem[Source Files]
```

### 2.1 디렉토리 구조 (Directory Structure)
```
/
├── main_gui.py            # [EntryPoint] 사람용 GUI
├── main_mcp.py            # [EntryPoint] AI용 MCP 서버
├── core/                  # [Shared] 핵심 로직 (GUI 의존성 없음)
│   ├── parser_factory.py
│   ├── parsers/
│   └── symbol_node.py
├── utils/
│   └── logger.py          # Stream(Console) + File Logging
└── logs/                  # 실행 로그 저장
```

---

## 3. 핵심 기능 명세 (Feature Specifications)

### 3.1 로깅 시스템 (Real-time Console Logging)
*   **Dual Output:** 모든 로그는 `logs/debug.log` 파일과 `CMD Console(StreamHandler)`에 동시에 출력되어야 한다.
*   **목적:** 개발자가 실행 중인 파싱 상태, 에러 발생 파일, 검색 쿼리 처리 현황을 실시간으로 모니터링.

### 3.2 심볼 검색 (Symbol Search) - GUI 전용
*   **UI:** 메인 윈도우 상단에 검색 바(Search Bar) 배치.
*   **Logic (Recursive Filter):**
    *   사용자 입력 시 실시간(또는 엔터 입력 시) 트리 필터링.
    *   검색어와 일치하는 노드(Node)는 강조 표시.
    *   **Rule:** 자식 노드가 매칭되면 부모 노드는 접히지 않고(Expanded) 보여야 함. 매칭되지 않는 노드는 숨김(Hidden).

---

## 4. MCP 서버 통합 (MCP Server Integration) - AI 전용

AI 에이전트가 로컬 프로젝트를 직접 분석할 수 있도록 표준 MCP 프로토콜을 구현한다.
초기엔 로컬(Stdio)로 구현하고, 추후 웹(SSE) 확장을 고려하여 **FastMcp** (Python SDK)를 사용한다.

### 4.1 제공 도구 (Exposed Tools)
AI에게 제공할 함수(Tools) 목록:

1.  **`get_project_structure(path: str, depth: int = 2)`**
    *   설명: 프로젝트의 폴더 구조와 파일 목록만 빠르게 리턴.
2.  **`search_symbol(query: str, project_root: str)`**
    *   설명: 프로젝트 전체에서 특정 함수/클래스 이름 검색. 해당 파일 경로와 라인 번호 리턴.
3.  **`read_skeleton(file_path: str)`**
    *   설명: **[핵심]** 파일의 전체 코드를 읽지 않고, `def`, `class` 정의부(Signature)만 추출하여 리턴. (토큰 절약)
4.  **`read_full_code(file_path: str, start_line: int, end_line: int)`**
    *   설명: 스켈레톤을 보고 AI가 특정 구현부가 필요하다고 판단하면, 해당 라인의 실제 코드를 조회.

### 4.2 실행 방식
*   **CLI 명령:** `python main_mcp.py --path "C:/TargetProject"`
*   AI 에이전트 설정 파일에 위 명령어를 등록하여 사용.

---

## 5. 상세 구현 가이드 (Implementation Details)

### 5.1 데이터 모델 업데이트 (`core/symbol_node.py`)
MCP에서 JSON 직렬화를 위해 `to_dict()` 메서드 추가.

```python
@dataclass
class SymbolNode:
    # ... (기존 필드) ...
    
    def to_dict(self):
        """MCP 응답용 JSON 변환"""
        return {
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "children": [child.to_dict() for child in self.children]
        }
```

### 5.2 검색 로직 (Filtering Strategy)
GUI와 MCP가 공유할 검색 유틸리티 함수.

```python
def search_recursive(node: SymbolNode, query: str) -> List[Dict]:
    """
    심볼 트리를 순회하며 쿼리와 일치하는 노드 검색.
    GUI에서는 뷰 필터링에 쓰고, MCP에서는 결과 리스트 반환에 씀.
    """
    results = []
    if query.lower() in node.name.lower():
        results.append(node)
    
    for child in node.children:
        results.extend(search_recursive(child, query))
    return results
```

---

## 6. 에이전트 작업 지시 사항 (Instructions for Agent)

1.  **Core Separation First:** Before building the GUI, implement the `core/` package. Ensure `SymbolNode` and `BaseParser` work independently of PyQt.
2.  **Console Visible:** Ensure `logging.StreamHandler` is attached to the root logger so the user can see parsing progress in the terminal window.
3.  **MCP Ready:** Implement the parsing logic such that `get_skeleton()` returns a clean string. The MCP server will wrapper this function.
4.  **Error Resilience:** If a parser encounters a binary file or encoding issue, log it to Console and **skip** it. Do not crash the MCP server or GUI.

---