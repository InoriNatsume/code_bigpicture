import os
from collections import defaultdict
from core.parser_factory import parser_factory

class CallGraph:
    def __init__(self):
        # Key: Called Function Name
        # Value: List of { 'path': str, 'caller': str, 'line': int, 'snippet': str }
        self.incoming_calls = defaultdict(list)
        
        # Key: (FilePath, Caller Function Name)
        # Value: List of { 'called': str, 'line': int, 'snippet': str }
        self.outgoing_calls = defaultdict(list)
        
        self.definitions = defaultdict(list)

    def build_graph(self, project_root, progress_callback=None, cancel_check=None):
        self.incoming_calls.clear()
        self.outgoing_calls.clear()
        self.definitions.clear()
        
        all_files = []
        exclude = {'.git', '__pycache__', 'node_modules', '.vs', 'build', 'dist', 'venv'}
        
        for root, dirs, files in os.walk(project_root):
            # 취소 확인
            if cancel_check and cancel_check():
                # 취소 시 부분 데이터 초기화
                self.incoming_calls.clear()
                self.outgoing_calls.clear()
                self.definitions.clear()
                return
            dirs[:] = [d for d in dirs if d not in exclude]
            for f in files:
                if f.endswith(('.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', '.go')):
                    all_files.append(os.path.join(root, f))

        total = len(all_files)
        for i, file_path in enumerate(all_files):
            # 취소 확인
            if cancel_check and cancel_check():
                # 취소 시 부분 데이터 초기화
                self.incoming_calls.clear()
                self.outgoing_calls.clear()
                self.definitions.clear()
                return
                
            if progress_callback: 
                progress_callback(i, total, file_path)
            
            try:
                parser = parser_factory.get_parser(file_path)
                if parser:
                    # 1. 모든 함수/클래스 정의 추출
                    if hasattr(parser, 'extract_definitions'):
                        definitions_list = parser.extract_definitions(file_path)
                        for func_name in definitions_list:
                            # 중복 경로 추가 방지
                            if file_path not in self.definitions[func_name]:
                                self.definitions[func_name].append(file_path)
                    
                    # 2. 함수 호출 정보 추출
                    if hasattr(parser, 'extract_calls'):
                        # calls = { 'caller': [ {'called':..., 'line':..., 'snippet':...} ] }
                        calls = parser.extract_calls(file_path)
                        
                        for caller_func, call_list in calls.items():
                            # 중복 경로 추가 방지
                            if file_path not in self.definitions[caller_func]:
                                self.definitions[caller_func].append(file_path)
                            
                            # Outgoing 저장
                            self.outgoing_calls[(file_path, caller_func)] = call_list
                            
                            # Incoming 저장
                            for call_info in call_list:
                                callee = call_info['called']
                                self.incoming_calls[callee].append({
                                    'path': file_path,
                                    'caller': caller_func,
                                    'line': call_info['line'],
                                    'snippet': call_info['snippet']
                                })
            except Exception as e:
                from utils.logger import logger
                logger.error(f"Error processing file {file_path}: {e}")

    def get_incoming(self, func_name):
        return self.incoming_calls.get(func_name, [])

    def get_outgoing(self, file_path, func_name):
        """
        Outgoing 호출 정보를 가져옵니다.
        경로 정규화 및 함수 이름 매칭을 개선했습니다.
        """
        if not file_path or not func_name:
            return []
        
        # 정확한 키로 먼저 시도
        key = (file_path, func_name)
        if key in self.outgoing_calls:
            return self.outgoing_calls[key]
        
        # 파일 경로 정규화 (절대 경로로 통일)
        try:
            # 상대 경로인 경우 절대 경로로 변환 시도
            if not os.path.isabs(file_path):
                # 프로젝트 루트가 있다면 절대 경로로 변환
                normalized_path = os.path.normpath(os.path.abspath(file_path))
            else:
                normalized_path = os.path.normpath(file_path)
            
            # 정규화된 경로로 재시도
            for (f, fn) in self.outgoing_calls.keys():
                try:
                    f_normalized = os.path.normpath(os.path.abspath(f)) if not os.path.isabs(f) else os.path.normpath(f)
                    if f_normalized == normalized_path and fn == func_name:
                        return self.outgoing_calls[(f, fn)]
                except (ValueError, OSError):
                    # 경로 변환 실패 시 원본 경로로 비교
                    if os.path.normpath(f) == normalized_path and fn == func_name:
                        return self.outgoing_calls[(f, fn)]
            
            # 함수 이름이 부분적으로 일치하는 경우 (예: "sample_sde" vs "sample_sde(self, ...)")
            # 함수 이름만 추출하여 비교
            func_name_only = func_name.split('(')[0].strip() if '(' in func_name else func_name.strip()
            for (f, fn) in self.outgoing_calls.keys():
                try:
                    f_normalized = os.path.normpath(os.path.abspath(f)) if not os.path.isabs(f) else os.path.normpath(f)
                    if f_normalized == normalized_path:
                        fn_only = fn.split('(')[0].strip() if '(' in fn else fn.strip()
                        if fn_only == func_name_only:
                            return self.outgoing_calls[(f, fn)]
                except (ValueError, OSError):
                    # 경로 변환 실패 시 원본 경로로 비교
                    if os.path.normpath(f) == normalized_path:
                        fn_only = fn.split('(')[0].strip() if '(' in fn else fn.strip()
                        if fn_only == func_name_only:
                            return self.outgoing_calls[(f, fn)]
        except Exception as e:
            from utils.logger import logger
            logger.warning(f"Error in get_outgoing for {file_path}:{func_name}: {e}")
        
        return []

call_graph = CallGraph()