# Deploying the public demo (Streamlit Community Cloud)

This is the runbook for the public demo of `chat_app.py`. The demo runs in
**demo mode**: lesson plans, worksheets, and quizzes are generated and can be
revised in chat, but nothing is written to Notion, Google Docs, or Google Forms.
Users download results instead.

## Why demo mode instead of the full integrations

| Integration | How it authenticates today | Problem on a public URL |
|---|---|---|
| Notion | One Internal Integration token (`NOTION_API_KEY`) | Every visitor's lesson plan would be created in the developer's workspace. Also needs Node.js for `npx @notionhq/notion-mcp-server`. |
| Google Docs / Forms | Desktop-app OAuth (`InstalledAppFlow.run_local_server`) + `token.json` | The flow opens a browser *on the server*, which hangs. Shipping `token.json` would write every visitor's files into the developer's Drive. |

Making these multi-user means per-user OAuth (a web redirect flow, per-session
tokens, Google app verification). That is deferred until real users ask for
direct export; the core value (standards-grounded plan + quiz, revisable by
chat) works without it.

## 1. Supabase (usage metrics + daily limit counter)

Create a free project, then run this in the SQL editor:

```sql
create table public.usage_events (
  id            bigint generated always as identity primary key,
  created_at    timestamptz not null default now(),
  session_id    uuid,
  event         text not null,
  locale        text,
  activity      text,
  model         text,
  input_tokens  integer,
  output_tokens integer,
  internal      boolean not null default false
);
create index usage_events_event_created_at on public.usage_events (event, created_at);

-- RLS on with no policies: the public (anon/publishable) key can neither read
-- nor write. The app uses the secret key, server-side only.
alter table public.usage_events enable row level security;
```

Copy the project URL and a **secret** key (Project Settings → API Keys).

## 2. Anthropic Console: hard spend limit

Set a monthly spend limit for the API key's workspace in the Anthropic Console.
The app's own limits (below) are the first line; the Console limit is the one
that holds even if the app has a bug.

## 3. Streamlit Community Cloud

1. New app → repo `werfriend808/class-prep-agent`, branch `main`, main file
   `chat_app.py`.
2. Advanced settings → Python 3.12, and paste secrets based on
   [`.streamlit/secrets.toml.example`](../.streamlit/secrets.toml.example).
3. Deploy. Open the app once with `?internal=1` appended to the URL to test;
   those events are flagged `internal=true` and excluded from the numbers below.

## 4. Limits

| Setting | Demo default | Meaning |
|---|---|---|
| `DAILY_LLM_CALL_LIMIT` | 150 | All visitors combined, per UTC day. Counted from Supabase, survives restarts. |
| `SESSION_LLM_CALL_LIMIT` | 30 | Per browser session, in memory. Stops a runaway tab. |

A lesson plan is 1 call, a worksheet is 1, a quiz is 2 (generate + verify).
Failed JSON parses retry once, which is another call.

## 5. Reading the numbers

Only report what these queries return. "Sessions" are browser sessions, not
people: a refresh starts a new session, and there is no cross-visit identifier.

```sql
-- Overview (excluding my own testing)
select
  count(*) filter (where event = 'session_start')        as sessions,
  count(*) filter (where event = 'plan_generated')       as lesson_plans,
  count(*) filter (where event = 'quiz_generated')       as quizzes,
  count(*) filter (where event = 'worksheet_generated')  as worksheets,
  count(*) filter (where event in ('plan_revised','quiz_revised','worksheet_revised')) as chat_revisions,
  count(*) filter (where event = 'download')             as downloads,
  count(*) filter (where event = 'generation_failed')    as failures,
  count(*) filter (where event = 'feedback_click')       as feedback_clicks,
  count(distinct created_at::date)                       as active_days
from usage_events
where not internal;

-- Sessions that generated at least one artifact (activation)
select count(distinct session_id)
from usage_events
where not internal and event in ('plan_generated', 'quiz_generated');

-- Measured tokens per LLM call (multiply by the model's current price for cost)
select model,
       count(*)                      as calls,
       round(avg(input_tokens))      as avg_input_tokens,
       round(avg(output_tokens))     as avg_output_tokens,
       sum(input_tokens)             as total_input_tokens,
       sum(output_tokens)            as total_output_tokens
from usage_events
where not internal and event = 'llm_call'
group by model;

-- Generation success rate
select activity,
       count(*) filter (where event in ('plan_generated','quiz_generated','worksheet_generated')) as ok,
       count(*) filter (where event = 'generation_failed') as failed
from usage_events
where not internal and activity is not null
group by activity;
```

## A second, Korean instance

Streamlit Community Cloud allows only one app per repo + branch + main file,
so the Korean app uses its own entry point: create another app from the same
repo and branch with **Main file path `chat_app_ko.py`**. That file forces
`LOCALE=ko` (Korean UI + NCIC curriculum, all subjects) before the app loads,
so the secrets can be the same as the English app's; only `FEEDBACK_URL`
should point to a Korean form if you have one. Both instances can share the
Supabase project: events carry a `locale` column, and the daily LLM-call limit
is counted across both, so there is still one cost ceiling.

## Running with the full integrations (local)

Put `NOTION_API_KEY` (and the rest of `.env.example`) in `.env` and leave
`DEMO_MODE` unset. Notion, Google Docs, and Google Forms sync work as before,
and the usage limits default to unlimited.
