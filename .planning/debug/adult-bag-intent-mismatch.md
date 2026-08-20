---
status: verifying
trigger: "Look at the most recent transcript. It's still dumb."
created: 2026-08-19
updated: 2026-08-19T20:19:00Z
diagnose_only: false
---

# Adult bag intent and follow-up mismatch

## Symptoms

- expected_behavior: The assistant should understand a request for a bag for an adult, retain or refine that audience across follow-ups, return adult-appropriate bags, and treat conversational corrections such as going back or ending the search as dialogue rather than literal product queries.
- actual_behavior: The latest live trace searches `Give bag`, selects a children's Wildkin duffel, then searches `Give bag adults` but checks the same children's product. A subsequent generic `bag` request returns children's gift bags. Earlier turns also search literal conversational phrases such as `Oh no go back`, `search result`, and `Okay that's all`.
- error_messages: No runtime exception is shown; the failure is semantic routing, context retention, and candidate relevance.
- timeline: Observed in the latest live voice conversation on 2026-08-19 after the recent context-switch and preference fixes.
- reproduction: In one live chat, ask for a bag, clarify that it is for an adult, reject the children's result or ask to go back, and then ask for a normal bag. Also end with a phrase such as `Okay that's all` and confirm no product search starts.

## Current Focus

- hypothesis: CONFIRMED — plural audience parsing, dialogue control routing, and generic recommendation fallback are three deterministic defects that combine into the observed live behavior.
- test: Ten unchanged focused regressions were rerun with `.venv/bin/python` after the minimal production patch.
- expecting: Met — all ten pass without tool calls for dialogue controls or presentation of the Wildkin child result.
- next_action: Parent debugger runs the proportionate adjacent regression suite and completes human-verification handling.
- reasoning_checkpoint:
    hypothesis: "Plural/synonym audience omissions prevent an adult hard facet, the conversation gate omits navigation/termination intents, and fallback templates interpolate semantic_query; together these deterministically cause child-bag selection, literal control-phrase searches, and canned raw-query rationales."
    confirming_evidence:
      - "Local real-catalog execution parses `Give bag adults` with no size and selects the Wildkin Kids result."
      - "Controlled runs route `Oh no go back` and `Okay that's all` to both retrieval tools."
      - "Ten focused regressions fail across all three paths before production changes."
    falsification_test: "The hypothesis is wrong if the unchanged focused tests remain red after only canonical audience parsing, early conversation-control returns, and grounded fallback wording are corrected."
    fix_rationale: "Canonicalizing supported adult terms restores the existing hard-facet machinery; handling control phrases at the existing pre-retrieval gate prevents tool calls; removing raw-query interpolation makes fallback rationale use only grounded candidate facts."
    blind_spots: "No live microphone/network verification is available here; broad dialogue paraphrases beyond the focused phrase set and model-generated non-fallback prose are outside this minimal patch."
- tdd_checkpoint:
    test_files:
      - graph/test_preferences.py
      - graph/test_fast_reply.py
      - graph/test_interactive.py
      - graph/test_answer.py
    status: red
    test_count: 10
    failure_count: 14
    failure_output: "Adult profile remains `Give bag adults` with no size; Wildkin is selected; all three dialogue controls search; both recommendation fallbacks expose the raw query."

## Evidence

- timestamp: 2026-08-19T19:57:25Z
  observation: MCP log records `rag.search(query='Give bag', k=12)` and then checks the live title `Wildkin Kids Overnighter Duffel Bag for Boys and...`.
  implication: The broad bag intent is accepted, but the selected top candidate is explicitly child-oriented.
- timestamp: 2026-08-19T19:57:51Z
  observation: The next MCP request is `rag.search(query='Give bag adults', k=12)`, yet the web lookup again targets the same Wildkin kids' duffel.
  implication: The adult refinement reaches the semantic query, but ranking/relevance does not enforce or meaningfully reward the requested audience.
- timestamp: 2026-08-19T19:58:10Z
  observation: A later `rag.search(query='bag', k=12)` checks `Stephen Joseph recycled bag sets`, and allowed results are children's gift bags rather than an ordinary adult bag.
  implication: Generic bag retrieval is dominated by lexical catalog similarity without sufficient product-type/audience disambiguation.
- timestamp: 2026-08-19T19:48:07Z
  observation: The system sends `Oh no go back` to both catalog and web search.
  implication: Conversational navigation/correction is being treated as a literal product request.
- timestamp: 2026-08-19T19:54:54Z
  observation: The system sends `Okay that's all` to both catalog and web search.
  implication: Conversation termination is not recognized and causes a meaningless retrieval turn.
