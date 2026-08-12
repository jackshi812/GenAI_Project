# App folder brief

This folder is owned by Jack.

It contains the Streamlit presentation layer: microphone capture, transcript,
spoken answer playback, product comparisons, completed steps, and citations.

`contracts.py` at the repository root is the single source of truth for shared
data shapes. Import its models; never redefine them here.

The interface renders the `AssistantResult` returned by
`graph.build.run_graph(transcript)`. It must not perform retrieval, matching,
reconciliation, or other business logic.

Show missing catalog fields and missing live matches honestly. Never invent a
price, rating, ingredient, citation, or running agent state.

Jack owns changes in this folder. Discuss shared contract changes first.
