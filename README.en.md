# class-prep-agent

[한국어로 보기](README.md) (the full, detailed development log)

An AI teaching-assistant agent for teachers, built as two Streamlit apps sharing one codebase. Originally built for a Korean bootcamp project around Korea's national curriculum (NCIC), it now also supports an English/US mode built on the Common Core Math standards.

> This is the short English overview. The full, very detailed development log — every design decision, bug encountered, and the original Korean bootcamp assignment context — lives in [`README.md`](README.md) (Korean). Code comments cross-reference specific numbered sections of that file (e.g. "README 13-7"), so treat `README.md` as the canonical history and this file as a quick-start summary.

## What it does

**`app.py`** — Natural-language search and summarization over a Notion team workspace of class materials, via the official [Notion MCP server](https://github.com/makenotion/notion-mcp-server).

**`chat_app.py`** — A multi-turn chatbot with two activities you can pick from:
- **Discussion lesson plan**: collects subject/grade/topic over chat, generates an 8-section discussion-based lesson plan grounded in curriculum standards, saves it to Notion automatically, lets you keep revising it by chatting, and can generate a matching student worksheet saved to Google Docs.
- **Quiz**: collects subject/grade/topic, generates a 5-question multiple-choice quiz, and publishes it to Google Forms with auto-grading — also revisable by chatting.

Both activities support **two curriculum/language modes**, controlled by a single `LOCALE` environment variable:

| `LOCALE` | Language | Curriculum standard | Notes |
|---|---|---|---|
| `ko` (default) | Korean | Korea's 2022 revised national curriculum (NCIC), 4,199 achievement standards across all grades/subjects | Original implementation |
| `us` | English | Common Core State Standards for Mathematics (Math only, 517 standards) | Added later; same lesson-plan/worksheet/quiz pipeline, English prompts and UI |

The `LOCALE=us` mode is newer than most of `README.md` and isn't documented there yet — this file is currently the only place it's written up. See `src/curriculum/` for the pluggable `CurriculumProvider` interface behind both modes, and `common_core_standards/README.md` for where the Common Core dataset came from and its licensing.

## Setup

**Prerequisites**
- Python 3.10+
- Node.js / npx (for the Notion MCP server)
- A Notion Internal Integration token, connected to the pages/databases you want the app to read and write
- An LLM key: `ANTHROPIC_API_KEY` (Claude, default) or `LLM_PROVIDER=clova` + `HCX_API_KEY` (Naver Clova Studio)
- For the worksheet and Quiz features: a Google Cloud project with the Docs, Drive, and Forms APIs enabled, and an OAuth desktop-app `credentials.json` in the repo root (see `README.md` §12/§17 for the step-by-step Google Cloud Console walkthrough)

**Install**

```bash
pip install -r requirements.txt
```

**Configure `.env`** (see `.env.example` for the full annotated list):

```
NOTION_API_KEY=ntn_...
ANTHROPIC_API_KEY=sk-ant-...
NOTION_DATA_SOURCE_ID=...
NOTION_LESSON_PLAN_PARENT_ID=...

# Optional: switch language + curriculum together
LOCALE=us
```

**Run**

```bash
python -m streamlit run chat_app.py   # the combined lesson-plan/worksheet/Quiz app
streamlit run app.py                   # the Notion search/summarize app
```

**Test**

```bash
python -m pytest
```

The suite (230+ tests) runs entirely on mocked LLM calls and fake data — no API keys, network access, or credits required.

## Project structure (high level)

```
app.py                        # Notion search/summarize entry point
chat_app.py                   # Lesson-plan / worksheet / Quiz entry point
src/
  curriculum/                 # CurriculumProvider interface + NCIC and Common Core Math implementations
  conversation.py             # Multi-turn slot-collection state machines
  lesson_plan.py               # Lesson plan generation (ko + us prompts)
  worksheet.py                 # Student worksheet generation (ko + us prompts)
  quiz.py                       # Quiz question generation + validation (ko + us prompts)
  notion_writer.py / google_docs_writer.py / forms_writer.py   # External-doc integrations
ncic_standards/                # Korean NCIC achievement-standards dataset
common_core_standards/         # Common Core Math standards dataset
tests/                         # Full unit test suite
```

## Known limitations

- The `LOCALE=us` mode only covers Math; other Common Core subjects aren't implemented.
- Actually generating a lesson plan, worksheet, or quiz (as opposed to the chat/slot-collection flow around it) needs a working LLM key with available credit/quota.
- See `README.md` for the much longer list of specific bugs found and fixed along the way, and the original project requirements this was built against.
