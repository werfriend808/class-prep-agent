"""Common Core Math 성취기준 데이터셋(common_core_standards/math_standards.json) 빌드 스크립트.

2026-09-17 (Phase 2): ncic_standards/achievement_standards.json과 같은 역할을
하는 미국판 데이터셋을 만든다. 공식 corestandards.org는 XML 패키지
(ccssi.zip)만 제공하는데 이 환경의 네트워크 정책상 그 도메인에 직접 접근할 수
없었다 — 대신 Achievement Standards Network(ASN) 식별자와 공식 CCSSI
GUID/dotNotation을 그대로 보존해서 재구성한 커뮤니티 데이터셋
(SirFizX/standards-data, 2012년 이후 갱신 없음이지만 Common Core Math
표준 자체가 2010년 이후 개정되지 않아 최신성 문제 없음)을 원본으로 삼아
우리 스키마로 다시 정리했다. 실제 성취기준 문구/코드는 NGA/CCSSO가 발행한
공식 내용 그대로이고, 재배포는 공식 Public License
(https://www.thecorestandards.org/public-license/)가 저작권 고지를 붙이는
조건으로 명시적으로 허용한다 — 그래서 모든 레코드의 `source_doc`에 그 고지
문구를 그대로 박아 넣었다(포맷팅한 인용문마다 자동으로 따라가게).

원본 파일의 `ccsiParent`(클러스터/도메인 계층 링크)는 레코드마다 있고 없고가
들쭉날쭉해서(2012년 데이터라 관계형 메타데이터가 불완전) 믿을 수 없었다 —
대신 shortCode 자체의 구조(예: "6.G.1" → 학년 6, 도메인 "G", 번호 1 /
"N-RN.1" → 고등학교 도메인 "N-RN", 번호 1)에서 도메인 코드를 뽑고, 원본
파일에 이미 있는 "Domain" 폴더 33개(statementLabel == "Domain")의 실제
이름으로 매핑했다 — 이 폴더 레코드들은 계층이 아니라 이름표라 들쭉날쭉한
문제가 없다.

사용법:
    python3 scripts/build_common_core_math_standards.py
    (네트워크로 raw.githubusercontent.com에서 원본을 받는다. --input으로
    이미 받아둔 로컬 사본을 지정할 수도 있다.)
"""
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/SirFizX/standards-data/master/"
    "clean-data/CC/math/CC-math-0.8.0.json"
)

# 공식 CCSS Public License(https://www.thecorestandards.org/public-license/)가
# 요구하는 저작권 고지. 재배포하는 모든 성취기준 인용에 그대로 붙어야 한다 —
# format_citation()이 이 문자열이 담긴 source_doc을 그대로 노출하므로 별도
# 처리가 필요 없다.
CCSS_ATTRIBUTION = (
    "Common Core State Standards for Mathematics — "
    "© Copyright 2010. National Governors Association Center for Best "
    "Practices and Council of Chief State School Officers. All rights reserved."
)

_HS_CODE_RE = re.compile(r"^([A-Z]+-[A-Z]+)\.")  # 예: "N-RN.1" -> "N-RN"
_GRADE_CODE_RE = re.compile(r"^([A-Za-z0-9]+)\.([A-Za-z]+)\.")  # 예: "6.G.1" -> ("6","G")


def _clean_text(value: str | None) -> str:
    """HTML 엔티티(예: &lt;sup&gt;★&lt;/sup&gt;)를 걷어내고 사람이 읽을 문자열로."""
    if not value:
        return ""
    unescaped = html.unescape(value)
    return re.sub(r"<[^>]+>", "", unescaped).strip()


def _domain_code_for(short_code: str) -> str | None:
    """shortCode(예: "6.G.1", "N-RN.1", "MP.1")에서 도메인 코드를 뽑는다."""
    if short_code.startswith("MP"):
        return "MP"
    m = _HS_CODE_RE.match(short_code)
    if m:
        return m.group(1)
    m = _GRADE_CODE_RE.match(short_code)
    if m:
        return m.group(2)
    return None


def _load_raw(input_path: str | None) -> list[dict]:
    if input_path:
        with open(input_path, encoding="utf-8") as f:
            return json.load(f)
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as resp:  # noqa: S310 — 고정된 https 원본
        return json.loads(resp.read().decode("utf-8"))


def build(input_path: str | None = None) -> list[dict]:
    raw = _load_raw(input_path)

    # "Domain" 폴더 33개(예: shortCode "G" -> statement "Geometry")에서 이름표를 뽑는다.
    # 최상위 "Standards for Mathematical Practice" 폴더는 statementLabel이 없어서
    # 따로 추가한다(shortCode "MP").
    domain_names: dict[str, str] = {
        f["shortCode"]: _clean_text(f["statement"])
        for f in raw
        if f.get("cls") == "folder" and f.get("statementLabel") == "Domain" and f.get("shortCode")
    }
    domain_names.setdefault("MP", "Standards for Mathematical Practice")

    leaves = [r for r in raw if r.get("cls") != "folder" and r.get("code") and r.get("shortCode")]

    records: list[dict] = []
    unmapped_domains: set[str] = set()
    for r in leaves:
        short_code = r["shortCode"]
        domain_code = _domain_code_for(short_code)
        domain_name = domain_names.get(domain_code or "")
        if domain_code and domain_name is None:
            unmapped_domains.add(domain_code)

        records.append(
            {
                "code": short_code,
                "subject": "Math",
                "domain_code": domain_code,
                "domain": domain_name,
                "grade": r.get("gradeLevel"),
                "text": _clean_text(r.get("statement")),
                "clarifications": [_clean_text(c) for c in r.get("clarifications") or []],
                "source_doc": CCSS_ATTRIBUTION,
            }
        )

    if unmapped_domains:
        raise RuntimeError(f"도메인 이름을 못 찾은 코드: {sorted(unmapped_domains)}")

    # 재현 가능한 diff를 위해 코드 순으로 정렬.
    records.sort(key=lambda rec: rec["code"])
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        help="원본 JSON 로컬 사본 경로 (생략하면 raw.githubusercontent.com에서 받는다).",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "common_core_standards" / "math_standards.json"),
    )
    args = parser.parse_args()

    records = build(args.input)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"{len(records)}건 저장: {out_path}")


if __name__ == "__main__":
    main()
