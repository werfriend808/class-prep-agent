"""환경변수 로딩 및 공통 설정."""
import os
from dotenv import load_dotenv

load_dotenv()


def _setting(name: str, default: str = "") -> str:
    """환경변수 -> Streamlit secrets 순으로 설정값을 찾는다.

    로컬에선 `.env`(load_dotenv)로, Streamlit Community Cloud에선 앱 설정의
    Secrets(TOML)로 같은 키를 넣는다. Streamlit은 최상위 secrets를 환경변수로도
    노출하지만, 그 시점이 이 모듈 import보다 늦을 수 있어서 st.secrets를 직접 한
    번 더 확인한다. streamlit이 없거나 secrets 파일이 없으면(테스트, 스크립트)
    조용히 기본값으로 떨어진다.
    """
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # noqa: BLE001 — secrets.toml 없음, streamlit 미설치 등
        value = None
    return str(value) if value not in (None, "") else default


NOTION_API_KEY = _setting("NOTION_API_KEY")
ANTHROPIC_API_KEY = _setting("ANTHROPIC_API_KEY", "")

# 프로젝트 전체(실전 1의 요약/질의분류 + 실전 2의 계획안 생성)에서 쓰는
# LLM provider 선택. "anthropic"(기본값) | "clova". llm.py의 get_client()
# (Claude 전용, 하위 호환용으로 남겨둠)는 더 이상 실전 1에서 직접 쓰이지 않고,
# summarizer.py/query_router.py/lesson_plan.py 모두 llm.complete()를 통해
# 이 설정을 따른다.
LLM_PROVIDER = _setting("LLM_PROVIDER", "anthropic")
# 네이버 클로바 스튜디오(HyperCLOVA X) API 키. 클로바 스튜디오 콘솔에서 발급.
# OpenAI 호환 엔드포인트(https://clovastudio.stream.ntruss.com/v1/openai/)로 호출한다.
HCX_API_KEY = _setting("HCX_API_KEY", "")
HCX_MODEL = _setting("HCX_MODEL", "HCX-005")

# FILTER 유형 검색(학년/과목/날짜/학기)에 쓸 "수업 자료" 데이터소스(데이터베이스) ID.
# notion-mcp-server의 search 또는 retrieve-a-database tool로 샘플 데이터셋을
# 한 번 조회해서 값을 채워 넣는다. TOPIC/TITLE 검색에는 필요 없다.
NOTION_DATA_SOURCE_ID = _setting("NOTION_DATA_SOURCE_ID", "")

# 실전 프로젝트 2: 생성한 수업계획안 페이지를 하위 페이지로 만들어 넣을 부모
# Notion 페이지 ID. 이 페이지에 Integration이 Connections로 연결되어 있어야 한다.
NOTION_LESSON_PLAN_PARENT_ID = _setting("NOTION_LESSON_PLAN_PARENT_ID", "")

# 종합 프로젝트: 학생 활동지를 Google Docs로 쓰기 위한 OAuth Desktop-app 인증.
# MCP 대신 REST API(google-api-python-client) 직접 연동을 쓰기로 결정함
# (공식 Google Docs MCP는 아직 Developer Preview에 create 기능이 없고, 원격
# OAuth-HTTP라 커스텀 클라이언트를 새로 짜야 해서 부담이 큼 — 스펙 문서가
# "MCP만으로 어려우면 REST API 병행 가능"이라고 명시적으로 허용).
# credentials.json: Google Cloud Console에서 발급한 OAuth 클라이언트(Desktop app) 원본.
# token.json: 최초 인증 후 자동 생성되는 갱신 토큰 캐시. 둘 다 .gitignore에 있음.
GOOGLE_CREDENTIALS_PATH = _setting("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = _setting("GOOGLE_TOKEN_PATH", "token.json")
# 학생 활동지 Google Doc을 만들 때 넣어줄 Drive 폴더 ID (선택). 비어있으면 내 드라이브 최상위에 생성.
GOOGLE_DOCS_FOLDER_ID = _setting("GOOGLE_DOCS_FOLDER_ID", "")

# 앱 로케일 — "ko"(기본, 한국/NCIC) | "us"(영어/Common Core Math, Phase 3).
# 이 값 하나로 교육과정 provider와 UI/프롬프트 언어가 함께 바뀐다
# (chat_app.py가 이 값에 따라 화면 전체를 한국어/영어 버전으로 분기한다).
LOCALE = _setting("LOCALE", "ko")

# 교육과정 provider 선택. 명시적으로 지정하지 않으면 위 LOCALE에서 유도한다
# ("ko" -> "ncic", "us" -> "common_core_math") — src/curriculum/__init__.py의
# get_provider() 참고. LOCALE과 별개로 CURRICULUM_PROVIDER만 따로 지정하는
# 것도 가능하다(예: 영어 UI 없이 provider만 바꿔서 테스트하고 싶을 때).
CURRICULUM_PROVIDER = _setting("CURRICULUM_PROVIDER") or (
    "common_core_math" if LOCALE == "us" else "ncic"
)

# 데모 모드: Notion/Google Docs/Google Forms로의 외부 쓰기를 전부 끄고, 생성
# 결과는 앱 화면 + 다운로드 버튼으로만 제공한다. 공개 배포(Streamlit Community
# Cloud)용이다 — 지금의 Notion(Internal Integration 토큰 1개)과 Google(Desktop
# OAuth + token.json) 연동은 둘 다 "개발자 본인 계정 1개" 전제라서, 공개 URL에서
# 켜두면 모든 방문자의 결과물이 개발자 워크스페이스/드라이브에 쓰이게 된다.
# DEMO_MODE=1로 명시하거나, NOTION_API_KEY가 아예 없으면 자동으로 켜진다
# (예전엔 NOTION_API_KEY가 없으면 import 시점에 RuntimeError로 앱이 아예 안
# 켜졌다 — 처음 써보는 사람이 키 없이도 핵심 기능을 체험할 수 있게 바꿨다).
DEMO_MODE = _setting("DEMO_MODE").lower() in ("1", "true", "yes") or not NOTION_API_KEY

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

# 익명 사용 지표(src/usage.py) 저장소. Supabase 프로젝트의 URL과 서버용(secret/
# service_role) 키. 둘 다 비어 있으면 이벤트를 저장하지 않고 로그로만 남긴다.
# 이 키는 Streamlit 서버에서만 쓰이고 브라우저로 내려가지 않는다.
SUPABASE_URL = _setting("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = _setting("SUPABASE_KEY", "")

# LLM_PROVIDER=anthropic일 때 쓸 Claude 모델. 공개 데모는 비용 때문에
# CLAUDE_MODEL=claude-haiku-5-5로 배포하고, 품질이 부족하면 코드 수정 없이
# secrets에서 모델 ID만 바꾼다. (SUMMARY_MODEL은 예전 이름 — 하위 호환용 별칭)
CLAUDE_MODEL = _setting("CLAUDE_MODEL", "claude-sonnet-5")
SUMMARY_MODEL = CLAUDE_MODEL
