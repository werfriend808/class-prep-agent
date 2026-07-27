"""환경변수 로딩 및 공통 설정."""
import os
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# FILTER 유형 검색(학년/과목/날짜/학기)에 쓸 "수업 자료" 데이터소스(데이터베이스) ID.
# notion-mcp-server의 search 또는 retrieve-a-database tool로 샘플 데이터셋을
# 한 번 조회해서 값을 채워 넣는다. TOPIC/TITLE 검색에는 필요 없다.
NOTION_DATA_SOURCE_ID = os.getenv("NOTION_DATA_SOURCE_ID", "")

if not NOTION_API_KEY:
    raise RuntimeError(
        ".env에 NOTION_API_KEY가 설정되어 있지 않습니다. "
        "Notion Integration 토큰을 .env에 넣어주세요."
    )

if not ANTHROPIC_API_KEY:
    print(
        "[경고] ANTHROPIC_API_KEY가 .env에 없습니다. "
        "요약 기능(summarizer)을 쓰려면 .env에 키를 추가하세요."
    )

# 요약에 사용할 Claude 모델
SUMMARY_MODEL = "claude-sonnet-5"
