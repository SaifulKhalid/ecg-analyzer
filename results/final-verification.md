# Final verification

Educational screening tool, not a medical device.

Observed during the final resumed checks on 2026-11-22:

| Check | Result | Evidence |
| --- | --- | --- |
| Python suite | PASS | 111 tests, 15.73 seconds; nonfatal upstream PyParsing deprecation warnings |
| Node suite | PASS | 30 tests after the measured-report prompt update |
| Existing Worker build | PASS | `cf build` under isolated Node 22.18; frontend and Worker bundles generated |
| Browser / API story | PASS | [Desktop/mobile demos, image uploads and actual-reply replay](ui-verification.md) |
| Production LLM boundary | PASS | Measured JSON plus config definitions only; no images or raw samples |
| Explanation numeric guard | PASS | Mock failures preserve measurements; [live reply passes 14 checks](grounded-explanation.json); [rejected live response also preserved](grounding-rejected.json) |
| Frozen measurement code | PASS | SHA-256 matches the [predeclared fresh-study manifest](holdout/manifest.json) |
| Git / credential-data audit | PASS | No tracked dataset/credential files or configured AgentRouter key values; whitespace check passes |
| Local demo readiness | PASS | Node :3000 -> FastAPI :8765 health ok; 9 demos available |

Wider detector evidence: [150.46-minute MIT-BIH validation](long-validation.md).
Original first-minute gate and both image comparisons remain preserved.
Numeric grounding does not establish clinical correctness or check written-out
numbers. The controlled-image comparisons do not validate patient screening or
photograph accuracy. No deployment or dataset training was performed.
