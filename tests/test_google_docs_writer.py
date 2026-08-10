"""google_docs_writer.py 단위 테스트.

notion_writer.py 테스트와 같은 원칙: 실제 네트워크 호출(Drive/Docs API,
OAuth 브라우저 플로우)이 필요한 부분은 로컬에서 수동 검증(scripts/
verify_google_docs_auth.py)으로 남겨두고, 여기서는 네트워크 없이 검증
가능한 순수 로직(요청 body 조립, batchUpdate 요청 배열 조립)만 다룬다.
"""
from src.google_docs_writer import _doc_metadata, _replace_body_requests


def test_doc_metadata_without_folder():
    metadata = _doc_metadata("제목", None, "")
    assert metadata["name"] == "제목"
    assert metadata["mimeType"] == "application/vnd.google-apps.document"
    assert "parents" not in metadata


def test_doc_metadata_uses_explicit_folder_over_default():
    metadata = _doc_metadata("제목", "explicit-folder", "default-folder")
    assert metadata["parents"] == ["explicit-folder"]


def test_doc_metadata_falls_back_to_default_folder():
    metadata = _doc_metadata("제목", None, "default-folder")
    assert metadata["parents"] == ["default-folder"]


def test_replace_body_requests_on_empty_doc_skips_delete():
    # 빈 문서는 endIndex가 1(빈 문서의 개행 문자 하나만 있음)이라 지울 내용이 없다.
    requests = _replace_body_requests(1, "새 내용")
    assert len(requests) == 1
    assert requests[0]["insertText"]["text"] == "새 내용"


def test_replace_body_requests_on_existing_doc_deletes_then_inserts():
    requests = _replace_body_requests(50, "새 내용")
    assert len(requests) == 2
    assert requests[0]["deleteContentRange"]["range"] == {"startIndex": 1, "endIndex": 49}
    assert requests[1]["insertText"]["text"] == "새 내용"


def test_replace_body_requests_with_empty_text_only_deletes():
    requests = _replace_body_requests(50, "")
    assert len(requests) == 1
    assert "deleteContentRange" in requests[0]
