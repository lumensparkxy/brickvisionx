# Ten-set release evaluation: official source matrix

Research date: 2026-10-03. This is a source-selection record, **not a claim that ten sets convert, render or assemble correctly**. The application catalogue inspected during this research contains only set 30669 / `alt-02`. Runtime outcomes belong in the release-test report.

The requested split is three simple, three medium and four complex sets. These are our evaluation tiers, not LEGO classifications: simple has fewer than 150 advertised pieces, medium has 150–800, and complex has more than 1,000. Piece count is a workload proxy, not a measure of geometric or reconstruction difficulty. The mixture deliberately includes Creator alternatives, separate models, Technic and large buildings.

## Selected sets

Names, set numbers, ages, advertised counts and listed PDF sizes below come from the linked official LEGO instruction pages. Sizes are the website's displayed MB values, not independently measured byte counts. No purchase availability is asserted.

| Tier | Set | Official set name / source | Advertised set pieces | Age | PDFs listed on official page | Evaluation purpose |
|---|---|---|---:|---|---|---|
| Simple | 30669 | [Iconic Red Plane](https://www.lego.com/en-us/service/building-instructions/30669) | 51 | 6+ | Three entries labeled 1/1: 3.21, 2.25, 2.39 MB | Existing alternate-booklet baseline; callouts and attachment transitions. |
| Simple | 60400 | [Go-Karts and Race Drivers](https://www.lego.com/en-us/service/building-instructions/60400) | 99 | 5+ | 1/2: 6.05 MB; 2/2: 6.90 MB | Two small models; booklet selection and set-wide completion accounting. |
| Simple | 31134 | [Space Shuttle](https://www.lego.com/en-us/service/building-instructions/31134) | 144 | 6+ | 1/3: 12.89 MB; 2/3: 8.06 MB; 3/3: 7.67 MB | Creator alternative selection; prevent treating different models as sequential booklets. |
| Medium | 31129 | [Majestic Tiger](https://www.lego.com/en-us/service/building-instructions/31129) | 755 | 9+ | 1/3: 34.11 MB; 2/3: 14.18 MB; 3/3: 13.67 MB | Larger organic and articulated model; alternate-model identity. |
| Medium | 42163 | [Heavy-Duty Bulldozer](https://www.lego.com/en-us/service/building-instructions/42163) | 195 | 7+ | 1/1: 7.68 MB | Small Technic geometry and connector variety before large Technic evaluation. |
| Medium | 76920 | [Ford Mustang Dark Horse Sports Car](https://www.lego.com/en-us/service/building-instructions/76920) | 344 | 9+ | 1/1: 21.24 MB | Detailed compact vehicle; varied orientations and dense assembly. |
| Complex | 42171 | [Mercedes-AMG F1 W14 E Performance](https://www.lego.com/en-us/service/building-instructions/42171) | 1,643 | 18+ | 1/1: 101.03 MB | Large Technic source and rendering workload. |
| Complex | 21343 | [Viking Village](https://www.lego.com/en-us/service/building-instructions/21343) | 2,103 | 18+ | 1/1: 112.15 MB | Large building assembly; prolonged instruction navigation and working set. |
| Complex | 21061 | [Notre-Dame de Paris](https://www.lego.com/en-us/service/building-instructions/21061) | 4,383 | 18+ | 1/1: 193.04 MB | Large single-PDF boundary and many repeated small elements. |
| Complex | 10316 | [THE LORD OF THE RINGS: RIVENDELL™](https://www.lego.com/en-us/service/building-instructions/10316) | 6,167 | 18+ | 1/3: 72.10 MB; 2/3: 79.72 MB; 3/3: 184.68 MB | Largest selected set; multi-book identity, ordering, storage and memory. |

The evaluation-purpose column is an engineering selection rationale. It is not a source-derived assembly reconstruction. The official Tiger and Rivendell pages list their links in the order 1/3, 3/3, 2/3; do not use DOM order as assembly order.

## Source and selected-build boundaries

- An advertised **set count is not a selected booklet BOM**, visible-instance count, triangle count or draw-call count. The existing 30669 alternate build uses a subset of the advertised 51-piece set. Other selected booklet BOMs remain unmeasured.
- Resolve a specific model/booklet before conversion. Three Creator PDFs can describe alternatives; multiple PDFs can also describe separate models or sequential portions of one build. A fraction in a link label does not settle that distinction. Inspect official booklet covers and content before assigning guide identity.
- The existing catalogue provides the exact 30669 source: [30669_02_BI_Build_Alt.pdf](https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_02_BI_Build_Alt.pdf). It was read from `config/sets.json` and also freshly observed in the official page HTML; this research did not download or hash the PDF. Catalogue metadata says eight pages and twelve main steps, checked 2026-10-01.
- For all ten sets, this pass records official instruction **page** links and their actual visible PDF card destinations, labels and sizes. PDF bytes, signatures, hashes, dimensions, page counts and assembly coverage were not fetched or verified. No CDN URL was guessed. Nothing was added to the production catalogue.
- The initial web-tool attempts for the US and Netherlands 60400 pages failed. A subsequent bounded direct HTML fetch succeeded for all ten official US pages with HTTP 200, including 60400. Its US booklet sizes are 6.05 and 6.90 MB; some other locales list 6.03 and 6.88 MB. Do not mix locale variants when identifying a source.
- Name/count checks used official web-tool results, which can be indexed snapshots. The subsequent live HTML fetch checked displayed headings and exact PDF card hrefs. This does not establish continuous uptime or byte-level reproducibility. Current stock, price and retail availability were outside scope.

## Observed PDF destinations

Machine-readable record: `var/evidence/ten-set-release/source-research.json`. Observed at 2026-10-03T09:53:55.382807+00:00. Each page read was capped at 4,000,000 bytes with a 20-second request timeout; all ten returned HTML and status 200. Only visible instruction-list cards were extracted. No hidden API was used. The linked asset IDs below are copied from the observed hrefs, not derived from set numbers. PDF page counts remain unknown.

| Set | Official card label | Exact linked asset | Listed MB |
|---|---|---|---:|
| 30669 | Iconic Red Plane (1/1) | [6491702](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6491702.pdf) | 3.21 |
| 30669 | Iconic Red Plane (1/1) | [30669_01_BI_Build_Alt](https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_01_BI_Build_Alt.pdf) | 2.25 |
| 30669 | Iconic Red Plane (1/1) | [30669_02_BI_Build_Alt](https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_02_BI_Build_Alt.pdf) | 2.39 |
| 60400 | Go-Karts and Race Drivers (1/2) | [6490975](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6490975.pdf) | 6.05 |
| 60400 | Go-Karts and Race Drivers (2/2) | [6490976](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6490976.pdf) | 6.90 |
| 31134 | Space Shuttle (1/3) | [6457820](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6457820.pdf) | 12.89 |
| 31134 | Space Shuttle (2/3) | [6457822](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6457822.pdf) | 8.06 |
| 31134 | Space Shuttle (3/3) | [6457824](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6457824.pdf) | 7.67 |
| 31129 | Majestic Tiger (1/3) | [6401641](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6401641.pdf) | 34.11 |
| 31129 | Majestic Tiger (3/3) | [6401645](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6401645.pdf) | 13.67 |
| 31129 | Majestic Tiger (2/3) | [6575247](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6575247.pdf) | 14.18 |
| 42163 | Heavy-Duty Bulldozer (1/1) | [6495263](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6495263.pdf) | 7.68 |
| 76920 | Ford Mustang Dark Horse Sports Car (1/1) | [6507100](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6507100.pdf) | 21.24 |
| 42171 | Mercedes-AMG F1 W14 E Performance (1/1) | [6562099](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6562099.pdf) | 101.03 |
| 21343 | Viking Village (1/1) | [6483079](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6483079.pdf) | 112.15 |
| 21061 | Notre-Dame de Paris (1/1) | [6634577](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6634577.pdf) | 193.04 |
| 10316 | THE LORD OF THE RINGS: RIVENDELL™ (1/3) | [6455635](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6455635.pdf) | 72.10 |
| 10316 | THE LORD OF THE RINGS: RIVENDELL™ (3/3) | [6455639](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6455639.pdf) | 184.68 |
| 10316 | THE LORD OF THE RINGS: RIVENDELL™ (2/3) | [6698730](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6698730.pdf) | 79.72 |

## Bottlenecks to test before claiming coverage

1. **Catalogue and conversion reachability.** Unsupported set lookup is a real coverage failure, even if the error UI behaves correctly. A source page being available is not proof that a scene exists.
2. **Bounded download limits.** Every selected complex set lists at least one PDF above 100 MB; Rivendell lists about 336.50 MB across three books. Compare these with actual configured byte, page, time, pixel and memory ceilings. Do not simply remove resource limits to make a test pass.
3. **Book identity and resumability.** Record separate source hashes, ordering and checkpoints for each selected book. Resume interrupted processing without mixing alternatives or redoing completed work.
4. **Correctness evidence.** For every actual reconstruction, compare official instruction panels, part identities, poses, assembly groups, final BOM and final view. Missing geometry is an explicit failure, not permission to replace it with a generic brick. Automated structural validity does not establish human review or physical assembly.
5. **Renderer measurements.** Measure actual loaded triangles, draw calls, geometry/texture counts, first usable frame, interaction-frame percentiles, long tasks, idle-render behavior and load/unload memory behavior. GPU timer queries, when supported and not disjoint, measure GPU work; JavaScript render duration is CPU submission time. Synthetic repeated geometry can expose scaling but cannot count as another successfully reconstructed set.

No source PDFs, community models or finished assemblies were downloaded by this research task. No external inference, credentials, publishing or catalogue mutation was used.
