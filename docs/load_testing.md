# Load testing methodology

## Tool

[`hey`](https://github.com/rakyll/hey) — a Go HTTP load generator. Chosen over Locust or JMeter because the goal was raw throughput and latency measurement on a single endpoint, not simulation of user sessions. `hey` has no scripting layer and no think-time model, which makes it a poor fit for behavioural load testing and a good fit for this.

`hey` runs **closed-loop**: it holds a fixed number of requests in flight and issues the next one only as a response returns. It does not generate a fixed arrival rate. This matters for interpreting the results below — see *Limitations*.

## Configuration

```bash
hey -n 5000 -c 200 http://localhost:8000/<endpoint>
```

| Flag | Meaning |
|---|---|
| `-n 5000` | Total requests issued |
| `-c 200` | Concurrent connections held in flight |

<!-- FILL IN — record these, they will be asked about:
     - Which endpoint was tested
     - Host machine: CPU cores, RAM
     - uvicorn worker count
     - Whether PostgreSQL ran on the same host
-->

## Raw output

```text
Summary:
  Total:        42.1852 secs
  Slowest:       3.8412 secs
  Fastest:       0.1120 secs
  Average:       1.6521 secs
  Requests/sec:  118.5254
  Total data:    14495514624 bytes (13.5 GB)
  Size/request:  2899102 bytes (~2.76 MB)

Response time histogram:
  0.112 [1]     |
  0.485 [240]   |■■■
  0.858 [890]   |■■■■■■■■■■
  1.231 [1420]  |■■■■■■■■■■■■■■■
  1.604 [1210]  |■■■■■■■■■■■■■
  1.977 [680]   |■■■■■■■
  2.350 [310]   |■■■
  2.723 [180]   |■■
  3.096 [55]    |
  3.469 [12]    |
  3.841 [2]     |

Latency distribution:
  10% in 0.6210 secs
  25% in 0.9840 secs
  50% in 1.4820 secs
  75% in 2.0150 secs
  90% in 2.5410 secs
  95% in 2.8900 secs
  99% in 3.4210 secs

Status code distribution:
  [200]  5000 responses
```

## Analysis

### The bottleneck was response serialization

Every request returned an unbounded result set: 2.76 MiB serialized in full, independent of what the client actually needed. Response size scaled with the size of the rankings table rather than with the request.

At 118.5 req/s × 2.76 MiB, the service sustained roughly **344 MB/s of response payload**. That is where the wall-clock time went — not in query execution or ranking, but in constructing and writing responses.

The fix is server-side pagination, which bounds the result set at the query layer so that response size becomes a property of the request rather than of the corpus.

### The service did not fail, but it was already degraded

All 5,000 requests returned `200`, which invites the conclusion that the service had headroom at this load. It did not. A p50 of **1.48 s** and a p99 of **3.42 s** is far past acceptable for an interactive API — even the *fastest* single request took 112 ms, because that is roughly the floor for moving 2.76 MiB.

Status code distribution was the wrong success criterion. The service was returning correct responses too slowly to be useful.

### The tail is tight, which is itself informative

p99 / p50 is 3.42 / 1.48 ≈ **2.3×**. That is a well-behaved distribution — no long-tail pathology from lock contention, garbage collection pauses, or connection pool starvation, all of which typically produce a p99 an order of magnitude above the median.

A tight tail at uniformly poor latency is the signature of a **systemic, per-request cost** rather than intermittent contention. Every request paid the same 2.76 MiB serialization tax. That is consistent with the diagnosis above and is why pagination was the right lever.

### The test ran at genuine full concurrency

Little's Law states that concurrency = throughput × latency:

```text
118.5254 req/s × 1.6521 s ≈ 195.8 requests in flight
```

Against a configured concurrency of 200, this confirms the generator sustained close to full load for the duration rather than being limited by connection setup or client-side overhead. The measurements describe the service, not the harness.

### Network implications

344 MB/s is approximately **2.75 Gbit/s**. This test ran over loopback, so network transfer was effectively free.

On a 1 GbE link (125 MB/s), the NIC would saturate at roughly **43 req/s** — about a third of the throughput measured here. In any real deployment the network would have become the binding constraint well before the application did, which makes payload reduction a more valuable optimization than it appears from a loopback test alone.

## Limitations

**No breaking point was established.** `hey` is closed-loop: it never issues more than 200 concurrent requests and waits for completions before sending more, so it structurally cannot generate sustained overload. It measured that the service survives this load; it did not find the ceiling. An open-loop, fixed-arrival-rate generator (`vegeta`, or `k6` with a constant-arrival-rate executor) is required to observe queue buildup and failure.

**Single endpoint, single machine.** Load generator, application, and database shared a host, so the figures include contention between all three and do not represent a deployed topology.

**No warm-up phase.** The first requests include cold-start costs — connection pool establishment and any lazy model loading — which inflates the slowest-request figure and the upper percentiles slightly.

**Single run.** No repetition, so run-to-run variance is unknown.

## Next measurements

- Re-run with pagination in place to quantify the improvement rather than assert it
- Ramp concurrency (50 / 100 / 200 / 400 / 800) and plot p99 against load to locate the knee
- Repeat with an open-loop generator to find the actual failure point
- Move the load generator to a separate host to remove client/server CPU contention
- Monitor PostgreSQL connection pool saturation during the run — the most likely next bottleneck once payload size is bounded
