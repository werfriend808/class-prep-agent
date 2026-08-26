"""Google Docs 문서 생성/수정 REST API 연동 (종합 프로젝트: 학생 활동지 → Google Docs).

Notion 연동(notion_writer.py)은 MCP(notion-mcp-server)를 통했지만, 여기서는
REST API(google-api-python-client)로 직접 붙는다. 공식 Google Docs MCP
서버(docsmcp.googleapis.com)는 아직 Developer Preview고 read_doc/update_doc만
있고 문서 생성 tool이 없으며, 원격 OAuth-HTTP라 Notion 때처럼 로컬 stdio
프로세스를 띄우는 방식이 아니라 우리 앱이 직접 원격 MCP OAuth 클라이언트를
새로 구현해야 해서 부담이 컸다. 스펙 문서가 "MCP만으로 구현하기 어려우면
REST API를 병행할 수 있다"고 명시적으로 허용하고 있어 REST API로 결정함
(2026-08-10, [[project_class_prep_agent_stage3]] 메모리 참고).

인증: OAuth 2.0 Desktop-app flow(google_auth.py에 있음, forms_writer.py와
공유). 최초 1회 로컬 브라우저 인증 후 token.json에 갱신 토큰을 캐시해서,
이후 실행부터는 브라우저 없이 자동 갱신된다. scope는 documents(문서 내용
읽기/쓰기)와 drive.file(이 앱이 만든 파일만 접근 — 기존 드라이브 전체에
접근하는 광범위한 drive 스코프보다 안전)만 쓴다.
"""
from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import GOOGLE_DOCS_FOLDER_ID
from .google_auth import GoogleAuthError, get_credentials


class GoogleDocsWriteError(RuntimeError):
    """문서 생성/본문 작성 실패를 UI에 알리기 위한 예외."""


def _credentials_or_raise():
    try:
        return get_credentials()
    except GoogleAuthError as exc:
        raise GoogleDocsWriteError(str(exc)) from exc


def _drive_service():
    return build("drive", "v3", credentials=_credentials_or_raise())


def _docs_service():
    return build("docs", "v1", credentials=_credentials_or_raise())


def _doc_metadata(title: str, folder_id: str | None, default_folder_id: str) -> dict[str, Any]:
    """Drive files().create에 보낼 body를 조립한다 (네트워크 호출 없는 순수 함수, 테스트용으로 분리)."""
    metadata: dict[str, Any] = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    target_folder = folder_id or default_folder_id
    if target_folder:
        metadata["parents"] = [target_folder]
    return metadata


def _replace_body_requests(end_index: int, text: str) -> list[dict]:
    """현재 문서의 endIndex와 새 text로 batchUpdate에 보낼 requests 배열을 조립한다.

    네트워크 호출 없는 순수 함수로 분리해서 endIndex 경계값(빈 문서 vs 내용
    있는 문서)을 단위 테스트로 바로 검증할 수 있게 했다.
    """
    requests: list[dict] = []
    if end_index > 2:
        # 문서 끝의 개행 문자는 지울 수 없어서 endIndex - 1까지만 지운다.
        requests.append(
            {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}}
        )
    if text:
        requests.append({"insertText": {"location": {"index": 1}, "text": text}})
    return requests


def create_doc(title: str, folder_id: str | None = None) -> dict:
    """빈 Google Doc을 만들고 {"doc_id", "url"}을 반환한다.

    Docs API에도 documents().create가 있지만 Drive 폴더 지정이 안 된다.
    폴더 지정이 필요해서 Drive API files().create로 만든다 (mimeType을
    Google Docs로 지정하면 Drive가 빈 Google Doc으로 만들어준다).
    """
    metadata = _doc_metadata(title, folder_id, GOOGLE_DOCS_FOLDER_ID)

    try:
        file = _drive_service().files().create(body=metadata, fields="id, webViewLink").execute()
    except HttpError as exc:
        raise GoogleDocsWriteError(f"Google Doc 생성 실패: {exc}") from exc

    doc_id = file["id"]
    url = file.get("webViewLink") or f"https://docs.google.com/document/d/{doc_id}/edit"
    return {"doc_id": doc_id, "url": url}


def replace_doc_body(doc_id: str, text: str) -> None:
    """문서 본문 전체를 text로 덮어쓴다 (Notion writer의 "replace_content"와 같은 역할).

    최초 생성 시 본문 삽입과, 나중에 수정 요청을 반영할 때(edit-propagation)
    둘 다 이 함수 하나로 처리한다. Docs API에는 "전체 교체" 메서드가 따로
    없어서, 기존 내용 끝 인덱스를 조회해 지우고(deleteContentRange) 새로
    넣는(insertText) 두 요청을 batchUpdate 하나로 묶어서 보낸다.
    """
    service = _docs_service()
    try:
        doc = service.documents().get(documentId=doc_id).execute()
    except HttpError as exc:
        raise GoogleDocsWriteError(f"Google Doc 조회 실패: {exc}") from exc

    end_index = doc.get("body", {}).get("content", [{}])[-1].get("endIndex", 1)
    requests = _replace_body_requests(end_index, text)

    if not requests:
        return

    try:
        service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    except HttpError as exc:
        raise GoogleDocsWriteError(f"Google Doc 본문 작성 실패: {exc}") from exc


def create_and_write_doc(title: str, text: str, folder_id: str | None = None) -> dict:
    """create_doc + replace_doc_body를 묶은 편의 함수. {"doc_id", "url"} 반환."""
    result = create_doc(title, folder_id=folder_id)
    replace_doc_body(result["doc_id"], text)
    return result
