import os
from utils.logger import logger

def read_file_safe(file_path: str) -> str:
    """
    파일을 안전하게 읽습니다. (Design Doc 6.4: Error Resilience)
    UTF-8로 시도하고 실패하면 다른 인코딩을 시도합니다.
    GUI와 MCP 서버에서 공통으로 사용하는 유틸리티 함수.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return ""

    # UTF-8로 먼저 시도
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # 다른 인코딩 시도 (일반적인 인코딩들)
        encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                    logger.debug(f"Successfully read {file_path} with encoding: {encoding}")
                    return content
            except (UnicodeDecodeError, LookupError):
                continue
        
        # 모든 인코딩 실패 시 바이너리로 간주
        logger.warning(f"Skipping binary or unsupported encoding file: {file_path}")
        return ""
    except PermissionError:
        logger.warning(f"Permission denied reading file: {file_path}")
        return ""
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}")
        return ""

