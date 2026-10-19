# @lam/otel

`@lam/otel` is the official [OpenTelemetry](https://opentelemetry.io) library
for [Lammergeier](https://lammergeier-lang.dev): traces, metrics and logs for
Lam services, exported to any OpenTelemetry Collector or OTLP-compatible
backend (Jaeger, Grafana Tempo/Mimir/Loki, Honeycomb, Datadog, New Relic, ...)
over **OTLP/HTTP with JSON encoding**.

Why use it:

- **Dependency-free.** Built only on the Lam standard library (`lamhttp`,
  `lamjson`, `lamconcurrency`, ...) and the Go standard library: no Go modules
  to pin, nothing to vendor.
- **Standard configuration.** Reads the usual `OTEL_*` environment variables
  (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
  `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_TRACES_SAMPLER`, ...), so deployment
  manifests written for other OpenTelemetry SDKs keep working.
- **Production behaviour.** Batch processors with bounded queues and
  background flushing, retries with exponential backoff on `429`/`5xx`,
  export timeouts, gzip, span limits, samplers, W3C Trace Context and Baggage
  propagation, cumulative metrics with a cardinality limit.
- **Testable.** In-memory exporters for every signal and console exporters
  for local debugging.

`@lam/otel` 1.0.0 replaces the `lamotel` 0.2.1 package that used to be
vendored in the compiler repository; see [CHANGELOG.md](CHANGELOG.md) for the
migration notes.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Examples](#examples)
- [API reference](#api-reference)
- [Behaviour notes](#behaviour-notes)
- [Testing](#testing)
- [License](#license)

## Installation

`@lam/otel` requires `lamc` 2.1 or newer. Add it to the `[dependencies]` of
your project's `lamlib.toml`:

```toml
[dependencies]
"@lam/otel" = { git = "https://github.com/thallium-solutions/lam-otel.git", ref = "1.0.0" }
```

and install it:

```bash
lamc install
```

Then import what you need:

```lammergeier
from @lam/otel import Otel, OtelTracer, OtelSpan, OtelSpanKind, OtelStatusCode
```

## Quick start

```lammergeier
from @lam/otel import Otel, OtelSdk, OtelTracer, OtelSpan, OtelSpanKind, OtelStatusCode, OtelCounter, OtelLogger
from lamerrors import Result

func main() {
    # Reads OTEL_SERVICE_NAME, OTEL_EXPORTER_OTLP_ENDPOINT, ... and installs
    # tracer, meter and logger providers globally.
    sdk: OtelSdk = Otel.setup()

    tracer: OtelTracer = Otel.tracer("orders", "1.0.0")
    orders: OtelCounter = Otel.meter("orders", "1.0.0").counter("orders.created", "{order}")
    logger: OtelLogger = Otel.logger("orders")

    span: OtelSpan = tracer.startSpan("create order", OtelSpanKind.INTERNAL, None, {"order.items": 3})
    orders.add(1, {"channel": "web"})
    logger.info("order created", {"order.id": "o-42"}, span.spanContext())
    span.setStatus(OtelStatusCode.OK)
    span.end()

    # Flush the batch processors and the metric reader before exiting.
    down: Result[bool] = sdk.shutdown()
    if not down.ok() {
        print(f"telemetry export failed: {down.error}")
    }
}
```

Run it against a local collector:

```bash
export OTEL_SERVICE_NAME=orders
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
lamc main.lam --run
```

Without `Otel.setup()` (or the `Otel.set*Provider` calls) the global
providers are no-ops: libraries can instrument themselves with
`Otel.tracer(...)` unconditionally and only applications decide whether
telemetry is exported.

## Configuration

`OtelConfig.fromEnv()` (used by `Otel.setup()` and every `fromEnv()` factory)
reads the variables below. Unset or blank variables keep the default. Every
setting is also a public field of `OtelConfig`, so everything can be
configured in code: `OtelConfig(serviceName, endpoint, headers, timeoutMs)`
followed by field assignments.

| Variable | `OtelConfig` field | Default | Meaning |
|---|---|---|---|
| `OTEL_SDK_DISABLED` | `disabled` | `false` | `true` makes every provider a no-op. |
| `OTEL_SERVICE_NAME` | `serviceName` | `service.name` of `OTEL_RESOURCE_ATTRIBUTES`, else `unknown_service` | The `service.name` resource attribute. |
| `OTEL_RESOURCE_ATTRIBUTES` | `resourceAttributes` | – | `key=value,key2=value2` resource attributes (values percent-decoded). |
| `OTEL_SERVICE_VERSION` | `serviceVersion` | – | `service.version` (kept from `lamotel`). |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | `environment` | – | `deployment.environment` (kept from `lamotel`). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `endpoint` | `http://localhost:4318` | Base URL; `/v1/traces`, `/v1/metrics`, `/v1/logs` are appended. |
| `OTEL_EXPORTER_OTLP_{TRACES,METRICS,LOGS}_ENDPOINT` | `tracesEndpoint`, `metricsEndpoint`, `logsEndpoint` | – | Full per-signal URL, used as is. |
| `OTEL_EXPORTER_OTLP_HEADERS` | `headers` | – | `key=value,...` request headers (for example `Authorization=Bearer%20xyz`). |
| `OTEL_EXPORTER_OTLP_{TRACES,METRICS,LOGS}_HEADERS` | `tracesHeaders`, ... | – | Extra per-signal headers (win over the generic ones). |
| `OTEL_EXPORTER_OTLP_TIMEOUT` | `timeoutMs` | `10000` | Per-request timeout in milliseconds. |
| `OTEL_EXPORTER_OTLP_{TRACES,METRICS,LOGS}_TIMEOUT` | `tracesTimeoutMs`, ... | – | Per-signal timeout. |
| `OTEL_EXPORTER_OTLP_COMPRESSION` | `compression` | `none` | `gzip` or `none`. |
| `OTEL_EXPORTER_OTLP_{TRACES,METRICS,LOGS}_COMPRESSION` | `tracesCompression`, ... | – | Per-signal compression. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `protocol` | `http/json` | Informational: only OTLP/HTTP JSON is implemented. |
| `OTEL_TRACES_EXPORTER` | `tracesExporter` | `otlp` | `otlp`, `console`, `none` (comma-separated list allowed). |
| `OTEL_METRICS_EXPORTER` | `metricsExporter` | `otlp` | `otlp`, `console`, `none`. |
| `OTEL_LOGS_EXPORTER` | `logsExporter` | `otlp` | `otlp`, `console`, `none`. |
| `OTEL_PROPAGATORS` | `propagators` | `tracecontext,baggage` | `tracecontext`, `baggage`, `none`. |
| `OTEL_TRACES_SAMPLER` | `sampler` | `parentbased_always_on` | `always_on`, `always_off`, `traceidratio`, `parentbased_always_on`, `parentbased_always_off`, `parentbased_traceidratio`. |
| `OTEL_TRACES_SAMPLER_ARG` | `samplerArg` | `1.0` | Ratio for the `traceidratio` samplers. |
| `OTEL_BSP_SCHEDULE_DELAY` | `bspScheduleDelayMs` | `5000` | Batch span processor flush interval (ms). |
| `OTEL_BSP_EXPORT_TIMEOUT` | `bspExportTimeoutMs` | `30000` | Max duration of one span export (ms). |
| `OTEL_BSP_MAX_QUEUE_SIZE` | `bspMaxQueueSize` | `2048` | Spans buffered before new ones are dropped. |
| `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` | `bspMaxExportBatchSize` | `512` | Spans per export request. |
| `OTEL_BLRP_SCHEDULE_DELAY` | `blrpScheduleDelayMs` | `1000` | Batch log processor flush interval (ms). |
| `OTEL_BLRP_EXPORT_TIMEOUT` | `blrpExportTimeoutMs` | `30000` | Max duration of one log export (ms). |
| `OTEL_BLRP_MAX_QUEUE_SIZE` | `blrpMaxQueueSize` | `2048` | Log records buffered. |
| `OTEL_BLRP_MAX_EXPORT_BATCH_SIZE` | `blrpMaxExportBatchSize` | `512` | Log records per export request. |
| `OTEL_METRIC_EXPORT_INTERVAL` | `metricExportIntervalMs` | `60000` | Periodic metric export interval (ms). |
| `OTEL_METRIC_EXPORT_TIMEOUT` | `metricExportTimeoutMs` | `30000` | Max duration of one metric export (ms). |
| `OTEL_ATTRIBUTE_COUNT_LIMIT` | `attributeCountLimit` | `128` | Default attribute count limit. |
| `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` | `attributeValueLengthLimit` | unlimited | Default attribute value length limit. |
| `OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT` | `spanAttributeCountLimit` | `OTEL_ATTRIBUTE_COUNT_LIMIT` | Attributes per span. |
| `OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT` | `spanAttributeValueLengthLimit` | `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` | Span attribute value length. |
| `OTEL_SPAN_EVENT_COUNT_LIMIT` | `spanEventCountLimit` | `128` | Events per span. |
| `OTEL_SPAN_LINK_COUNT_LIMIT` | `spanLinkCountLimit` | `128` | Links per span. |
| `OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT` | `eventAttributeCountLimit` | `128` | Attributes per span event. |
| `OTEL_LINK_ATTRIBUTE_COUNT_LIMIT` | `linkAttributeCountLimit` | `128` | Attributes per span link. |
| `OTEL_LOGRECORD_ATTRIBUTE_COUNT_LIMIT` | `logRecordAttributeCountLimit` | `OTEL_ATTRIBUTE_COUNT_LIMIT` | Attributes per log record. |
| `OTEL_LOGRECORD_ATTRIBUTE_VALUE_LENGTH_LIMIT` | `logRecordAttributeValueLengthLimit` | `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` | Log attribute value length. |

Export retries are configured in code: `retryMaxAttempts` (default `5`),
`retryInitialBackoffMs` (`1000`) and `retryMaxBackoffMs` (`5000`).

## Examples

### Tracing an HTTP handler with context propagation

The handler continues the caller's trace (W3C `traceparent`/`tracestate`),
reads the caller's baggage, propagates both to a downstream call, and marks
failures. Header dictionaries are `dict[str, str]`; header names are matched
case-insensitively.

```lammergeier
from @lam/otel import Otel, OtelTracer, OtelSpan, OtelSpanKind, OtelStatusCode, OtelSpanContext, OtelBaggage
from lamerrors import Result, Error
from lamhttp import HttpClient, HttpResponse, HttpRequestOptions

class InventoryClient {
    func init(self, baseUrl: str) {
        self.client: HttpClient = HttpClient(baseUrl, 2000)
        self.tracer: OtelTracer = Otel.tracer("shop.inventory-client", "1.0.0")
    }

    func reserve(self, parent: OtelSpan, baggage: OtelBaggage, sku: str) -> Result[str] {
        span: OtelSpan = self.tracer.childSpan(parent, "POST /reservations", OtelSpanKind.CLIENT, {"shop.sku": sku})
        headers: dict[str, str] = {}
        Otel.inject(headers, span.spanContext(), baggage)
        options: HttpRequestOptions = HttpRequestOptions()
        for name, value in headers {
            options.header(name, value)
        }
        response: Result[HttpResponse] = self.client.request("POST", "/reservations", options)
        if not response.ok() {
            span.recordError(Error("TransportError", str(response.error)))
            span.setStatus(OtelStatusCode.ERROR, "inventory unreachable")
            span.end()
            return Result.Err(Error("InventoryError", "inventory unreachable", response.error))
        }
        res: HttpResponse = response.unwrap()
        span.setAttribute("http.response.status_code", res.status)
        if res.status >= 500 {
            span.setStatus(OtelStatusCode.ERROR, f"inventory returned {res.status}")
        }
        span.end()
        return Result.Ok(res.body)
    }
}

func handleCheckout(headers: dict[str, str], inventory: InventoryClient) -> int {
    tracer: OtelTracer = Otel.tracer("shop.checkout", "1.0.0")
    parent: OtelSpanContext = Otel.extract(headers)
    baggage: OtelBaggage = Otel.extractBaggage(headers)
    span: OtelSpan = tracer.startSpan("POST /checkout", OtelSpanKind.SERVER, parent, {"http.request.method": "POST", "http.route": "/checkout"})
    status: int = 200
    do {
        reservation: str = inventory.reserve(span, baggage, "A-1")?
        span.addEvent("reserved", {"reservation": reservation})
    } catch err {
        status = 502
        span.setStatus(OtelStatusCode.ERROR, err.message)
    }
    span.setAttribute("http.response.status_code", status)
    span.end()
    return status
}
```

`tracer.startSpanFromHeaders("POST /checkout", headers)` is a shortcut for
the extract-and-start pair, and `span.inject(headers)` writes only the
trace context of a span.

### Metrics

```lammergeier
from @lam/otel import Otel, OtelMeter, OtelCounter, OtelUpDownCounter, OtelHistogram, OtelGauge, OtelObservableResult

class QueueStats {
    func init(self) {
        self.depth: int = 0
    }

    func observe(self, result: OtelObservableResult) {
        result.observe(self.depth, {"queue": "emails"})
    }
}

func instrument(stats: QueueStats) {
    meter: OtelMeter = Otel.meter("mailer", "2.1.0")
    sent: OtelCounter = meter.counter("mailer.sent", "{email}", "Emails sent")
    inFlight: OtelUpDownCounter = meter.upDownCounter("mailer.in_flight", "{email}")
    latency: OtelHistogram = meter.histogram("mailer.send.duration", "ms", "SMTP latency", [5.0, 25.0, 100.0, 500.0, 2000.0])
    pool: OtelGauge = meter.gauge("mailer.pool.size", "{connection}")
    meter.observableGauge("mailer.queue.depth", stats.observe, "{email}")

    inFlight.add(1)
    sent.add(1, {"provider": "ses", "status": "ok"})
    latency.record(42, {"provider": "ses"})
    latency.recordFloat(12.5, {"provider": "ses"})
    pool.record(8)
    inFlight.add(-1)
}
```

Integer methods (`add`, `record`) and float methods (`addFloat`,
`recordFloat`) exist on every instrument; a stream switches to `asDouble`
as soon as one float is recorded. Metrics are exported every
`OTEL_METRIC_EXPORT_INTERVAL` milliseconds, on `forceFlush()` and on
`shutdown()`.

### Logs correlated with traces

```lammergeier
from @lam/otel import Otel, OtelLogger, OtelSeverity, OtelSpan

func charge(span: OtelSpan, amountCents: int) {
    logger: OtelLogger = Otel.logger("payments", "1.0.0")
    logger.info("charging card", {"amount.cents": amountCents}, span.spanContext())
    if amountCents > 100000 {
        logger.warn("large charge", {"amount.cents": amountCents}, span.spanContext())
    }
    # Structured body, explicit severity and an event name.
    logger.emit(OtelSeverity.ERROR, {"code": 402, "reason": "card_declined"}, {"retry": false}, span.spanContext(), 0, "payment.declined")
}
```

`Otel.loggerProvider().setMinSeverity(OtelSeverity.INFO)` drops debug and
trace records before they are processed.

### Testing your instrumentation with the in-memory exporter

```lammergeier
from @lam/otel import OtelTracerProvider, OtelTracer, OtelSpan, OtelSimpleSpanProcessor, OtelInMemorySpanExporter, OtelMeterProvider, OtelMetricReader, OtelInMemoryMetricExporter, OtelMetricData, Otel

func main() {
    spans: OtelInMemorySpanExporter = OtelInMemorySpanExporter()
    traces: OtelTracerProvider = OtelTracerProvider()
    traces.addProcessor(OtelSimpleSpanProcessor(spans))
    Otel.setTracerProvider(traces)

    metrics: OtelInMemoryMetricExporter = OtelInMemoryMetricExporter()
    reader: OtelMetricReader = OtelMetricReader(metrics, 0)    # manual reader
    meters: OtelMeterProvider = OtelMeterProvider()
    meters.addReader(reader)
    Otel.setMeterProvider(meters)

    codeUnderTest()

    print(spans.names())                                    # [lookup]
    lookup: OtelSpan = spans.find("lookup")
    print(lookup.getAttribute("cache.hit"))                 # true
    _ = reader.forceFlush()
    hits: OtelMetricData = metrics.find("cache.hits")
    print(hits.point({"cache": "users"}).intValue)          # 1
}

func codeUnderTest() {
    span: OtelSpan = Otel.tracer("cache").startSpan("lookup")
    span.setAttribute("cache.hit", true)
    Otel.meter("cache").counter("cache.hits").add(1, {"cache": "users"})
    span.end()
}
```

`OtelInMemoryLogExporter` (`finishedRecords()`, `bodies()`) does the same
for logs, and the console exporters (`OtelConsoleSpanExporter`, ...) print
one JSON line per item, or pass each line to a `func(str)` callback.

## API reference

All names are exported from the package root: `from @lam/otel import ...`.
Times are Unix nanoseconds unless the name says otherwise; attribute maps
are `dict[str, any]` whose values may be `str`, `bool`, `int`, `float` or
homogeneous lists of those (`None` values are ignored).

### Setup and globals

**`Otel`** (static facade)

| Method | Description |
|---|---|
| `setup(cfg: OtelConfig = None) -> OtelSdk` | Build all providers from `cfg` (or the environment) and install them and the propagator globally. |
| `shutdown() -> Result[bool]`, `forceFlush() -> Result[bool]` | Shut down / flush the global providers. |
| `tracer(name = "", version = "") -> OtelTracer` | Tracer of the global tracer provider. |
| `meter(name = "", version = "") -> OtelMeter` | Meter of the global meter provider. |
| `logger(name = "", version = "") -> OtelLogger` | Logger of the global logger provider. |
| `tracerProvider()`, `meterProvider()`, `loggerProvider()`, `propagator()` | Current globals (no-op providers and `tracecontext,baggage` until set). |
| `setTracerProvider(p)`, `setMeterProvider(p)`, `setLoggerProvider(p)`, `setPropagator(p)` | Install globals. |
| `inject(headers, context: OtelSpanContext, baggage: OtelBaggage = None)` | Write propagation headers with the global propagator. |
| `extract(headers) -> OtelSpanContext`, `extractBaggage(headers) -> OtelBaggage` | Read incoming propagation headers. |
| `traceId()`, `spanId()`, `idsTrace()`, `idsSpan()` | New random ids (the `ids*` names are kept from `lamotel`). |
| `parsePairs(text) -> dict[str, str]`, `parseHeaders(text)` | Parse `key=value,...` lists. |
| `tracesPayload(spans) -> json`, `metricsPayload(resource, metrics) -> json`, `logsPayload(records) -> json` | OTLP/JSON request bodies. |

**`OtelSdk`**: `config`, `tracerProvider`, `meterProvider`,
`loggerProvider`, `propagator`; `OtelSdk.fromConfig(cfg)`, `tracer(...)`,
`meter(...)`, `logger(...)`, `forceFlush()`, `shutdown()`.

**`OtelConfig`**: `OtelConfig(serviceName = "unknown_service", endpoint =
"http://localhost:4318", headers = "", timeoutMs = 10000)`,
`OtelConfig.fromEnv()`, the fields of the [configuration table](#configuration),
`isReady()`, `tracesUrl()`, `metricsUrl()`, `logsUrl()`, `urlFor(signal)`,
`headersFor(signal)`, `timeoutFor(signal)`, `compressionFor(signal)`,
`exporterFor(signal)` (`signal` is `"traces"`, `"metrics"` or `"logs"`) and
`resource() -> OtelResource`.

**`OtelResource`**: `OtelResource(attributes = {})`, `fromEnv()`,
`sdkDefaults()`, `attributes`, `set(key, value)`, `get(key) -> any`,
`getString(key, fallback = "")`, `has(key)`, `serviceName()`,
`merge(other) -> OtelResource` (other wins), `key()`, `toJson()`.

### Tracing

**`OtelTracerProvider`**: `OtelTracerProvider(resource = None, sampler =
None, limits = None)`, `fromConfig(cfg)`, `fromEnv()`, `noop()`;
`addProcessor(p: OtelSpanProcessor)`, `processorList()`, `tracer(name = "",
version = "") -> OtelTracer` (cached per scope), `forceFlush()`,
`shutdown()`, `isShutdown()`; fields `resource`, `sampler`, `limits`,
`enabled`, `config`.

**`OtelTracer`**: `fromConfig(cfg)`, `fromEnv()`, fields `provider`,
`name`, `version`, and:

| Method | Description |
|---|---|
| `startSpan(name, kind = OtelSpanKind.INTERNAL, parent: OtelSpanContext = None, attributes = {}, links: list[OtelSpanLink] = [], startTimeUnixNano = 0) -> OtelSpan` | Start a span; a valid `parent` joins its trace. |
| `childSpan(parent: OtelSpan, name, kind = INTERNAL, attributes = {}) -> OtelSpan` | Child of a local span. |
| `startSpanFromHeaders(name, headers, kind = SERVER, attributes = {}) -> OtelSpan` | Continue the trace of incoming W3C headers. |
| `withSpan(name, fn: func(OtelSpan), kind = INTERNAL, parent = None)` | Run `fn` inside a span that is always ended; a thrown exception is recorded, sets `ERROR` and is re-raised. |
| `exportSpan(span)`, `exportSpans(spans) -> Result[OtelExportResult]` | Synchronous OTLP export bypassing the processors (needs a provider built from a config). |
| `batch() -> OtelSpanBatch` | Empty batch for manual export. |

**`OtelSpan`**: fields `name`, `kind`, `traceId`, `spanId`, `traceFlags`,
`traceState`, `parentSpanId`, `parentRemote`, `startTimeUnixNano`,
`endTimeUnixNano`, `attributes`, `events`, `links`, `statusCode`,
`statusMessage`, `droppedAttributesCount`, `droppedEventsCount`,
`droppedLinksCount`, `resource`, `scopeName`, `scopeVersion`; methods
`OtelSpan(name, kind = 1, traceId = "", spanId = "")` (stand-alone span),
`spanContext()`, `isRecording()`, `isSampled()`, `isEnded()`,
`setAttribute(key, value)`, `setAttributes(attrs)`, `getAttribute(key)`,
`updateName(name)`, `addEvent(name, attributes = {}, timeUnixNano = 0)`,
`addLink(context, attributes = {})`, `setStatus(code, description = "")`,
`recordException(message, exceptionType = "", stacktrace = "", attributes =
{})`, `recordError(err: Error, attributes = {})`, `fail(message)`,
`setParent(parentSpanId)`, `end(endTimeUnixNano = 0)`, `durationNanos()`,
`durationMs()`, `inject(headers)`, `eventNames()`, `toJson()`.

**`OtelSpanKind`**: `UNSPECIFIED`, `INTERNAL`, `SERVER`, `CLIENT`,
`PRODUCER`, `CONSUMER`; `parse(name)`, `name(kind)`.
**`OtelStatusCode`**: `UNSET`, `OK`, `ERROR`; `parse(name)`, `name(code)`.

**`OtelSpanContext`**: `OtelSpanContext(traceId = "", spanId = "",
traceFlags = 0, traceState = "", remote = false)`, `invalid()`, `isValid()`,
`isSampled()`, `isRemote()`, `traceparent()`.
**`OtelSpanEvent`** (`name`, `timeUnixNano`, `attributes`,
`droppedAttributesCount`, `toJson()`) and **`OtelSpanLink`** (`OtelSpanLink(context,
attributes = {})`, `toJson()`).

**`OtelSpanLimits`**: `OtelSpanLimits(attributeCountLimit = 128,
attributeValueLengthLimit = -1, eventCountLimit = 128, linkCountLimit = 128,
attributePerEventCountLimit = 128, attributePerLinkCountLimit = 128)`,
`fromConfig(cfg)`; `-1` means unlimited.

**`OtelSampler`**: `alwaysOn()`, `alwaysOff()`, `traceIdRatio(ratio)`,
`parentBased(root)` (public delegate fields `remoteParentSampled`,
`remoteParentNotSampled`, `localParentSampled`, `localParentNotSampled`),
`custom(name, fn: func(OtelSpanContext, str, str, int, dict[str, any]) ->
int)`, `fromConfig(name, arg = "")`, `shouldSample(parent, traceId, name,
kind, attributes) -> int`, `description()`.
**`OtelSamplingDecision`**: `DROP`, `RECORD_ONLY`, `RECORD_AND_SAMPLE`.

**Propagation**: **`OtelTraceContext`** — `parseTraceparent(value)`,
`extract(headers)`, `inject(ctx, headers)`, `sanitizeTraceState(value)`,
`traceStateGet(state, key)`, `traceStateSet(state, key, value)`,
`traceStateDelete(state, key)`. **`OtelBaggage`** — `set(key, value,
metadata = "")`, `get(key)`, `getMetadata(key)`, `has(key)`, `remove(key)`,
`keys()`, `size()`, `isEmpty()`, `copy()`, `toHeader()`,
`fromHeader(value)`, `extract(headers)`, `inject(headers)`.
**`OtelPropagator`** — `OtelPropagator(traceContext = true, baggage = true)`,
`parse(names)`, `fromConfig(cfg)`, `fields()`, `inject(headers, ctx, baggage
= None)`, `extract(headers)`, `extractBaggage(headers)`.

**Processors** (implement `OtelSpanProcessor`: `onStart(span)`,
`onEnd(span)`, `forceFlush() -> Result[bool]`, `shutdown() ->
Result[bool]`): `OtelSimpleSpanProcessor(exporter)` and
`OtelBatchSpanProcessor(exporter, maxQueueSize = 2048, scheduleDelayMs =
5000, maxExportBatchSize = 512, exportTimeoutMs = 30000)` with
`fromConfig(exporter, cfg)`, `queued()`, `dropped()`, `exported()`,
`failed()`, `lastError()`.

**Exporters** (implement `OtelSpanExporter`: `export(spans) ->
Result[OtelExportResult]`, `shutdown() -> Result[bool]`):
`OtelOtlpSpanExporter(cfg = None)` (field `transport`),
`OtelInMemorySpanExporter()` (`finishedSpans()`, `count()`, `names()`,
`find(name)`, `reset()`, `exportCalls`), `OtelConsoleSpanExporter(out:
func(str) = None)` (`format(span)`). **`OtelTraceJson.payload(spans)`**
builds the request body. **`OtelSpanBatch`**: `add(span)`, `size()`,
`export(tracer)`, field `spans`.

### Metrics

**`OtelMeterProvider`**: `OtelMeterProvider(resource = None)`,
`fromConfig(cfg)`, `fromEnv()`, `noop()`; `addReader(reader)`,
`meter(name = "", version = "") -> OtelMeter`, `collect() ->
list[OtelMetricData]`, `forceFlush()`, `shutdown()`, `isShutdown()`; fields
`resource`, `startTimeUnixNano`, `cardinalityLimit` (default 2000),
`enabled`.

**`OtelMeter`**: `counter(name, unit = "", description = "") ->
OtelCounter`, `upDownCounter(...) -> OtelUpDownCounter`, `gauge(...) ->
OtelGauge`, `histogram(name, unit = "", description = "", boundaries:
list[float] = []) -> OtelHistogram`, `observableGauge(name, callback:
func(OtelObservableResult), unit = "", description = "")`,
`observableCounter(...)`, `observableUpDownCounter(...)` (return
`OtelObservableInstrument`), `collect(nowUnixNano)`, `validName(name)`,
`DEFAULT_BOUNDS`.

**Instruments** (all derive from `OtelInstrument`: `name`, `unit`,
`description`, `kind`, `monotonic`, `collect(nowUnixNano)`):
`OtelCounter.add(value: int, attributes = {})` / `addFloat(value: float,
...)`, `OtelUpDownCounter.add` / `addFloat`, `OtelGauge.record(value: int,
...)` / `recordFloat`, `OtelHistogram.record(value: int, ...)` /
`recordFloat` / `boundaries()`, `OtelObservableInstrument.setCallback(fn)`.
**`OtelObservableResult`**: `observe(value: int, attributes = {})`,
`observeFloat(value: float, attributes = {})`, `size()`.

**Data**: **`OtelMetricData`** — `name`, `kind` (`"sum"`, `"gauge"`,
`"histogram"`), `unit`, `description`, `monotonic`, `temporality`,
`scopeName`, `scopeVersion`, `points`, `point(attributes = {})`, `toJson()`.
**`OtelMetricPoint`** — `attributes`, `startTimeUnixNano`, `timeUnixNano`,
`isDouble`, `intValue`, `doubleValue`, `value()`, `count`, `sum`, `min`,
`max`, `bucketCounts`, `explicitBounds`, `copy()`, `toJson(kind)`.
**`OtelMetricJson.payload(resource, metrics)`** builds the request body.

**`OtelMetricReader`**: `OtelMetricReader(exporter, intervalMs = 60000,
timeoutMs = 30000)` (`intervalMs <= 0` = manual), `fromConfig(exporter,
cfg)`, `collect()`, `forceFlush()`, `shutdown()`, `exports()`,
`errorMessage()`.

**Exporters** (implement `OtelMetricExporter`: `export(resource, metrics)
-> Result[OtelExportResult]`, `shutdown()`): `OtelOtlpMetricExporter(cfg =
None)`, `OtelInMemoryMetricExporter()` (`latest()`, `find(name)`,
`exportCount()`, `reset()`, `batches`), `OtelConsoleMetricExporter(out =
None)`.

### Logs

**`OtelLoggerProvider`**: `OtelLoggerProvider(resource = None,
attributeCountLimit = 128, attributeValueLengthLimit = -1)`,
`fromConfig(cfg)`, `fromEnv()`, `noop()`; `addProcessor(p:
OtelLogProcessor)`, `setMinSeverity(severity)`, `logger(name = "", version
= "") -> OtelLogger`, `processorList()`, `forceFlush()`, `shutdown()`,
`isShutdown()`.

**`OtelLogger`**: `emit(severity, body: any, attributes = {}, context:
OtelSpanContext = None, timeUnixNano = 0, eventName = "")`, `trace`,
`debug`, `info`, `warn`, `error`, `fatal` (`(message, attributes = {},
context = None)`), `enabled(severity = 0)`.

**`OtelSeverity`**: `TRACE` (1), `DEBUG` (5), `INFO` (9), `WARN` (13),
`ERROR` (17), `FATAL` (21), `UNSPECIFIED`; `text(severity)`, `parse(name)`.
**`OtelLogRecord`**: `timeUnixNano`, `observedTimeUnixNano`,
`severityNumber`, `severityText`, `body`, `attributes`,
`droppedAttributesCount`, `eventName`, `traceId`, `spanId`, `traceFlags`,
`resource`, `scopeName`, `scopeVersion`, `bodyString()`, `toJson()`.
**`OtelLogJson.payload(records)`** builds the request body.

**Processors** (implement `OtelLogProcessor`: `onEmit(record)`,
`forceFlush()`, `shutdown()`): `OtelSimpleLogProcessor(exporter)`,
`OtelBatchLogProcessor(exporter, maxQueueSize = 2048, scheduleDelayMs =
1000, maxExportBatchSize = 512, exportTimeoutMs = 30000)` with
`fromConfig`, `queued()`, `dropped()`, `exported()`, `failed()`.
**Exporters** (implement `OtelLogExporter`): `OtelOtlpLogExporter(cfg =
None)`, `OtelInMemoryLogExporter()` (`finishedRecords()`, `count()`,
`bodies()`, `reset()`), `OtelConsoleLogExporter(out = None)`.

### Transport and utilities

**`OtelExportResult`**: `status` (HTTP status, `0` for local exporters),
`body`, `attempts`, `items`, `rejected`, `errorMessage`, `ok()`,
`partial()`.

**`OtelOtlpHttp`**: `OtelOtlpHttp(url, headers = {}, timeoutMs = 10000,
compression = "none", maxAttempts = 5, initialBackoffMs = 1000,
maxBackoffMs = 5000)`, `forSignal(cfg, signal)`, `retryable(status)`,
`backoffMs(attempt, retryAfter = "")`, `send(payload: json, items = 0) ->
Result[OtelExportResult]`.

**`OtelUtil`**: id helpers (`traceId`, `spanId`, `randomHex`, `isZeroHex`,
`isLowerHex`), parsing (`parsePairs`, `percentDecode`, `percentEncode`,
`parseFloatOr`, `parseHex2`, `hex2`, `env*`), headers (`header`,
`setHeader`), attributes (`truncate`, `setLimited`, `attributesJson`,
`anyValueJson`, `bytesValueJson`, `attributeKey`, `copyAttributes`,
`sortedKeys`), `gzip`, `ratioSampled`, `validTraceStateMember`,
`validToken`. **`OtelWorker`** (background ticker) and
**`OtelBatchQueue[T]`** (bounded batching queue) are the building blocks of
the processors and readers and can be reused by custom components.

**Error kinds** in `Result.Err(Error(...))`: `OtelConfigError` (no
endpoint), `OtelExportError` (HTTP failure or rejection; the cause is the
final `OtelExportResult` or the transport error), `OtelTimeoutError`
(export exceeded the processor/reader timeout), `OtelShutdownError`
(exporter already shut down), `OtelCompressionError`.

## Behaviour notes

- **Protocol.** Only OTLP/HTTP with JSON encoding is implemented (`http/json`).
  Collectors accept it on the standard port 4318. IDs are lowercase hex,
  enums are integers and 64-bit integers are decimal strings, as the OTLP
  JSON mapping requires. Payloads were verified against the OpenTelemetry
  Collector 0.111.
- **Shut down before exiting.** Batch processors and periodic readers export
  from background goroutines; call `Otel.shutdown()` / `sdk.shutdown()`
  (or the provider's `shutdown()`) so buffered telemetry is flushed. Shutdown
  is idempotent and later spans, metrics and logs are ignored.
- **Failures never crash the application.** Export errors are returned as
  `Result` values from `forceFlush()`/`shutdown()` and counted by the
  processors (`failed()`, `lastError()`); panics in exporters and
  observable callbacks are recovered.
- **Retries.** `429`, `500`, `502`, `503` and `504` responses and transport
  errors are retried up to `retryMaxAttempts` times with exponential backoff
  (`retryInitialBackoffMs` doubling up to `retryMaxBackoffMs`; a
  `Retry-After` header in seconds wins, still capped). Other statuses fail
  immediately. A `partialSuccess` response is a success whose
  `OtelExportResult.rejected`/`errorMessage` report the rejected items.
- **Sampling.** The default sampler is `parentbased_always_on`. Dropped
  spans still carry a valid context, so propagation keeps working;
  `RECORD_ONLY` spans are processed but not exported. The trace-id ratio
  decision is deterministic per trace id.
- **Limits.** Attributes, events and links beyond the configured limits are
  dropped and counted in the `dropped*Count` fields of the exported data;
  string values (and strings in lists) are truncated to the value length
  limit.
- **Metrics** use cumulative temporality from the provider start time.
  Counters ignore negative increments. A histogram bucket `i` counts values
  `<= boundaries[i]` (and greater than the previous bound). Each instrument
  keeps at most `cardinalityLimit` attribute sets; the rest are aggregated
  into an `otel.metric.overflow=true` series. Instruments with an invalid
  name ignore their measurements.
- **Concurrency.** Spans, instruments, loggers, providers, processors and
  exporters are safe to use from several goroutines.
- **Context.** Lam has no implicit context propagation: pass parents
  explicitly (`startSpan(..., parent=span.spanContext())`, `childSpan`,
  the `context` argument of the logger methods). A
  `lamcontext.Context` can carry a span (`Context.simple().valued("span",
  span)`) when you need to thread it through call chains.
- **Compiler notes (lamc 2.1).** The whole package lives in `__init__.lam`
  because `json` return types of functions re-exported from package
  submodules are lost by the semantic checker; in your own code avoid
  naming a local variable `log` (`log.info(...)` is lowered as a Go package
  call).

## Testing

```bash
python3 tests/run_lamotel_tests.py --verbose        # or: lamc lib run test
python3 tests/run_lamotel_tests.py -j 4 -k metrics  # parallel, filtered
```

The runner uses the `lamc` on `PATH` (2.1.0 or newer), stages the package
into a temporary `extlibs/@lam/otel` (the installed-package boundary),
compiles every `tests/test_*.lam` file and compares its output with the
`# expect:` lines. Export paths are tested against ephemeral local
collectors (`tests/otelmock.lam`) that record requests and assert the OTLP
JSON shape, headers, retries and compression. Ambient `OTEL_*` variables are
removed from the offline tests' environment.

The live test exports traces, metrics and logs to a real collector:

```bash
docker run --rm -p 4318:4318 otel/opentelemetry-collector:0.111.0 &
LAMOTEL_LIVE_TESTS=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
    python3 tests/run_lamotel_tests.py --live --verbose
```

Without `LAMOTEL_LIVE_TESTS=1` the live test is reported as skipped.

## Links

- Lammergeier language: <https://github.com/thallium-solutions/lammergeier-lang>
- Documentation: <https://lammergeier-lang.dev>
- OpenTelemetry specification: <https://opentelemetry.io/docs/specs/otel/>

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
