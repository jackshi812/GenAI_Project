# Jack's optional coordination guide

This is a reminder sheet, not a set of approval gates. Jack coordinates the
combined project; Austin and Ginger do not need permission for implementation
choices inside their own folders.

## Getting everyone unblocked

- Make the cleaned dataset and shared configuration available in the repo.
- Share `contracts.py` and fixture examples early enough for independent work.
- Confirm teammates know their folders and the public interfaces they consume.
- Keep credentials in a private channel and local environment only.

## While building

- Use fixtures to develop the full voice and UI path without waiting.
- Keep matching and reconciliation out of the UI.
- Keep the microphone → transcript → answer → spoken playback flow simple.
- Check the layout on a projector-sized viewport and prioritize the comparison.
- Share contract changes before another contributor builds against the old
  shape.

## When comparing outputs

- Look together at one real serialized output from each layer.
- Pay attention to numeric versus string prices, document IDs, nullable fields,
  and brand punctuation.
- Try the real conflict product title against the matcher rather than relying
  only on a curated fixture title.
- Adjust the selected demo product if the evidence is genuinely weak; never
  edit evidence to create a cleaner story.

## During integration

- Let Ginger own the graph-side MCP adapter and Austin own server corrections.
- Replace Jack's single fixture-result seam with `run_graph(transcript)`.
- Exercise live and recorded modes and label whichever mode is actually used.
- If something fails, identify which interface disagrees and return the change
  to that component's owner.

## Preparing the final experience

- Make the spoken answer concise and traceable to visible evidence.
- Keep the private-versus-live reconciliation easy to find.
- Explain missing private ratings and other data limitations plainly.
- Document setup and configuration from a new user's point of view.
- Rehearse together, simplify fragile steps, and keep a truthful backup
  recording available.
