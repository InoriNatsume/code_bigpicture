# Changelog

## [v4.2] - Python 특화 기능 추가

### 주요 기능
- **데코레이터 지원**: Python, TypeScript, JavaScript의 데코레이터 정보 추출 및 표시
  - GUI: 함수/클래스 시그니처 앞에 데코레이터 표시 (예: `@torch.no_grad() def forward(...)`)
  - MCP: `read_skeleton` 응답에 데코레이터 포함
  - 툴팁: 데코레이터 목록 별도 표시
  
- **클래스 상속 정보**: 베이스 클래스 추출 및 표시
  - GUI: 클래스 툴팁에 "Inherits from: ..." 표시
  - MCP: skeleton 응답에 상속 정보 포함
  - Python: `class MyModel(nn.Module)` → `['nn.Module']`
  - TypeScript/JavaScript/Java: `extends`/`implements` 지원
  
- **LLM용 컨텍스트 복사**: AI 에이전트 사용을 위한 원클릭 복사 기능
  - 우클릭 메뉴: "🤖 Copy Context for LLM" 옵션 추가
  - 마크다운 형식 출력: 파일 경로, 심볼명, 라인 번호, 데코레이터, 코드 스니펫 포함
  - 상태바 피드백: 복사 성공 시 "✅ Context copied to clipboard for LLM!" 메시지

### 데이터 모델 변경
- `SymbolNode`: `decorators: List[str]`, `base_classes: List[str]` 필드 추가
- `to_dict()`: 선택적 필드로 JSON 응답에 포함 (비어있으면 생략)

### 파서 개선
- `TreeSitterParser._extract_decorators()`: 다중 언어 데코레이터 추출
  - Python: `decorated_definition` → `decorator` 노드 파싱
  - TypeScript/JavaScript: `decorator` 노드 지원
- `TreeSitterParser._extract_base_classes()`: 상속 관계 추출
  - Python: `argument_list` 파싱
  - TypeScript/JavaScript: `class_heritage`, `extends_clause`
  - Java: `superclass`, `super_interfaces`

### 사용 사례
- **PyTorch 개발**: `@torch.no_grad()`, `@staticmethod` 등 데코레이터 정보 즉시 파악
- **ComfyUI 커스텀 노드**: `nn.Module` 상속 구조 추적
- **웹 UI 사용**: MCP 없이도 ChatGPT/Claude에 코드 컨텍스트 빠르게 공유

---



## [v4.1] - Call Graph 기능 추가

### 주요 기능
- **Call Graph 구축 및 시각화**: 함수 호출 관계를 추적하여 Incoming/Outgoing References 표시
- **트리 구조 네비게이션**: 호출 체인을 트리 형태로 탐색 가능
- **자동 인덱싱**: 프로젝트 열기 시 백그라운드에서 Call Graph 자동 구축

### 잠재적 문제점 및 주의사항

#### 1. 메모리 사용량
- **문제**: 대규모 프로젝트(수천 개 파일)에서 Call Graph 구축 시 메모리 사용량이 급증할 수 있음
- **영향**: `call_graph.py`의 `incoming_calls`, `outgoing_calls`, `definitions` 딕셔너리가 모든 호출 정보를 메모리에 저장
- **권장사항**: 
  - 매우 큰 프로젝트의 경우 인덱싱 시간이 길어질 수 있음
  - 필요시 디스크 기반 캐싱 또는 증분 인덱싱 고려

#### 2. 함수 이름 매칭 정확도
- **문제**: 함수 시그니처가 포함된 이름과 실제 호출 이름 간 매칭이 복잡함
- **위치**: `core/call_graph.py:71-78` (함수 이름 부분 추출 로직)
- **영향**: 
  - `"sample_sde(self, ...)"` vs `"sample_sde"` 같은 경우 처리
  - 메서드 체이닝이나 동적 호출은 추적 불가
- **제한사항**: Tree-sitter 파서의 한계로 일부 호출 패턴은 감지되지 않을 수 있음

#### 3. 순환 참조 처리 한계
- **문제**: `max_depth=10`으로 제한되어 있지만, 깊은 호출 체인에서는 정보 손실 가능
- **위치**: `main_gui.py:252, 300` (`_build_incoming_tree`, `_build_outgoing_tree`)
- **영향**: 매우 깊은 호출 체인은 표시되지 않을 수 있음
- **현재 대응**: `visited` set으로 순환 참조 방지, 하지만 깊이 제한으로 인한 정보 손실 가능

#### 4. 메서드 추출 정확도
- **문제**: `obj.method()` 형태에서 `method`만 추출하는 로직이 복잡함
- **위치**: `core/parsers/tree_sitter_parser.py:167-202` (`_extract_called_name`)
- **영향**: 
  - 동적 속성 접근 (`getattr(obj, 'method')()`)은 추적 불가
  - 일부 언어별 특수 케이스에서 메서드 이름 추출 실패 가능

#### 5. `get_outgoing()` 성능 이슈
- **문제**: `get_outgoing()` 메서드가 모든 키를 순회하며 경로 정규화를 반복 수행
- **위치**: `core/call_graph.py:71-124`
- **영향**: 대규모 프로젝트에서 호출 시 성능 저하 가능 (O(n) 복잡도)
- **권장사항**: 경로 정규화를 인덱싱 시점에 수행하여 키를 정규화된 경로로 저장

### v4.1.1 개선 사항 (2025-01-XX)
- ✅ 인덱싱 취소 기능 구현
- ✅ 에러 처리 강화 (모든 예외에 로깅 추가)
- ✅ 동시성 문제 해결 (인덱싱 중 UI 비활성화)
- ✅ 경로 정규화 로직 개선 (절대 경로 통일, 예외 처리 강화)
- ✅ 파일 인코딩 처리 개선 (다중 인코딩 자동 시도)
- ✅ 중복 호출 정보 처리 개선

### v4.1.2 개선 사항 (2025-01-XX)
- ✅ UI 상태 복원 개선 (`set_call_graph_enabled()`에서 제목 복원 로직 추가)
- ✅ 전역 스코프 호출 추적 추가 (모듈 레벨 함수 호출도 Call Graph에 포함)
- ✅ 중복 정의 경로 누적 방지 (`definitions`에 중복 경로 추가 방지)
- ✅ MCP 서버 인코딩 처리 통일 (`utils/file_utils.py` 공통 유틸리티 함수 생성 및 사용)
- ✅ 전역 검색 결과 클릭 시 라인 번호 활용 (해당 심볼로 자동 스크롤)
- ✅ 인덱싱 취소 시 부분 데이터 초기화 (취소 시 명시적으로 데이터 clear)
- ✅ 파일 경로 유효성 검사 강화 (`on_symbol_clicked()`에서 경로 검증 추가)
