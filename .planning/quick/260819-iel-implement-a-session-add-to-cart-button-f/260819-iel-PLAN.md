---
quick_id: 260819-iel
status: ready
description: Implement a session-persistent add-to-cart action for every one of the six visible grounded product cards, with ordered deduplication, removal, and clear controls.
phase: quick-260819-iel
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: false
files_modified:
  - app/cart.py
  - app/product_grid.py
  - app/main.py
  - app/test_cart.py
  - app/test_product_grid.py
  - app/test_main.py
must_haves:
  truths:
    - "Each of the existing six visible grounded product cards has a native Add to cart action, and an item already in the cart is unmistakably marked Added without creating a duplicate."
    - "The cart survives Streamlit reruns, typed and voice searches, and chat restarts for the lifetime of the browser session; it preserves first-addition order until the shopper removes an item or explicitly clears the cart."
    - "Every cart row retains the selected result's grounded title, displayed price and price provenance, source labels, and safe outbound link without calculating a total or claiming checkout or purchase completion."
    - "Adding, removing, and clearing cart items do not reorder results, move the graph-owned top recommendation, start a search, synthesize speech, or alter the current transcript and answer."
  artifacts:
    - path: "app/cart.py"
      provides: "Pure canonical-identity, ordered-deduplication, removal, and clear operations over grounded ComparisonProduct snapshots"
    - path: "app/product_grid.py"
      provides: "Shared ordered card/display metadata helpers used by both result cards and cart rows"
    - path: "app/main.py"
      provides: "Session cart state, six per-card native actions, and remove/clear cart presentation"
    - path: "app/test_cart.py"
      provides: "Unit regressions for identity, order, deduplication, provenance retention, removal, and clear behavior"
    - path: "app/test_main.py"
      provides: "Streamlit AppTest coverage for cart interactions across searches without graph or voice side effects"
  key_links:
    - from: "app/main.py"
      to: "app/cart.py"
      via: "native Streamlit button callbacks replace cart_products with pure add/remove/clear results"
      pattern: "(add|remove|clear).*cart"
    - from: "app/main.py"
      to: "app/product_grid.py"
      via: "the same first-six ordered product slice supplies card HTML, native actions, and grounded cart display metadata"
      pattern: "MAX_GRID_PRODUCTS|product_card"
    - from: "app/cart.py"
      to: "contracts.py"
      via: "cart entries retain ComparisonProduct snapshots and use catalog doc_id before live URL as canonical identity"
      pattern: "ComparisonProduct|catalog:|live:"
---

# Quick Task 260819-iel Plan

<objective>
Add a truthful, session-local cart to the existing six-card Streamlit result surface while leaving discovery, recommendation, ordering, and voice behavior unchanged.

Purpose: Let a shopper save grounded products across successive searches and manage that shortlist without implying that the demo performs checkout or a real purchase.
Output: App-local cart state helpers, a native action paired with every visible result card, a persistent cart surface with remove/clear controls, focused automated regressions, and a local browser acceptance check.
</objective>

<execution_context>
@/Users/jackshi/.codex/gsd-core/workflows/execute-plan.md
@/Users/jackshi/.codex/gsd-core/templates/summary.md
</execution_context>

<context>
@Instructions.md
@AGENTS.md
@app/AGENTS.md
@.planning/STATE.md
@.planning/phases/01-parallel-build/01-CONTEXT.md
@app/main.py
@app/product_grid.py
@contracts.py
@app/test_main.py
@app/test_product_grid.py
@app/test_livekit_component.py
@run_live_app.py

