---
phase: quick-260819-iel
plan: 01
subsystem: streamlit-ui
tags: [streamlit, session-state, cart, grounded-products, app-test]

requires:
  - phase: 02-integration
    provides: grounded AssistantResult products, canonical recommendations, and the two-column voice/search UI
provides:
  - Pure ordered cart operations keyed by catalog document or live URL identity
  - Shared grounded card/cart display metadata with HTTP(S)-only links
  - Six indexed native card actions and a session-persistent shortlist with remove and clear controls
affects: [app, product-grid, session-state, browser-uat]

tech-stack:
  added: []
  patterns:
    - Immutable-style list replacement for Streamlit session cart mutations
    - Shared prepared-product metadata for result cards, comparison rows, and cart rows

key-files:
  created:
    - app/cart.py
    - app/test_cart.py
  modified:
    - app/product_grid.py
    - app/main.py
    - app/test_product_grid.py
    - app/test_main.py

key-decisions:
  - "Cart identity exactly mirrors the graph: catalog doc_id wins for matched products, with live URL used only for live-only products."
  - "The cart stores the first ComparisonProduct snapshot and replaces its list on each mutation, preserving first-addition order without quantities or totals."
  - "cart_products is initialized outside restartable chat defaults so only Remove, Clear cart, or browser-session termination can empty it."
  - "Restart chat preserves the handled component event ID so a sticky restart payload cannot trigger an infinite rerun."

patterns-established:
  - "ProductDisplay is the single presentation selection for title, displayed price, price provenance, source labels, and safe listing URL."
  - "PreparedProductCard preserves the graph-owned first-six order, positional web step, and first-card-only canonical recommendation treatment."

requirements-completed: []

coverage:
  - id: D1
    description: Ordered cart identity, deduplication, snapshot retention, removal, and clear behavior are pure and deterministic.
    verification:
      - kind: unit
        ref: app/test_cart.py#CartStateTests
        status: pass
    human_judgment: false
  - id: D2
    description: Grounded display metadata, safe links, six-card capping, order, web-step indexing, and canonical-top treatment remain aligned.
    verification:
      - kind: unit
        ref: app/test_product_grid.py#ProductGridTests
        status: pass
    human_judgment: false
  - id: D3
    description: Native add/added/remove/clear interactions persist across typed search, voice result, and chat restart without graph or TTS side effects.
    verification:
      - kind: automated_ui
        ref: app/test_main.py#GraphResultSeamTests cart interaction regressions
        status: pass
    human_judgment: false
  - id: D4
    description: Desktop three-column alignment and narrow-width one-column usability require inspection in the local browser.
    verification:
      - kind: manual_procedural
        ref: 260819-iel-PLAN.md#Task 3
        status: unknown
    human_judgment: true
    rationale: Responsive visual alignment and rendered browser usability cannot be established by Streamlit AppTest.

duration: 16min
completed: 2026-08-19
status: complete
---

# Quick Task 260819-iel: Session-Persistent Grounded Cart Summary

**A truthful browser-session shortlist with six native product actions, ordered deduplication, grounded price/source/link retention, and side-effect-free remove and clear controls**

## Performance

- **Duration:** 16 min
- **Started:** 2026-08-19T18:18:00Z
- **Completed:** 2026-08-19T18:33:53Z
- **Automated tasks:** 2 of 2 complete
- **Files created/modified:** 6 implementation and test files, plus this summary
- **Focused tests:** 34 passed through the repository's unittest-compatible runner
- **Full repository tests:** 152 passed

## Accomplishments

- Added pure cart helpers that retain grounded `ComparisonProduct` snapshots in first-addition order, deduplicate by graph-compatible identity, and never mutate caller-owned lists.
- Extracted shared product display and prepared-card metadata so cards, comparison rows, native actions, and cart rows agree on grounded title, displayed price and provenance, source labels, safe listing link, positional web step, and canonical-top treatment.
- Added one native Add/Added action for each of the first six visible results plus a persistent `Cart (N)` shortlist with grounded rows, targeted Remove controls, and Clear cart.
- Kept price provenance truthful across cards and the cart: live Serper prices are current, fixture prices are recorded, and unknown-origin prices are labeled only as web prices.
- Proved cart state survives a second typed search, a voice result, and Restart chat while cart mutations leave transcript, result, external-turn, audio, graph calls, and TTS calls unchanged.
- Preserved restart-event deduplication across chat-state reset so a repeatedly returned component event cannot create an infinite rerun.

