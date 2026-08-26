"""Google Forms 퀴즈 생성/수정 REST API 연동 (종합 프로젝트: Quiz Activity).

google_docs_writer.py와 같은 이유로 MCP 대신 REST API를 쓴다 — Google
Workspace MCP 지원 제품 목록(Gmail/Drive/Docs/Sheets/Slides/Calendar/Chat/
People)에 Forms는 아예 없다(2026-08-10, 2026-08-12 재확인 — 공식·커뮤니티
서버 모두 없음). Docs 때와 달리 "MCP는 있는데 부족해서 REST API로" 갔던
것과도 다르게, 여기는 MCP 선택지 자체가 없다.

인증은 google_auth.py의 get_credentials()/SCOPES를 Docs 연동과 그대로
공유한다 — Forms API의 forms.create/batchUpdate/setPublishSettings 세
메서드 모두 공식 문서 기준 허용 스코프가 drive/drive.file/forms.body 중
하나면 되고, 이미 요청 중인 drive.file(이 앱이 만든 파일에만 접근)로
충분해서 forms.body를 별도로 추가하지 않았다.

**폼 게시 관련 주의(2026-08-12 조사):** 2026년 6월 30일부터 Forms API로
만든 폼은 기본이 "게시 안 됨" 상태로 바뀌었다(구글 공식 공지, "API changes
to Google Forms"). 그대로 두면 응답을 전혀 못 받는 빈 폼이 되므로,
create_quiz_form()이 문항을 다 채운 뒤 setPublishSettings()로 명시적으로
게시(isPublished=True, isAcceptingResponses=True)한다.
"""
from __future__ import annotations

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_auth import GoogleAuthError, get_credentials

# 폼 ID로 편집 화면/응답 화면 URL을 직접 구성한다 (forms.create 응답에도
# 없는 필드라 문서에 나온 표준 URL 패턴을 그대로 쓴다).
EDITOR_URL_TEMPLATE = "https://docs.google.com/forms/d/{form_id}/edit"
RESPONDER_URL_TEMPLATE = "https://docs.google.com/forms/d/{form_id}/viewform"


class FormsWriteError(RuntimeError):
    """폼 생성/문항 작성/게시 실패를 UI에 알리기 위한 예외."""


def _forms_service():
    try:
        creds = get_credentials()
    except GoogleAuthError as exc:
        raise FormsWriteError(str(exc)) from exc
    return build("forms", "v1", credentials=creds)


def _question_item(question: dict, index: int) -> dict:
    """quiz.generate_quiz()가 만든 문항 dict 하나를 Forms API의 Item(RADIO 객관식)으로 변환한다.

    correctAnswers를 넣은 RADIO 문항은 Forms가 자동 채점 대상으로 인식한다
    (공식 가이드 "Set up quiz grading options" 기준 — Checkbox/Radio/
    Dropdown만 자동 채점 가능). 네트워크 호출이 없는 순수 함수라 단위
    테스트로 검증한다.
    """
    correct_value = question["options"][question["correct_index"]]
    explanation = question.get("explanation", "")
    when_wrong_text = f"아쉬워요, 정답은 '{correct_value}'예요." + (f" {explanation}" if explanation else "")
    return {
        "title": question["question"],
        "questionItem": {
            "question": {
                "required": True,
                "grading": {
                    "pointValue": 1,
                    "correctAnswers": {"answers": [{"value": correct_value}]},
                    "whenRight": {"text": "정답이에요!"},
                    "whenWrong": {"text": when_wrong_text},
                },
                "choiceQuestion": {
                    "type": "RADIO",
                    "options": [{"value": opt} for opt in question["options"]],
                },
            }
        },
    }


def _create_item_requests(questions: list[dict]) -> list[dict]:
    """문항 리스트를 batchUpdate용 createItem 요청 배열로 조립한다 (순수 함수)."""
    return [
        {"createItem": {"item": _question_item(q, i), "location": {"index": i}}}
        for i, q in enumerate(questions)
    ]


def _delete_all_items_requests(item_count: int) -> list[dict]:
    """기존 문항을 전부 지우는 deleteItem 요청 배열을 조립한다 (역순 — 앞에서부터
    지우면 남은 항목들의 index가 밀려서 다음 삭제 대상이 어긋난다)."""
    return [{"deleteItem": {"location": {"index": i}}} for i in range(item_count - 1, -1, -1)]


def create_quiz_form(title: str, questions: list[dict]) -> dict:
    """새 Google Forms 퀴즈를 만들고, 객관식 문항을 채우고, 게시까지 한다.

    {"form_id", "edit_url", "responder_url"}을 반환한다.
    """
    service = _forms_service()

    try:
        form = service.forms().create(body={"info": {"title": title}}).execute()
    except HttpError as exc:
        raise FormsWriteError(f"Google Forms 생성 실패: {exc}") from exc

    form_id = form["formId"]

    requests: list[dict] = [
        {
            "updateSettings": {
                "settings": {"quizSettings": {"isQuiz": True}},
                "updateMask": "quizSettings.isQuiz",
            }
        }
    ]
    requests.extend(_create_item_requests(questions))

    try:
        service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()
    except HttpError as exc:
        raise FormsWriteError(f"Google Forms 문항 작성 실패: {exc}") from exc

    _publish(service, form_id)

    return {
        "form_id": form_id,
        "edit_url": EDITOR_URL_TEMPLATE.format(form_id=form_id),
        "responder_url": RESPONDER_URL_TEMPLATE.format(form_id=form_id),
    }


def _publish(service, form_id: str) -> None:
    try:
        service.forms().setPublishSettings(
            formId=form_id,
            body={
                "publishSettings": {
                    "publishState": {"isPublished": True, "isAcceptingResponses": True}
                },
                "updateMask": "publishState",
            },
        ).execute()
    except HttpError as exc:
        raise FormsWriteError(f"Google Forms 게시 실패: {exc}") from exc


def replace_quiz_questions(form_id: str, questions: list[dict]) -> None:
    """기존 폼의 문항을 전부 지우고 새 문항으로 교체한다 (수정 요청 반영용).

    Forms API에는 "전체 교체" 메서드가 따로 없어서, 현재 문항 개수를 조회한
    뒤 전부 지우고(deleteItem, 역순) 새로 채운다(createItem) —
    google_docs_writer.replace_doc_body()의 delete-then-insert 패턴과 같은
    방식이다. isQuiz 설정과 게시 상태는 최초 생성 때 이미 되어 있으므로
    다시 건드리지 않는다.
    """
    service = _forms_service()

    try:
        form = service.forms().get(formId=form_id).execute()
    except HttpError as exc:
        raise FormsWriteError(f"Google Forms 조회 실패: {exc}") from exc

    existing_items = form.get("items", [])
    requests = _delete_all_items_requests(len(existing_items)) + _create_item_requests(questions)

    if not requests:
        return

    try:
        service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()
    except HttpError as exc:
        raise FormsWriteError(f"Google Forms 문항 수정 실패: {exc}") from exc