<interfaces>
- `AssistantResult.products` is the graph-owned ordered `list[ComparisonProduct]`; `app.main._render_evidence` takes `products[:MAX_GRID_PRODUCTS]`, where `MAX_GRID_PRODUCTS` is 6.
- A grounded product's canonical identity is `catalog:{private.doc_id}` when private evidence exists, otherwise `live:{live.url}`. `TopRecommendation.product_key` uses the same rule and remains aligned with `products[0]`.
- The existing card displays the live title/link and live price when present, otherwise the private title/link and `price_low` then raw private price. A matched row visibly retains both Catalog and Web search provenance; ratings remain live-only.
- `st.session_state` owns UI continuity. Chat/search defaults are reset by `restart_chat`, while room/identity are initialized separately; cart state must also be initialized separately so only Remove, Clear cart, or browser-session termination empties it.
- HTML emitted through `unsafe_allow_html` cannot mutate Streamlit state. Per-card cart actions must therefore be native `st.button` widgets paired with the ordered card markup, not decorative HTML controls or query-parameter links.
</interfaces>

<execution_constraints>
- Preserve all unrelated worktree changes and restrict edits to the six files listed in frontmatter.
- Do not stage or commit any file while executing this quick task.
- Do not change `contracts.py`, the graph, retrieval, prompts, voice component, or frontend event protocol; the cart is local Streamlit presentation state per D-09 and D-10.
</execution_constraints>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Define grounded cart identity and ordered state operations</name>
  <files>app/cart.py, app/product_grid.py, app/test_cart.py, app/test_product_grid.py</files>
  <behavior>
    - A catalog-backed or matched product keys as `catalog:{doc_id}`; a live-only product keys as `live:{url}`. Re-adding the same key is a no-op and keeps its original position.
    - Adding distinct products appends them in first-addition order; removing one key leaves the relative order of every remaining entry unchanged; clearing returns an empty cart.
    - Cart state retains the original `ComparisonProduct` snapshot, while shared display metadata selects the same title, shown price, price provenance, source labels, and safe HTTP(S) link as the product card.
    - A missing price stays missing and renders honestly; a numeric or raw source price is carried through unchanged, and unsafe URL schemes are not exposed as links.
  </behavior>
  <action>Write the cart and presentation-helper regressions first. Create `app/cart.py` as an app-local, pure state module operating on ordered `list[ComparisonProduct]` snapshots: expose canonical key lookup, membership, add, remove, and clear operations without mutating the caller's list. Deduplicate strictly by the graph-compatible source identity above, never by fuzzy title or price. In `app/product_grid.py`, extract the card's existing grounded display selection and ordered-card assembly into reusable helpers so the result card and cart row cannot disagree about title, primary price, price label, source labels, link safety, web-step indexing, or the first-card-only top badge. Keep `MAX_GRID_PRODUCTS` at 6 and preserve the current HTML, escaping, missing-field messages, rating rules, outbound listing CTA, and first-six order. Per D-02, retain Catalog (2020) versus Web search provenance; per D-09 and D-10, consume the existing contract without adding a cart model to `contracts.py`. Do not derive quantities, totals, discounts, availability, ratings, or any other claim.</action>
  <verify>
    <automated>.venv/bin/python -m pytest -q app/test_cart.py app/test_product_grid.py</automated>
  </verify>
  <done>Pure tests prove canonical identity, first-addition ordering, duplicate no-ops, targeted removal, clear behavior, exact grounded display-field retention, safe links, six-card capping, stable order, and unchanged canonical-top rendering.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire native per-card actions and the persistent cart surface</name>
  <files>app/main.py, app/test_main.py</files>
  <behavior>
    - Exactly six native Add to cart buttons accompany six visible products, in the same indexed order as the cards; fewer results receive exactly one action each and no fabricated padding.
    - Clicking Add stores that product once, changes its card action to a disabled `Added ✓` state, and leaves card order and the graph-owned top recommendation unchanged.
    - The cart remains visible and in first-addition order through a second typed or voice result and through Restart chat; each row shows grounded title, price with its source label, source badges/text, and a safe listing link.
    - Remove deletes only its targeted item and Clear cart empties the cart. These controls do not call `run_graph`, `synthesize`, or emit/overwrite LiveKit typed, voice, or external-turn events.
  </behavior>
  <action>Write the Streamlit AppTest interaction regressions first. Initialize `cart_products` outside `_SESSION_DEFAULTS`, alongside other browser-session state, so ordinary search resets and `restart_chat` cannot discard it; explicit cart controls remain the only in-session removal path. Replace only the monolithic raw-grid call in `_render_evidence` with ordered rows of three Streamlit columns: render each prepared card HTML unchanged, then place one native button in the same column using a stable widget key derived from action, canonical product key, and visible index. Use `Add to cart` for available products and disabled `Added ✓` for membership already present. Render a compact `Cart (N)` surface before result-specific early stops so it remains accessible while a new search is pending or after chat restart; list each retained product with its grounded display price label, source labels, and safe outbound link, plus one Remove action per row and a Clear cart action when non-empty. Label the surface as a session shortlist and state that it does not perform checkout or purchase. Per D-13 through D-15, keep the two-column page, result/comparison/citation/step-log order, first-card recommendation, microphone component, automatic typed/voice flow, replay audio, and event-deduplication logic intact. Tests must exercise two different searches plus cart clicks and assert graph/TTS call counts only increase for searches, not for cart mutations.</action>
  <verify>
    <automated>.venv/bin/python -m pytest -q app/test_cart.py app/test_product_grid.py app/test_main.py app/test_livekit_component.py</automated>
  </verify>
  <done>AppTest proves that all six current cards have functional, correctly indexed cart actions; cart contents persist and deduplicate across searches and chat restart; remove/clear work; grounded fields stay intact; and search, voice, canonical order, and top recommendation state do not change on cart clicks.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Verify the cart interaction in the local browser</name>
  <files>No files modified; visual verification only</files>
  <action>After both implementation tasks and their focused tests pass, launch the existing local stack in fixture tool mode and complete the desktop and narrow-width browser walkthrough below. Inspect the actual rendered controls and session transitions; do not edit application code during this checkpoint.</action>
  <what-built>A native six-card add-to-cart flow and a session-persistent grounded cart with Added, Remove, and Clear cart states.</what-built>
  <how-to-verify>
    1. Start the local stack in fixture tool mode with `TOOL_MODE=fixture .venv/bin/python run_live_app.py --restart`, then open `http://localhost:8501` in the local browser.
    2. Submit a grounded typed request that returns at least six products. Confirm the first six retain their original rank, only the first has the Top recommendation badge, and every card has a clickable `Add to cart` action next to its existing listing link.
    3. Add the third card and then the first card. Confirm both buttons become disabled `Added ✓`, the cart lists the third product before the first, and each row repeats only the title, source-labeled price, Catalog/Web source labels, and working grounded link shown by that result. Confirm no subtotal, checkout control, purchase confirmation, fabricated rating, or new price appears.
    4. Submit a different typed request and, if configured, one voice request. Confirm the saved cart remains in first-addition order, the new six results keep canonical order/top treatment, and cart clicks do not alter the transcript, spoken answer, replay audio, or trigger another search/spoken response.
    5. Add a new result, remove the earlier first-added item, and confirm the other rows retain their order. Click Clear cart and confirm the cart becomes empty and every currently visible product is addable again.
    6. Capture a local screenshot after the second search with at least two cart items, visually checking three-column alignment at desktop width and one-column usability at a narrow/mobile width. Store the screenshot outside the repository or discard it after review.
  </how-to-verify>
  <verify>
    <automated>.venv/bin/python -m pytest -q app/test_cart.py app/test_product_grid.py app/test_main.py app/test_livekit_component.py</automated>
    <human-check>Complete all six browser steps and inspect the saved-cart screenshot at desktop and narrow/mobile widths.</human-check>
  </verify>
  <done>The user approves the six-card actions, cross-search session behavior, grounded cart rows, remove/clear interactions, responsive alignment, and lack of search or voice side effects.</done>
  <resume-signal>Type "approved" or describe any cart alignment, state, provenance, link, ordering, search, or voice issue.</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Graph result → session cart | Catalog and live evidence crosses from validated `ComparisonProduct` objects into longer-lived browser-session state. |
