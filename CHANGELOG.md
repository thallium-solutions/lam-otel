# @lam/otel Changelog

All notable changes to `@lam/otel` are documented here. The package follows
semantic versioning; tags are plain versions (`1.0.0`).

## [1.0.0] - 2026-10-19

First release as an official Lammergeier library. `@lam/otel` replaces the
`lamotel` 0.2.1 package that was vendored in `lammergeier-lang/third_party`
and grows it from a single-span exporter into a dependency-free
OpenTelemetry SDK for traces, metrics and logs over OTLP/HTTP JSON.

### Moved

- From `third_party/lamotel` 0.2.1 (MIT) in the compiler repository to its own
  repository, `thallium-solutions/lam-otel`, under the **Apache-2.0** license
  (see `LICENSE` and `NOTICE`).
- Import path: `from lamotel import ...` becomes `from @lam/otel import ...`.
- Tests run through the installed-package boundary
  (`tests/run_lamotel_tests.py` stages the package into a temporary
  `extlibs/@lam/otel` and uses the `lamc` found on `PATH`); requires
  `lamc` 2.1 or newer (`compatibility.lamc = ">=2.1, <4"`).

### Breaking changes

- Export methods return payload-typed results:
  `OtelTracer.exportSpan`/`exportSpans` and `OtelSpanBatch.export` return
  `Result[OtelExportResult]` (status, body, attempts, items, partial-success
  details) instead of an untyped `Result` wrapping an `HttpResponse`.
- `OtelTracer(cfg)` is now `OtelTracer.fromConfig(cfg)` (or
  `OtelTracerProvider.fromConfig(cfg).tracer(name, version)`); the
  constructor takes the owning provider. `OtelTracer.fromEnv()` is unchanged.
- Span kinds and status codes are the OTLP integers: `OtelSpanKind.SERVER`
  instead of `"server"`, `OtelStatusCode.ERROR` instead of `"error"`
  (`OtelSpanKind.parse` / `OtelStatusCode.parse` convert old strings).
  `setStatus` follows the specification: `OK` is final, the description is
  only kept for `ERROR`.
- `recordException(message)` only records the `exception` event (with
  `exception.message`/`exception.type`/`exception.stacktrace` on the event,
  not on the span) and no longer sets the status; use `span.fail(message)`
  for the old behaviour.
- Timestamps are Unix nanoseconds: `startUnixMs`/`endUnixMs` became
  `startTimeUnixNano`/`endTimeUnixNano`; `durationMs()` is kept and
  `durationNanos()` was added.
- Span mutators (`setAttribute`, `addEvent`, `setStatus`, ...) no longer
  return a value. Attribute values keep their type (`int`, `float`, `bool`,
  lists) instead of being strings.
- `OtelSpan.toDict(serviceName)` was removed; `toJson()` returns the OTLP/JSON
  span. `Otel.tracesPayload(serviceName, spans)` and
  `Otel.tracesPayloadWithResource(...)` were replaced by
  `Otel.tracesPayload(spans)`, which groups spans by their resource and
  instrumentation scope. The payload now follows the OTLP/JSON mapping
  (`KeyValue` attribute lists, integer enums, string-encoded 64-bit
  integers).
- `OtelConfig.resource()` returns an `OtelResource` (use `getString(key)` or
  `attributes`) instead of `dict[str, str]`, and includes the
  `telemetry.sdk.*` attributes.
- Defaults follow the specification: the service name defaults to
  `unknown_service` (was `lammergeier-app`), a `service.name` entry of
  `OTEL_RESOURCE_ATTRIBUTES` is honoured when `OTEL_SERVICE_NAME` is unset,
  and the export timeout comes from `OTEL_EXPORTER_OTLP_TIMEOUT` (default
  10 s, was a fixed 30 s).
- `OtelSpan.setParent` returns nothing; prefer `startSpan(..., parent=ctx)`.
- `User-Agent` is `lam-otel/1.0.0` and the instrumentation scope defaults to
  `@lam/otel` 1.0.0 (tracers name their own scope).

