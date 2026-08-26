"""forms_writer.py 단위 테스트.

google_docs_writer.py 테스트와 같은 원칙: 실제 네트워크 호출(Forms API,
OAuth 브라우저 플로우)이 필요한 부분은 로컬에서 수동 검증
(scripts/verify_forms_auth.py)으로 남겨두고, 여기서는 네트워크 없이 검증
가능한 순수 로직(문항 → Item 변환, batchUpdate 요청 배열 조립)만 다룬다.
"""
from src.forms_writer import (
    _create_item_requests,
    _delete_all_items_requests,
    _question_item,
)


def _sample_question(**overrides) -> dict:
    base = {
        "question": "삼각형의 내각의 합은?",
        "options": ["90도", "180도", "270도", "360도"],
        "correct_index": 1,
        "explanation": "삼각형의 세 내각의 합은 항상 180도입니다.",
    }
    base.update(overrides)
    return base


def test_question_item_uses_radio_choice_question():
    item = _question_item(_sample_question(), 0)
    choice = item["questionItem"]["question"]["choiceQuestion"]
    assert choice["type"] == "RADIO"
    assert [o["value"] for o in choice["options"]] == ["90도", "180도", "270도", "360도"]


def test_question_item_correct_answer_matches_correct_index():
    item = _question_item(_sample_question(correct_index=2), 0)
    grading = item["questionItem"]["question"]["grading"]
    assert grading["correctAnswers"]["answers"] == [{"value": "270도"}]
    assert grading["pointValue"] == 1


def test_question_item_when_wrong_includes_explanation():
    item = _question_item(_sample_question(), 0)
    when_wrong = item["questionItem"]["question"]["grading"]["whenWrong"]["text"]
    assert "180도" in when_wrong
    assert "세 내각의 합" in when_wrong


def test_question_item_title_is_question_text():
    item = _question_item(_sample_question(question="이건 무슨 문제?"), 0)
    assert item["title"] == "이건 무슨 문제?"


def test_create_item_requests_places_items_at_sequential_indexes():
    questions = [_sample_question(), _sample_question(question="두 번째 문제")]
    requests = _create_item_requests(questions)
    assert len(requests) == 2
    assert requests[0]["createItem"]["location"] == {"index": 0}
    assert requests[1]["createItem"]["location"] == {"index": 1}
    assert requests[1]["createItem"]["item"]["title"] == "두 번째 문제"


def test_delete_all_items_requests_goes_in_reverse_order():
    # 역순으로 지워야 한다 — 앞에서부터 지우면 남은 항목들의 index가 밀린다.
    requests = _delete_all_items_requests(3)
    indexes = [r["deleteItem"]["location"]["index"] for r in requests]
    assert indexes == [2, 1, 0]


def test_delete_all_items_requests_empty_when_no_items():
    assert _delete_all_items_requests(0) == []