| Live/catalog strings → cart UI | Titles, raw prices, and outbound URLs are displayed again outside the existing card renderer. |
| Native widget event → search/voice session state | Cart clicks share a Streamlit rerun with transcript, graph, TTS, and LiveKit state but must mutate only the cart. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-IEL-01 | Tampering | `app/cart.py` identity/deduplication | medium | mitigate | Use the same catalog-doc/live-URL identity as `TopRecommendation`, prefer private identity for matched products, and prove duplicate adds cannot replace or reorder the retained snapshot. |
| T-IEL-02 | Information Disclosure | `app/product_grid.py` and cart links | high | mitigate | Reuse HTML escaping and HTTP(S)-only URL validation for every cart field and link; never interpolate an untrusted URL into raw markup unchecked. |
| T-IEL-03 | Spoofing | `app/main.py` cart language | medium | mitigate | Call the cart a session-local shortlist, expose no checkout path, and never emit copy claiming an order, charge, or completed purchase. |
| T-IEL-04 | Tampering | cart callbacks versus graph/voice state | high | mitigate | Give cart widgets dedicated stable keys and callbacks that replace only `cart_products`; AppTest asserts unchanged transcript/result/external-turn data and unchanged graph/TTS call counts after each cart mutation. |
</threat_model>

<source_audit>

