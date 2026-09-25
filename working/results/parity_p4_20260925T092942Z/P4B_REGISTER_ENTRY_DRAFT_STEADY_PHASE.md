# DRAFT register entry (proposal; not added to METHODOLOGY_REGISTER.md)

## Proposed: steady-phase docs/s as the smoke metric for throughput gates

> P2-A and P3-A ran their smoke gates on the 384-document slice with span docs/s: documents answered ok divided by the
> first submission to the last completion. On that slice the span is mostly drain, the tail after the last submission
> when fewer than C documents remain in flight. The drain penalises whichever arm has the longer tail, and it leaves the
> box idle, so a span-based smoke neither predicted the full-scale ratio (P2-A's gate did not fire, yet P3-A's full run
> cleared the bar) nor ranked thread shapes the way full scale did (P3-C, register 60).
>
> P4-B (1) re-read the committed 384-slice legs with P0's steady-phase definition: ok documents completed by the last
> submission, divided by the time to the last submission. The rule was fixed in P4's pre-registration before the
> figures were computed; the validation is POST-HOC, on legs that already existed. By that rule it VALIDATES: in both
> sessions (P2-A, P3-A health) the steady-phase RocketRide/LlamaIndex ratio agrees with the full-scale ratio within
> LlamaIndex's replicate spread, and the steady phase ranks vars=4 below vars=1, as full scale did (analysis_p4b.json).
>
> Proposed rules:
>
> - **A throughput smoke gate on a slice reads steady-phase docs/s, not span docs/s.** Report the span and the drain
>   share beside it.
> - **Only ratios and rankings carry over.** The absolute steady-phase rate on the slice is not full-scale
>   throughput, so it is never quoted as throughput.
> - **The validation is two sessions and one shape comparison, post-hoc.** The first pre-registered use of the metric
>   should record its own full-scale confirmation, and the rule is revisited if it disagrees.
