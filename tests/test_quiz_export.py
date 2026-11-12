from src.quiz import quiz_to_markdown


def _draft(locale):
    return {
        "locale": locale,
        "topic": "Fractions",
        "subject": "Math",
        "grade": "5",
        "questions": [
            {"question": "1/2 + 1/4 = ?", "options": ["3/4", "2/6", "1/8", "1"], "correct_index": 0,
             "explanation": "Common denominator 4."},
            {"question": "2/3 of 9?", "options": ["3", "6"], "correct_index": 1},
        ],
    }


def test_quiz_markdown_puts_answers_in_separate_key():
    md = quiz_to_markdown(_draft("us"))
    questions_part, answer_part = md.split("## Answer key")
    assert "1/2 + 1/4" in questions_part
    assert "Common denominator" not in questions_part  # 해설이 문항 쪽에 새지 않음
    assert "1. A — Common denominator 4." in answer_part
    assert "2. B" in answer_part


def test_quiz_markdown_korean_headings():
    md = quiz_to_markdown(_draft("ko"))
    assert "## 정답 및 해설" in md
    assert "**과목**" in md
