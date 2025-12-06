from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class SymbolNode:
    """
    소스 코드의 구조(파일, 클래스, 함수 등)를 나타내는 트리 노드 데이터 모델.
    GUI와 MCP 서버 모두에서 공통으로 사용됩니다.
    
    v4.2: decorators와 base_classes 필드 추가 (Python 특화 기능)
    """
    name: str
    kind: str             # 'file', 'class', 'method', 'function' 등
    start_line: int       # 1-based index
    end_line: int         # 1-based index
    path: str = ""        # 파일 시스템 경로
    signature: str = ""   # 함수/클래스 정의부 (Skeleton 용)
    decorators: List[str] = field(default_factory=list)  # 데코레이터 목록 (예: ['@torch.no_grad()', '@classmethod'])
    base_classes: List[str] = field(default_factory=list)  # 상속받은 베이스 클래스 목록 (클래스에만 사용)
    children: List['SymbolNode'] = field(default_factory=list)

    def add_child(self, child: 'SymbolNode'):
        """자식 노드 추가"""
        self.children.append(child)

    def to_dict(self) -> Dict[str, Any]:
        """
        MCP 서버 응답 및 JSON 직렬화를 위한 딕셔너리 변환 메서드.
        (Design Document 5.1 준수)
        
        v4.2: decorators와 base_classes 필드 추가
        """
        result = {
            "name": self.name,
            "kind": self.kind,
            "path": self.path,
            "range": {
                "start": self.start_line,
                "end": self.end_line
            },
            "signature": self.signature,
            "children": [child.to_dict() for child in self.children]
        }
        
        # 데코레이터와 베이스 클래스가 있으면 추가 (선택적 필드)
        if self.decorators:
            result["decorators"] = self.decorators
        if self.base_classes:
            result["base_classes"] = self.base_classes
        
        return result