### Added

- Configuration from the standard variables: `OTEL_SDK_DISABLED`,
  `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`,
  `OTEL_EXPORTER_OTLP_{,TRACES_,METRICS_,LOGS_}{ENDPOINT,HEADERS,TIMEOUT,COMPRESSION}`,
  `OTEL_{TRACES,METRICS,LOGS}_EXPORTER` (`otlp`, `console`, `none`),
  `OTEL_PROPAGATORS`, `OTEL_TRACES_SAMPLER[_ARG]`, `OTEL_BSP_*`,
  `OTEL_BLRP_*`, `OTEL_METRIC_EXPORT_{INTERVAL,TIMEOUT}` and the attribute,
  span, event, link and log-record limits.
- OTLP/HTTP JSON transport shared by all signals: per-signal URLs, headers
  and timeouts, optional gzip, retries with exponential backoff on
  429/500/502/503/504 honouring `Retry-After`, partial-success parsing.
- Tracing: `OtelTracerProvider`, `OtelSpanContext`, span events, links,
  limits with dropped counts, `recordError(Error)`, `updateName`,
  `startSpanFromHeaders`, `withSpan`, W3C Trace Context (`OtelTraceContext`,
  including `tracestate` helpers), W3C Baggage (`OtelBaggage`), composite
  `OtelPropagator`, samplers (`alwaysOn`, `alwaysOff`, `traceIdRatio`,
  `parentBased`, `custom`, `fromConfig`), `OtelSimpleSpanProcessor` and
  `OtelBatchSpanProcessor` (bounded queue, batch size, periodic background
  flush, export timeout, `forceFlush`, `shutdown`), and the
  `OtelSpanProcessor`/`OtelSpanExporter` interfaces for custom components.
- Metrics: `OtelMeterProvider`, `OtelMeter`, `OtelCounter`,
  `OtelUpDownCounter`, `OtelGauge`, `OtelHistogram` (explicit buckets, min,
  max), observable gauges/counters/up-down counters, cumulative temporality,
  per-instrument cardinality limit with an overflow series, and
  `OtelMetricReader` (periodic or manual).
- Logs: `OtelLoggerProvider`, `OtelLogger` (`trace` ... `fatal`, `emit`),
  `OtelSeverity`, trace/span correlation, minimum severity, attribute limits,
  `OtelSimpleLogProcessor` and `OtelBatchLogProcessor`.
- Exporters for every signal: OTLP (`OtelOtlpSpanExporter`,
  `OtelOtlpMetricExporter`, `OtelOtlpLogExporter`), in-memory exporters for
  tests and console exporters (one JSON line per item).
- `Otel` facade: `setup()` (all providers from the environment), global
  providers and propagator, `inject`/`extract`, `forceFlush`, `shutdown`.
  `Otel.idsTrace()`, `Otel.idsSpan()`, `Otel.parsePairs()` and
  `Otel.parseHeaders()` are kept from `lamotel`; `parsePairs` now
  percent-decodes values.
- IDs come from a cryptographically secure random source and are never all
  zeros.

### Testing

- 16 offline tests (one per feature plus a composed HTTP-service scenario and
  the ported `lamotel` scenarios) against ephemeral local collectors that
  assert the OTLP JSON shape, and the guarded `tests/live_export.lam`
  (`--live` with `LAMOTEL_LIVE_TESTS=1`).

## lamotel 0.2.1 - 2026-10-15

History of the vendored package, for reference.

- Convert span attribute maps with `Json.fromValue(...)` when building the
  OTLP payload.
- The OTLP instrumentation scope and `User-Agent` report the package version
  (`0.2.1`) instead of the stale `0.1.0`.

## lamotel 2026-09-25

- Offline composed tracing test; optional environment reads use `Env.getOr`;
  OTLP export consumes `HttpClient.post -> Result[HttpResponse]`.
