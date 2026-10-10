# Interface and experience specification

## Direction
A focused building tool. On 3 October 2026 the user selected the second displayed design concept,
Open Studio. Its visual reference is preserved at `var/evidence/open-studio/selected-reference.png`: a
compact white header, navy typography, pale model stage, blue actions, one left instruction rail and a
unified bottom navigation dock. This supersedes the earlier three-column workspace and dark header.
The older `assets/v1-concept.png` remains historical visual context only.
The current set-number requirement overrides the mockup's upload screen. Its aircraft render, parts, counts,
completion badges, navigation and exports are illustrative and must not be treated as product data.
Do not embed the mockup as the application UI or as assembly evidence.

## Screen A — set lookup
The user selected the first Brick Playground landing concept on 3 October 2026, retained at
`var/evidence/landing-playground/selected-reference.png`. It complements the unchanged Open Studio tutorial.
White `Guide2Build 3D` header and `How it works` anchor; sunshine-yellow hero with the heading
`Small bricks. A clearer picture.`, colourful illustrative brick artwork, labelled set-number field,
`Find my set` action and supported-source note. `Try the plane tutorial` resolves the actual supported
catalogue entry and alt-02 booklet through the same APIs; it must retain unavailable-source/preparation states.
Three illustrated steps explain finding the set, choosing the booklet and following the 3D instructions.
Artwork is visibly identified as illustrative and is never reconstruction or official-source evidence.
On success, show set name and the supported booklet choice with its official-source link.
Move focus to the result or actionable error. Return from the tutorial to the found set, while entering
the tutorial resets document scroll. Keep all preparation/retry/provider and review distinctions.
No upload control, community navigation, profile, shopping, pricing, generation prompt or search-engine facade.

Input states: empty, malformed, loading, unsupported, source unavailable and supported.
Do not use “success” styling when only the booklet has been found. A known source is not a reconstructed model.

## Screen B — preparation
After booklet selection, open a cached valid tutorial or display the real conversion state. Include stage name,
completed steps/pages where measurable, retry/cancel, and any review or provider-access requirement.
The user should understand the difference between waiting for a job and needing to resolve a specific ambiguity.
A provider outage does not require re-entering the set number. A source access block does not trigger a PDF-upload requirement.

## Screen C — tutorial workspace
Desktop layout: current instruction, source and parts share one readable left rail; the interactive model
occupies the large remaining stage. A compact application header and a single bottom navigation dock
frame the workspace. Keep the workspace within the viewport and let the rail scroll independently.

Left rail: the current main step and substep, source-grounded instruction sentence, exact rendered source crop, page label and open-page control.
Centre: real part geometry, useful default camera, orbit/pan/zoom/reset, active-piece outline and non-colour cue.
Below the source: quantities/thumbnails of newly introduced pieces, real library colour names with identifier fallback, and the complete parts list toggle.
Bottom: previous, replay, full-build playback and next; grouped main-step dots plus a seekable microstep selector retain original main-step numbering. Substep controls expose every callout and attachment.

For callout instructions, show the subassembly clearly separated while it is built. On attachment, move the
same instances into the main assembly and keep the existing structure visible. “No new pieces” is valid
on an attachment microstep. A finished build is shown only at the correct final step.

An exploded view may be included if it is deterministic and useful, but it is not a required V1 gate.
Do not label an exploded presentation as physically validated placement. Preserve the exact final snapshot.

## Screen D — review
Developer/reviewer mode opens findings beside the source and model on wide desktop; at overlay widths it uses a keyboard-accessible dialog with focus containment, Escape and focus restoration. Inspecting a finding dismisses the overlay to reveal its instruction. It displays the source crop and candidate render, outstanding findings, selected instance,
part candidates, colour, translation and rotation controls with supported snapping. Include undo, save revision
and revalidate. Corrections are explicit events, not direct mutation of accepted data. Display the origin of
suggested mappings and whether the reviewer is an agent or a human.

## Interaction details
Use keyboard-operable buttons and visible focus. Arrow-key navigation should not capture typing inside fields.
Offer click controls for operations that otherwise need drag gestures. Respect reduced motion: placement can
jump to the final state instead of animating. Progress is locally saved with revision-aware keys.
Do not write camera positions to persistent storage on every animation frame.

Colour and numbering are both needed for new-part emphasis. Parts lists use distinct physical quantity and
part ID; repeated IDs may aggregate only when colour matches. A missing part asset surfaces its identifier and
blocks misleading rendering—never replace it silently with a generic box.

## Responsive layout
At tablet sizes, retain the left rail and model stage with compact controls. At phone width, keep shared
instruction context above `3D`, `Guide` and `Pieces` tabs and persistent next/previous controls below.
Tabs support arrow keys and Home/End with associated tab panels. Reserve space for camera tools so they
do not cover the default model framing.
Test 1440×900 and 390×844 at minimum. No page-wide horizontal overflow. Verify the source image is legible
when opened/zoomed rather than forcing the entire instruction sheet into a tiny frame.

## Evidence and visual acceptance
Capture source lookup, not-ready, partial build, callout build, attachment, review-needed and final-build states.
Compare the UI against this written spec and the style reference. The concept's incorrect copy/counts must
not be copied for visual fidelity. Inspect real screenshots for clipping, typography, spacing, source alignment
and 3D visibility. JavaScript tests alone are not a visual review.