## Task Commits

No commits were created. The delegating agent explicitly retained staging and commit ownership for the shared dirty worktree.

## Files Created/Modified

- `app/cart.py` - Canonical identity plus pure membership, add, remove, and clear operations.
- `app/product_grid.py` - Shared grounded `ProductDisplay` and ordered `PreparedProductCard` helpers reused by all product surfaces.
- `app/main.py` - Separately initialized session cart, native per-card actions, and persistent remove/clear shortlist UI.
- `app/test_cart.py` - Identity, ordering, deduplication, snapshot, removal, clear, and non-mutation regressions.
- `app/test_product_grid.py` - Display-field, raw/missing price, safe-link, capping, step-index, and canonical-top regressions.
- `app/test_main.py` - Streamlit AppTest coverage for six actions, Added state, persistence, grounded cart rows, voice/restart continuity, and search/TTS isolation.

## Decisions Made

- Used catalog `doc_id` before live URL for matched-product identity, exactly matching `TopRecommendation.product_key` and preventing title- or price-based fuzzy deduplication.
- Retained the originally added Pydantic snapshot when a later result carries the same identity, so duplicate searches cannot replace or reorder saved evidence.
- Kept `cart_products` outside `_SESSION_DEFAULTS`; chat restart still resets conversation, room, and identity state but leaves the browser-session shortlist intact.
- Preserved the handled restart event ID after resetting chat defaults, allowing the next rerun to ignore a sticky component value while still accepting future event IDs.
- Rendered each existing card HTML fragment unchanged inside an ordered three-column Streamlit row and aligned its native action with a stretch/distribute container rather than a fixed-height scroll box.
- Reused HTTP(S)-only validation, inert native text, and native link controls for cart output; no quantity, subtotal, checkout, availability inference, fabricated rating, or purchase claim was added.
- Disabled the action for the contract-valid but evidence-less fallback shape instead of allowing a callback error.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Prevented a sticky Restart chat event from rerunning forever**

- **Found during:** Final read-only diff review of Task 2
- **Issue:** The existing restart loop reset `last_component_event_id` to `None` immediately before `st.rerun()`. If the component returned its current `restart_chat` value again, the app treated it as new indefinitely, blocking the required cart-through-restart flow.
- **Fix:** Restore the handled restart event ID after resetting chat defaults, while leaving `cart_products` outside that reset. The AppTest mock now deliberately returns the same restart event on subsequent reruns.
- **Files modified:** `app/main.py`, `app/test_main.py`
- **Verification:** Sticky restart regression passes and the cart remains ordered and visible afterward.
- **Committed in:** Not committed per delegating-agent instruction.

---

**Total deviations:** 1 auto-fixed bug
**Impact on plan:** The correction is required for deterministic Restart chat behavior and does not alter graph, voice, or product contracts. The planned browser checkpoint remains intentionally pending for the owning agent/user.

## Issues Encountered

- The repository virtual environment does not contain `pytest`, so the literal plan command exits with `No module named pytest`. No dependency was installed. The same four unittest-compatible modules were run with `.venv/bin/python -m unittest`; all 34 tests passed. Full unittest discovery passed 152 tests.
- Streamlit emitted expected bare-mode `ScriptRunContext` warnings, and the existing LiveKit JWT tests emitted short-development-key warnings; neither affected results.

## Known Stubs

None. The empty-cart message, missing-price marker, no-image placeholder, and unavailable-link caption are intentional honest states rather than unwired data.

## User Setup Required

None - no dependencies, credentials, network endpoints, or external services were added.

## Remaining Browser Verification

Task 3 remains a blocking human visual check: run the fixture stack, exercise third-then-first addition across another typed/voice result, remove and clear, and inspect desktop three-column plus narrow/mobile one-column alignment. Automated behavior is complete; no screenshot was written to the repository.

## Threat Review

All introduced surfaces were anticipated by the plan threat model: canonical identity prevents cart replacement/reordering, every repeated product field is escaped, outbound cart links require HTTP(S), shortlist language explicitly disclaims checkout/purchase, and AppTest proves cart widgets do not invoke graph or TTS work.

## Self-Check: PASSED

All six planned implementation/test files and this summary exist. The focused 34-test fallback suite and full 152-test discovery passed, Python compilation passed, scoped `git diff --check` passed, and the worktree shows no changes outside the six owned app files and this quick-task directory.

---
*Quick task: 260819-iel*
*Completed: 2026-08-19*