| Source | Item | Task | Status |
|--------|------|------|--------|
| QUICK GOAL | Real Add to cart action for every one of the six visible product cards | 2 | COVERED |
| QUICK GOAL | Session-persistent, first-addition ordered, deduplicated cart across searches | 1, 2 | COVERED |
| QUICK GOAL | Grounded title, price provenance, source, and link retained without totals, checkout, invented values, or purchase claims | 1, 2 | COVERED |
| QUICK GOAL | Added state, targeted remove, and explicit clear behavior | 1, 2 | COVERED |
| QUICK GOAL | Preserve result order, canonical top recommendation, search flow, and voice behavior | 1, 2, 3 | COVERED |
| QUICK GOAL | Focused automated coverage and local visual/browser verification | 1, 2, 3 | COVERED |
| CONTEXT | D-02/D-09/D-10 preserve per-field provenance and the existing graph-to-app contract boundary | 1, 2 | COVERED |
| CONTEXT | D-13/D-14/D-15 preserve the two-column evidence surface, honest product details, and hands-free voice flow | 2, 3 | COVERED |
| REQ | No roadmap requirement ID is assigned to this additive quick task | — | N/A |
| RESEARCH | No research artifact is required; this is Level 0 work using established Streamlit, contract, and test patterns with no dependency changes | — | N/A |

</source_audit>

<verification>
Run `.venv/bin/python -m pytest -q app/test_cart.py app/test_product_grid.py app/test_main.py app/test_livekit_component.py`, then run `git diff --check -- app/cart.py app/product_grid.py app/main.py app/test_cart.py app/test_product_grid.py app/test_main.py`. Complete the blocking local-browser flow above and confirm the final diff contains no changes to contracts, graph, voice, frontend events, dependencies, secrets, or unrelated dirty-worktree files.
</verification>

<success_criteria>
- Every visible result, up to the unchanged cap of six, has one functional native cart action paired with its card.
- The browser-session cart preserves first-addition order and grounded snapshots across typed searches, voice results, reruns, and chat restart; duplicate adds are impossible and Remove/Clear cart are deterministic.
- Cart rows carry only grounded title, shown source price, source labels, and safe source link, with honest missing states and no calculated total, checkout, fabricated rating/price, or completed-purchase claim.
- Cart mutations leave `AssistantResult.products`, canonical product zero, `TopRecommendation`, transcript, graph call count, TTS call count, audio, and LiveKit event state unchanged.
- Focused tests pass and the desktop/mobile browser check confirms readable card/action alignment and complete cart interaction behavior.
</success_criteria>

<output>
Create `.planning/quick/260819-iel-implement-a-session-add-to-cart-button-f/260819-iel-SUMMARY.md` when done. Do not stage or commit the implementation or summary.
</output>