- timestamp: 2026-08-19T20:01:30Z
  observation: The latest MCP log confirms the exact tool boundary: `Give bag adults` reaches `rag.search` intact, but the immediate live lookup is still the first Wildkin kids result; `Okay that's all` reaches both tools unchanged.
  implication: Adult intent loss occurs after query construction, while termination failure occurs before retrieval routing; these are distinct mechanisms.
- timestamp: 2026-08-19T20:01:30Z
  observation: Exact source search finds query-echoing recommendation templates in `graph/recommendation.py` and `graph/response_style.py`, including `It is the closest grounded candidate for your {query} request.`
  implication: The unnatural Wildkin rationale is deterministic formatter output, not only an LLM wording issue.
- timestamp: 2026-08-19T20:01:30Z
  observation: The worktree already contains unrelated app/cart edits, while the graph files implicated by this bug are currently unmodified.
  implication: Investigation and any eventual fix can stay within graph-owned code/tests without disturbing the user's app/cart work.
- timestamp: 2026-08-19T20:03:00Z
  observation: Deterministic local execution with the real catalog returns the Wildkin Kids Overnighter for `Give bag adults`; the parsed profile is `product_query='Give bag adults'`, `sizes=[]`, and the fast answer says `It matches your bag request.`
  implication: The exact plural-audience miss and child selection reproduce without network, model, or timing variability.
- timestamp: 2026-08-19T20:04:00Z
  observation: Controlled interactive runs send `Give bag adults` to RAG, search the Wildkin title live, and emit `It is the highest-ranked grounded match for your Give bag adults request.`; a hard-adult recommendation state emits the exact reported `It is the closest grounded candidate for your Give bag adults request.`
  implication: Raw-query exposure is deterministic in the canonical fallback formatter, including the exact acceptance-evidence wording.
- timestamp: 2026-08-19T20:05:00Z
  observation: Controlled interactive runs send both `Oh no go back` and `Okay that's all` to RAG then direct web fallback; rule parsing also turns `go back` into an exclusion and `Oh` into the product query.
  implication: Dialogue phrases fail before the planner because the conversation gate lacks navigation/termination intents and preference parsing consumes their grammar as shopping data.
- timestamp: 2026-08-19T20:06:00Z
  observation: Ten focused regression tests produced RED with 14 failures/subtest failures: adult parsing kept `Give bag adults` and no sizes, adult-synonym evidence was not recognized, child Wildkin was presented, each of three conversation controls searched, and both canonical and fast prose echoed query text.
  implication: Each root-cause branch is independently reproduced and the test suite now protects the exact live wording plus adjacent answer paths before any production patch.
- timestamp: 2026-08-19T20:17:00Z
  observation: System `python` collected zero focused cases because importing `catalog.search` failed with `ModuleNotFoundError: chromadb` for every selector.
  implication: This run did not test the patch; verification must use the project's dependency-managed runtime.
- timestamp: 2026-08-19T20:19:00Z
  observation: The exact ten unchanged RED selectors pass under `.venv/bin/python`: 10 tests, zero failures or errors, 0.146 seconds.
  implication: The minimal production patch causally fixes all three reproduced branches: adult audience retention/filtering, dialogue-control routing, and raw-query fallback prose.

## Eliminated

## Resolution

- root_cause: Three deterministic gaps combine. (1) `graph/preferences.py` models `adult` as a hard size/audience facet but does not canonicalize plural `adults` or adult synonyms in evidence, and `is_new_product_request` treats the clarification as a new product; `graph/fast_reply.py` also leaves imperative `give` in the semantic query. Therefore ranking has no adult requirement and accepts Wildkin on `bag` overlap plus high similarity. (2) `graph/fast_reply.py::_conversation_reply` recognizes only greetings, thanks, and cart completion, so navigation/termination phrases are consumed by preference parsing and routed to product tools. (3) `graph/recommendation.py` and `graph/response_style.py` fill missing rationale with templates that interpolate `semantic_query`, exposing `Give bag adults` instead of grounded feature, price/provenance, or supported audience evidence.
- fix: Canonicalized adult audience aliases into the existing hard size facet and evidence matcher; retained the active product when the same family is refined; stripped `give` from semantic queries; added bounded navigation/termination conversation controls; replaced raw-query fallback prose with grounded price/facet wording on the affected paths.
- verification: Focused GREEN — the same 10 tests that established RED now pass unchanged (10/10, zero failures) under the repository virtualenv. Broader adjacent regression verification remains with the parent debugger.
- files_changed:
    - graph/test_preferences.py
    - graph/test_fast_reply.py
    - graph/test_interactive.py
    - graph/test_answer.py
    - graph/preferences.py
    - graph/fast_reply.py
    - graph/recommendation.py
    - graph/response_style.py
