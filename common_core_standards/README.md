# Common Core Math 성취기준 데이터셋

Phase 2("영어/미국 Common Core Math 지원")에서 `CommonCoreMathProvider`가 쓰는
성취기준 데이터셋. `ncic_standards/`와 같은 역할(원본 → 우리 스키마로 정리)을
하지만, 대상은 미국 Common Core State Standards for Mathematics(CCSSM,
2010년 제정 이후 개정 없음)다.

## 원본 및 접근 경위

공식 corestandards.org는 XML 패키지(`ccssi.zip`, CEDS 스키마)만 제공하는데,
이 프로젝트가 도는 네트워크 환경의 egress 정책상 `thecorestandards.org`
도메인에 직접 접근할 수 없었다(반면 `github.com`/`raw.githubusercontent.com`은
접근 가능). 그래서 공식 CCSSI GUID·dotNotation과 Achievement Standards
Network(ASN) 식별자를 그대로 보존해서 재구성해 둔 커뮤니티 데이터셋
([SirFizX/standards-data](https://github.com/SirFizX/standards-data),
`clean-data/CC/math/CC-math-0.8.0.json`)을 원본으로 썼다. 2012년 이후
갱신이 없는 저장소지만, Common Core Math 표준 자체가 2010년 제정 이후
개정된 적이 없어서 최신성 문제는 없다 — 성취기준 문구/코드는 여전히
NGA/CCSSO가 발행한 공식 내용 그대로다.

`scripts/build_common_core_math_standards.py`가 위 원본을 받아서(네트워크로
자동 다운로드, 또는 `--input`으로 로컬 사본 지정) 아래 스키마로 다시 정리해
`math_standards.json`을 만든다 — ncic_standards가 원본 PDF를 직접 파싱해서
자체 스키마로 정리한 것과 같은 접근이다.

## 라이선스 및 저작권 고지

성취기준 문구 자체의 재배포는 공식
[CCSS Public License](https://www.thecorestandards.org/public-license/)가
"저작권 고지를 포함한다"는 조건으로 명시적으로 허용한다. 그래서 모든
레코드의 `source_doc` 필드에 그 고지 문구를 그대로 박아 넣었다 — 이 데이터를
어떻게 재가공해서 쓰든(수업계획안 인용 등) `format_citation()`을 거치면
저작권 고지가 자동으로 따라간다. 필요한 고지 문구:

> © Copyright 2010. National Governors Association Center for Best Practices
> and Council of Chief State School Officers. All rights reserved.

## 스키마 (`math_standards.json`)

```json
{
  "code": "6.G.1",
  "subject": "Math",
  "domain_code": "G",
  "domain": "Geometry",
  "grade": "Grade 6",
  "text": "Find the area of right triangles, other triangles, special quadrilaterals, and polygons by composing into rectangles or decomposing into triangles and other shapes; apply these techniques in the context of solving real-world and mathematical problems.",
  "clarifications": [],
  "source_doc": "Common Core State Standards for Mathematics — © Copyright 2010. National Governors Association Center for Best Practices and Council of Chief State School Officers. All rights reserved."
}
```

- `code`: 공식 shortCode (예: "6.G.1", "N-RN.1", "K.CC.3", "MP.1"). 교사들이
  실제로 부르는 표기 그대로.
- `subject`: 항상 "Math" (이 데이터셋은 Math 전용).
- `domain_code`/`domain`: 성취기준 코드에서 뽑은 도메인 코드와, 원본 파일에
  있는 "Domain" 폴더 33개의 실제 이름으로 매핑한 사람이 읽을 도메인명(예:
  "Geometry", "The Real Number System"). 8개 "Standards for Mathematical
  Practice"는 도메인 코드 "MP"로 묶었다(원본엔 이 폴더에 이름표가 따로 없어서
  수작업으로 붙임).
- `grade`: 학년 라벨 11종 중 하나 — "Kindergarten" / "Grade 1" ~ "Grade 8" /
  "High School"(고등학교는 학년별이 아니라 개념 범주·도메인 단위로 묶임 —
  한국 NCIC의 "고등학교 공통/선택"과 비슷한 성격의 밴드) / "K-12"(8개 수학적
  실천 기준 전용 — 모든 학년에 공통 적용). `src/common_core_math_matcher.
  grade_groups_for()`가 사용자가 말하는 구체적인 학년("3", "K", "10" 등)을
  이 라벨로 변환해 필터링한다 — 한국 NCIC의 학년군(밴드형)과 달리 미국
  Common Core Math는 대부분 학년 1개당 라벨 1개(학년별형)이고, 고등학교와
  "K-12" 두 경우만 여러 학년이 라벨을 공유한다.
- `text`: 성취기준 문장 원문 (HTML 엔티티 제거).
- `clarifications`: 원문에 딸린 보충 설명/예시 (있는 경우만, 없으면 빈 리스트).
  매칭 스코어링(키워드 검색)에는 안 쓴다 — NCIC와 동일하게 `text`만 본다.
- `source_doc`: 위 저작권 고지 문구 (모든 레코드 동일, 고정값).

## 수집 결과 — 총 517건

학년별: High School 192, Grade 6 47, Grade 7 43, Grade 5 40, Grade 3 37,
Grade 4 37, Grade 8 36, Grade 2 28, Kindergarten 25, Grade 1 24, K-12(MP) 8.

도메인별 상위 항목: Measurement and Data(MD) 50, Geometry(G) 43, Number and
Operations in Base Ten(NBT) 39, Number and Operations—Fractions(NF) 37,
Operations and Algebraic Thinking(OA) 34, Expressions and Equations(EE) 31,
The Number System(NS) 28, Statistics and Probability(SP) 26 — 나머지 고등학교
세부 도메인(N-VM/F-IF/A-REI/G-CO 등 25개)은 각 3~17건.

## 재현 방법

```bash
python3 scripts/build_common_core_math_standards.py
# 원본을 이미 받아둔 로컬 사본으로 재현하려면:
python3 scripts/build_common_core_math_standards.py --input path/to/CC-math-0.8.0.json
```

## 알려진 한계

1. **원본 데이터셋의 클러스터/도메인 계층 링크(`ccsiParent`)가 레코드마다
   있고 없고가 들쭉날쭉하다**(2012년 데이터라 관계형 메타데이터가 불완전).
   그래서 도메인명은 그 링크를 안 쓰고 shortCode 구조 자체(예: "6.G.1"의
   가운데 토큰)에서 뽑아서, 원본에 있는 "Domain" 폴더 33개의 이름표로
   매핑했다 — 코드 형식이 안정적이라 이 방식이 계층 링크보다 신뢰도가 높다.
2. **고등학교(High School)는 학년(9~12) 단위가 아니라 도메인/개념 범주
   단위로 조직된다** — 이건 한계가 아니라 Common Core 자체의 설계다
   (예: "고등학교 대수" 표준은 특정 학년에 매이지 않는다). 사용자가 "9학년"
   "10학년" 등을 말해도 전부 "High School" 라벨로 묶어서 찾는다.
3. **8개 "Standards for Mathematical Practice"(MP.1~MP.8)는 특정 학년/도메인
   내용이 아니라 전 학년 공통 사고 습관 기준이다.** `grade == "K-12"`로 묶어서
   어떤 학년을 조회하든 항상 후보에 포함되도록 했다 — 실제 수업계획안에서
   자주 함께 인용되는 항목이라 제외하지 않았다.
4. **ELA(읽기·쓰기) 등 Math 외 과목은 아직 없다.** 현재 계획(Phase 2)이
   "우선 Math부터"라 다른 과목은 필요해지면 같은 스크립트 패턴으로 추가하면
   된다 — `CurriculumProvider` 인터페이스 자체는 과목에 종속되지 않는다.
