## Summary
<!-- 1 to 3 sentences: where in the product the change acts, what users or the system experienced before, what happens now, and why. Situate every screen, state, or internal layer before naming it. -->

## References
- **Issue**: <!-- [labeled link] -->
- **Origin**: <!-- [labeled link] -->
- **Related PRs**: <!-- [links] -->
- **Other**: <!-- [docs, recordings, mockups] -->

## What Changes
```text
<!--
+  table of exported invoices          table · billing-api
+  "export invoice as PDF" route       route · billing-api
~  invoice page offers the export      screen · web-app
~  PDFs deleted after 90 days          rule · billing-api · was: kept forever
-  manual export script                job · billing-api
!  PDF layout written inside the job   out of pattern · other documents use the templates folder, because …

unchanged  no new service, queue, secret, or client · no data rewritten or sent out · contracts and boundaries intact
-->
```

## Decisions
<!-- Each decision taken and its reason, ordered by cost to reverse after merge, the hardest first: business rules, contracts created or altered, consequential trade-offs, assumptions, and maintenance commitments. Omit when there is nothing material. -->

## How It Works
<!-- Only when the change alters a flow across places of the system: a visualize-it swimlane as a Mermaid sequenceDiagram, then at most two sentences on what to notice. Omit otherwise. -->

## Test Evidence
| | Behavior | How it was verified | How to check |
| :---: | :--- | :--- | :--- |
| ✅ | <!-- behavior description --> | <!-- unit/integration test in path --> | Covered by test suite |

## Impact
<!-- Contract breaks, database migrations, new environment variables, and what a deploy or rollback needs; "None" when there are none. -->
