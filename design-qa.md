# Brick Playground landing design QA — 3 October 2026

## Target and evidence

Source visual truth: `var/evidence/landing-playground/selected-reference.png`, the first displayed landing
concept selected by the user. Actual source is 1199×1312 pixels. Local implementation:
`http://127.0.0.1:5173/`, initial landing state, supported set number prefilled, no lookup response yet.

Final comparison: selected-reference.png and desktop-final.png opened together in one image comparison
input. CSS viewport 1199×1312, density 1; full-page implementation 1199×1339. The extra 27px belongs to the
explicit artwork/provenance footer note, an intentional product constraint. No scaling/stretching was used.
The shared 1199px-wide header, hero and process sections were compared directly. All text and controls
were readable in the paired full-resolution images; a separate close crop was unnecessary.

Additional inspected captures: phone-final.png at 390px (final phone layout),
phone-found.png (real supported-booklet response), tablet.png and tablet-final.png at 768px,
phone-320-final.png (final small-phone caption placement). `desktop-first.png` and `desktop-second.png`
are earlier iteration evidence, not acceptance images. The previous Open Studio QA report remains at
`var/evidence/open-studio/design-qa.md`.

## Findings and comparison history

- P2, initial hero: tail cropped at the right edge and fallback typography was compressed. Reduced desktop
  artwork width from 59% to 55%, adjusted right offset, and loaded a self-hosted Inter font under a landing-only
  alias. Second capture revealed the wider type reaching the blue brick. Reduced headline scale from 6.5vw
  to 6vw; final paired comparison shows readable type and a complete plane silhouette. Evidence:
  desktop-first.png → desktop-second.png → desktop-final.png.
- P2, tablet: illustration crowded the search action and lost its tail beyond the frame. The medium-width
  artwork now occupies 44% of the hero and stays at its lower-right edge. tablet-final.png shows the complete
  plane and clear form/text. Desktop and phone rules are unchanged by this breakpoint repair.
- P2, smallest phone: rotated artwork caption overlapped the tail at 320px. Moved the phone caption above
  the plane; phone-320-final.png confirms separation and no horizontal overflow.
- P2, independent content review: generated decorative art was not visibly distinguished from product
  evidence. Added “Illustrative preview” beside the hero label and a shared footer note. Actual tutorial
  source crops, geometry and review status remain unchanged.

No actionable P0/P1/P2 findings remain in this scope.

## Five fidelity surfaces

- Typography: self-hosted Inter 400–800, navy display type, two-line hero, comfortable body and form labels.
  Existing tutorial font remains untouched. Final desktop line breaks and responsive headings are legible.
- Layout: white compact header, approximately 600px yellow desktop hero, large right-hand model artwork,
  prominent inline search and direct-example action, three evenly spaced process columns. Phone places the
  form before artwork and uses illustrated process rows. Results/errors appear after the hero and receive
  keyboard focus. The source concept has no result/error mock; these states follow existing product behavior.
- Colours/tokens: warm yellow#ffe143, navy type, blue actions, red/green/blue/yellow brick accents, white
  process surface and subtle separators. Flat CSS surface intentionally replaces the concept's light spill;
  lighting is carried by generated raster assets rather than drawn CSS imagery.
- Images: all four image slots use separately generated transparent raster artwork from the selected target,
  compressed as WebP with original PNG evidence retained. No CSS/SVG substitute art, placeholder or baked-in
  page screenshot. Booklet/tablet art is decorative; exact graphic detail and lighting differ from the concept.
- Content: selected headline, purpose, supported set, CTA and three-step explanation retained. APIs supply
  the actual set/guide. No invented catalogue, accounts, shopping, automatic conversion or review claims.
  Added artwork qualifier is intentional; it accounts for the slight full-page height difference.

## Behavior and verification

- `npm run check`: 26 frontend tests pass, TypeScript and production build pass.
- Relevant browser suite: 8/8 pass in 19.2s, covering new landing, current preparation and full real-source
  integration. Additional focused responsive/shortcut rerun: 3/3 pass in 3.8s.
- Automated widths: 1199,768,390,320; no horizontal overflow, primary search remains in the viewport,
  illustration assets load, How it works anchor reaches the explanation, example resolves real alt-02 and
  enters tutorial, return restores set-result focus, unavailable reconstruction retains preparation, malformed
  input remains actionable. Existing integration covers all 16 instructions, source/BOM synchronization,
  camera, callouts, review, reload and resume.
- Manual: inspected desktop/phone/tablet and phone result, opened the actual tutorial, returned to landing.
  Final browser console checked. No tutorial renderer/style edits. No new motion added.
- Local font requests only; font license retained. Artwork payload 556,990bytes, approximately 544KiB.

Limits: current Chromium desktop browser and viewport emulation; Safari, real-device touch and full
screen-reader audit were not run. Existing Three.js chunk-size advisory remains. Reconstruction accuracy,
human review and physical testing are unchanged. No publication or deployment.

P3 follow-up only: generated illustration lighting and booklet angle differ slightly from the mock; the
handwritten decorative arrow is omitted. These do not change hierarchy or the chosen theme.

final result: passed

## Follow-up: shared palette, booklet dialog and Step 3 stability

User-selected yellow/blue direction now extends through tutorial, preparation and review. Native
booklet dialog replaces the broad inline result. Manual final inspection: `var/evidence/theme-consistency/dialog-1440.png`,
`tutorial-final.png`, `review-final.png`, `phone-attach-final.png`; phone dialog widths also verified at390/320.
The final active substep is solid blue, instruction context pale yellow, header bright yellow and model
stage neutral for real piece legibility. Reserved sibling copy space is intentional to prevent control
movement. Shared camera framing intentionally leaves more room after attachment so the view stays stable.

Interaction checks passed: keyboard popup cycle/Escape/restore; closing pending fetch; all16 replay
outcomes; visible two-pulse highlight and exact final snapshot restoration; Steps3/4 stable panel/control
rectangles at1440/900/390/320; reduced motion. Independent async-dismiss issue fixed and rechecked.
All26 unique browser checks passed across the broad run and affected-file rerun. See validation report
for exact run boundaries. No generated decorative artwork was introduced as assembly evidence.
