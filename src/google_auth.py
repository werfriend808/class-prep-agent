"""Google OAuth 인증 공용 헬퍼 — google_docs_writer.py와 forms_writer.py가 공유.

credentials.json/token.json 기반 OAuth Desktop-app flow는 원래
google_docs_writer.py 안에 Docs 전용으로 만들었지만(2026-08-10), Quiz
Activity를 위해 Google Forms 연동을 추가하면서(2026-08-12) 여기로 옮겨
공유한다. Forms API도 별도 스코프 없이 이미 요청 중인 `drive.file`로
충분하다 — forms.create/batchUpdate/setPublishSettings 세 메서드 모두 공식
문서 기준 허용 스코프가 `drive` / `drive.file` / `forms.body` 중 하나면
되고, `drive.file`은 "이 앱이 만든 파일에만 접근" 스코프라 Forms API로 만든
폼도 포함된다. 그래서 `forms.body`를 새로 추가하지 않았고, 기존
token.json으로 Forms 연동도 별도 재동의 없이 될 것으로 예상한다(실제로
막히면 SCOPES에 forms.body를 추가하고 token.json을 지워서 재동의가
필요하다 — scripts/verify_forms_auth.py로 확인).
"""
from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleAuthError(RuntimeError):
    """OAuth 인증 실패(자격증명 파일 없음 등)를 알리기 위한 예외.

    호출하는 쪽(google_docs_writer.py, forms_writer.py)이 각자의 도메인
    예외(GoogleDocsWriteError, FormsWriteError)로 감싸서 다시 올린다 — UI
    쪽에서 도메인별로 다른 except 절을 유지할 수 있게 하기 위함이다.
    """


def get_credentials() -> Credentials:
    """token.json이 있으면 재사용(+필요시 자동 갱신), 없으면 최초 1회 로컬 브라우저 인증을 띄운다."""
    creds: Credentials | None = None
    if os.path.exists(GOOGLE_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
                raise GoogleAuthError(
                    f"{GOOGLE_CREDENTIALS_PATH}가 없습니다. Google Cloud Console에서 "
                    "OAuth 클라이언트(데스크톱 앱)를 만들고 다운로드한 JSON을 "
                    "이 경로에 저장해주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GOOGLE_TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds
