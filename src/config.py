"""환경변수 로딩 및 공통 설정."""
import os
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 프로젝트 전체(실전 1의 요약/질의분류 + 실전 2의 계획안 생성)에서 쓰는
# LLM provider 선택. "anthropic"(기본값) | "clova". llm.py의 get_client()
# (Claude 전용, 하위 호환용으로 남겨둠)는 더 이상 실전 1에서 직접 쓰이지 않고,
# summarizer.py/query_router.py/lesson_plan.py 모두 llm.complete()를 통해
# 이 설정을 따른다.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
# 네이버 클로바 스튜디오(HyperCLOVA X) API 키. 클로바 스튜디오 콘솔에서 발급.
# OpenAI 호환 엔드포인트(https://clovastudio.stream.ntruss.com/v1/openai/)로 호출한다.
HCX_API_KEY = os.getenv("HCX_API_KEY", "")
HCX_MODEL = os.getenv("HCX_MODEL", "HCX-005")

# FILTER 유형 검색(학년/과목/날짜/학기)에 쓸 "수업 자료" 데이터소스(데이터베이스) ID.
# notion-mcp-server의 search 또는 retrieve-a-database tool로 샘플 데이터셋을
# 한 번 조회해서 값을 채워 넣는다. TOPIC/TITLE 검색에는 필요 없다.
NOTION_DATA_SOURCE_ID = os.getenv("NOTION_DATA_SOURCE_ID", "")

# 실전 프로젝트 2: 생성한 수업계획안 페이지를 하위 페이지로 만들어 넣을 부모
# Notion 페이지 ID. 이 페이지에 Integration이 Connections로 연결되어 있어야 한다.
NOTION_LESSON_PLAN_PARENT_ID = os.getenv("NOTION_LESSON_PLAN_PARENT_ID", "")

# 종합 프로젝트: 학생 활동지를 Google Docs로 쓰기 위한 OAuth Desktop-app 인증.
# MCP 대신 REST API(google-api-python-client) 직접 연동을 쓰기로 결정함
# (공식 Google Docs MCP는 아직 Developer Preview에 create 기능이 없고, 원격
# OAuth-HTTP라 커스텀 클라이언트를 새로 짜야 해서 부담이 큼 — 스펙 문서가
# "MCP만으로 어려우면 REST API 병행 가능"이라고 명시적으로 허용).
# credentials.json: Google Cloud Console에서 발급한 OAuth 클라이언트(Desktop app) 원본.
# token.json: 최초 인증 후 자동 생성되는 갱신 토큰 캐시. 둘 다 .gitignore에 있음.
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
# 학생 활동지 Google Doc을 만들 때 넣어줄 Drive 폴더 ID (선택). 비어있으면 내 드라이브 최상위에 생성.
GOOGLE_DOCS_FOLDER_ID = os.getenv("GOOGLE_DOCS_FOLDER_ID", "")

if not NOTION_API_KEY:
    raise RuntimeError(
        ".env에 NOTION_API_KEY가 설정되어 있지 않습니다. "
        "Notion Integration 토큰을 .env에 넣어주세요."
    )

if LLM_PROVIDER == "clova":
    if not HCX_API_KEY:
        print(
            "[경고] LLM_PROVIDER=clova인데 HCX_API_KEY가 .env에 없습니다. "
            "요약/질의분류(실전 1), 수업계획안 생성(실전 2) 모두 실패합니다."
        )
elif not ANTHROPIC_API_KEY:
    print(
        "[경고] ANTHROPIC_API_KEY가 .env에 없습니다. "
        "요약/질의분류(실전 1), 수업계획안 생성(실전 2) 모두 실패합니다."
    )

# 요약에 사용할 Claude 모델
SUMMARY_MODEL = "claude-sonnet-5"
