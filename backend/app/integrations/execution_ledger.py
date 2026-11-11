class UsageDetails(TypedDict):
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    reasoning_tokens: int | None
    cache_write_tokens: int | None


def usage_details(raw: object) -> UsageDetails:
    usage = raw if isinstance(raw, dict) else {}
    input_tokens = _count(usage.get("input_tokens", usage.get("prompt_tokens")))
    output_tokens = _count(usage.get("output_tokens", usage.get("completion_tokens")))
    inputs = usage.get("input_tokens_details", usage.get("prompt_tokens_details"))
    outputs = usage.get("output_tokens_details", usage.get("completion_tokens_details"))
    cached = _count(inputs.get("cached_tokens")) if isinstance(inputs, dict) else None
    reasoning = _count(outputs.get("reasoning_tokens")) if isinstance(outputs, dict) else None
    cache_write = _count(inputs.get("cache_write_tokens")) if isinstance(inputs, dict) else None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached
        if input_tokens is not None and (cached or 0) <= input_tokens
        else None,
        "reasoning_tokens": reasoning
        if output_tokens is not None and (reasoning or 0) <= output_tokens
        else None,
        "cache_write_tokens": cache_write
        if cache_write is not None
        else _count(usage.get("cache_write_tokens")),
    }


@dataclass
class Observation:
    record: CallRecord

    def response(self, envelope: Mapping[str, object]) -> None:
        model = envelope.get("model")
        self.record = replace(
            self.record,
            actual_model=model if isinstance(model, str) else None,
            **usage_details(envelope.get("usage")),
        )

    def complete(self, error_code: str | None = None) -> None:
        self.record = replace(
            self.record, status="failed" if error_code else "succeeded", error_code=error_code
        )


@dataclass(frozen=True)
class _Scope:
    ledger: ExecutionLedger
    run_id: str
    entrypoint: str
    provider: str
    metadata: dict[str, str | int | bool | None]
    parent_call_id: str | None = None
    ignore_io_errors: bool = False


_SCOPE: ContextVar[_Scope | None] = ContextVar("execution_ledger_scope", default=None)


@contextmanager
def execution_scope(
    ledger: ExecutionLedger,
    *,
    run_id: str,
    entrypoint: str,
    provider: str = "openai_compatible",
    metadata: dict[str, str | int | bool | None] | None = None,
    ignore_io_errors: bool = False,
) -> Iterator[None]:
    # 평가 실행은 기본 strict다. 선택 관측인 실제 서비스 진입점만 I/O 격리를 켠다.
    scope = _Scope(
        ledger,
        run_id,
        entrypoint,
        provider,
        dict(metadata or {}),
        ignore_io_errors=ignore_io_errors,
    )
    # 잘못된 관측 설정은 유료 실행 전에 검증한다.
    CallRecord(
        "scope-validation",
        run_id,
        entrypoint,
        "scope",
        "stage",
        0,
        provider=provider,
        metadata=scope.metadata,
    )
    token = _SCOPE.set(scope)
    try:
        yield
    finally:
        _SCOPE.reset(token)


def _ignore_io_failure(
    scope: _Scope, error: OSError | sqlite3.OperationalError, *, operation: str, phase: str
) -> bool:
    if not scope.ignore_io_errors:
        return False
    # 파일 경로·SQL·사용자 원문은 남기지 않는다. 누락 관측을 성공·사용량0으로 만들지 않는다.
    _logger.warning(
        "ai_execution_ledger_io_failed",
        extra={"phase": phase, "operation": operation, "exception_type": type(error).__name__},
    )
    return True


async def _finish_observation(scope: _Scope, record: CallRecord) -> None:
    try:
        await asyncio.to_thread(scope.ledger.finish, record)
    except (OSError, sqlite3.OperationalError) as error:
        # ProgrammingError·IntegrityError 등 잘못된 장부 사용은 서비스에서도 숨기지 않는다.
        if not _ignore_io_failure(scope, error, operation=record.operation, phase="finish"):
            raise


@asynccontextmanager
async def observe_call(
    operation: str,
    *,
    kind: str = "generation",
    requested_model: str | None = None,
    request_sha256: str | None = None,
    metadata: dict[str, str | int | bool | None] | None = None,
) -> AsyncIterator[Observation | None]:
    scope = _SCOPE.get()
    if scope is None:
        yield None
        return
    started = time.perf_counter()
    observed = Observation(
        CallRecord(
            str(uuid4()),
            scope.run_id,
            scope.entrypoint,
            operation,
            kind,
            time.time(),
            provider=scope.provider,
            requested_model=requested_model,
            request_sha256=request_sha256,
            metadata={**scope.metadata, **(metadata or {})},
            parent_call_id=scope.parent_call_id,
        )
    )
    try:
        await asyncio.to_thread(scope.ledger.start, observed.record)
    except (OSError, sqlite3.OperationalError) as error:
        if not _ignore_io_failure(scope, error, operation=operation, phase="start"):
            raise
        # 시작 기록이 없으면 자식도 같은 실패 장부에 쓰지 않는다. 호출 종료 뒤 부모는 복원한다.
        token = _SCOPE.set(None)
        try:
            yield None
        finally:
            _SCOPE.reset(token)
        return
    # 비동기 자식 작업에는 현재 단계의 부모 관계만 전파하고 형제 단계와 섞지 않는다.
    token = _SCOPE.set(replace(scope, parent_call_id=observed.record.call_id))
    try:
        yield observed
    except BaseException as error:
        observed.record = replace(
            observed.record,
            status="cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
            error_code=type(error).__name__,
        )
        raise
    finally:
        _SCOPE.reset(token)
        if observed.record.status == "started":
            observed.complete()
        observed.record = replace(observed.record, elapsed_seconds=time.perf_counter() - started)
        pending = asyncio.create_task(_finish_observation(scope, observed.record))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            raise


@dataclass(frozen=True)
class PriceProfile:
    provider: str
    model: str
    input_per_million: str
    output_per_million: str
    source: str
    as_of: str
    cached_input_per_million: str | None = None
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.currency != "USD" or not self.source.strip() or not self.as_of.strip():
            raise ValueError("explicit USD pricing source and date are required")
        if not isinstance(self.input_per_million, str) or not isinstance(
            self.output_per_million, str
        ):
            raise ValueError("prices must be explicit decimal strings")
        for value in (
            self.input_per_million,
            self.output_per_million,
            self.cached_input_per_million,
        ):
            if value is not None:
                try:
                    if (
                        not isinstance(value, str)
                        or not Decimal(value).is_finite()
                        or Decimal(value) < 0
                    ):
                        raise ValueError("invalid price")
                except InvalidOperation:
                    raise ValueError("invalid price") from None

    def estimate(self, record: CallRecord) -> Decimal | None:
        if record.cache_write_tokens:
            # 공급자별 cache-write의 입력 포함 여부·별도 단가를 추정하지 않는다.
            return None
        if record.input_tokens is None or (
            record.kind != "embedding" and record.output_tokens is None
        ):
            return None
        regular = Decimal(self.input_per_million)
        cached = (
            Decimal(self.cached_input_per_million)
            if self.cached_input_per_million is not None
            else regular
        )
        if cached != regular and record.cached_input_tokens is None:
            return None
        cached_count = record.cached_input_tokens or 0
        return (
            (record.input_tokens - cached_count) * regular
            + cached_count * cached
            + (record.output_tokens or 0) * Decimal(self.output_per_million)
        ) / Decimal(1_000_000)


def summarize(
    records: Sequence[CallRecord], *, prices: Sequence[PriceProfile] = ()
) -> dict[str, Any]:
    if len({item.call_id for item in records}) != len(records):
        raise ValueError("duplicate physical call")
    price_map = {(price.provider, price.model): price for price in prices}
    if len(price_map) != len(prices):
        raise ValueError("duplicate price profile")
    calls = [item for item in records if item.kind != "stage"]
    intervals = sorted(
        (item.started_at, item.started_at + item.elapsed_seconds)
        for item in calls
        if item.elapsed_seconds is not None
    )
    active = 0.0
    end = 0.0
    for left, right in intervals:
        active += max(0.0, right - max(left, end))
        end = max(end, right)
    durations = sorted(item.elapsed_seconds for item in calls if item.elapsed_seconds is not None)
    estimates: list[Decimal] = []
    sources: set[str] = set()
    for item in calls:
        price = price_map.get((item.provider, item.actual_model or ""))
        amount = price.estimate(item) if price is not None else None
        if amount is not None:
            estimates.append(amount)
            assert price is not None
            sources.add(price.source)
    unpriced = len(calls) - len(estimates)
    known_cost = sum(estimates, Decimal(0))
    return {
        "schema_version": "execution-metrics.v1",
        "physical_calls": len(calls),
        "stage_count": len(records) - len(calls),
        "statuses": dict(Counter(item.status for item in calls)),
        "by_operation": dict(Counter(item.operation for item in calls)),
        "outcome_scopes": dict(
            Counter(str(item.metadata.get("outcome_scope", "unspecified")) for item in calls)
        ),
        "known_input_tokens": sum(item.input_tokens or 0 for item in calls),
        "known_output_tokens": sum(item.output_tokens or 0 for item in calls),
        "unknown_usage_calls": sum(
            item.input_tokens is None or (item.kind != "embedding" and item.output_tokens is None)
            for item in calls
        ),
        "unfinished_calls": sum(item.status == "started" for item in calls),
        "unknown_duration_calls": len(calls) - len(durations),
        "duration_sum_seconds": sum(durations),
        "active_wall_seconds": active,
        "observed_window_seconds": max((right for _, right in intervals), default=0)
        - min((left for left, _ in intervals), default=0),
        "duration_p50_seconds": durations[math.ceil(len(durations) * 0.5) - 1]
        if durations
        else None,
        "duration_p95_seconds": durations[math.ceil(len(durations) * 0.95) - 1]
        if durations
        else None,
        "estimated_cost_usd": float(known_cost) if calls and not unpriced else None,
        "known_estimated_cost_usd": float(known_cost) if estimates else None,
        "unpriced_calls": unpriced,
        "cost_status": "estimated" if calls and not unpriced else "incomplete",
        "actual_billed_cost_usd": None,
        "pricing_sources": sorted(sources),
    }


def import_http_records(
    admissions: Sequence[dict[str, Any]],
    receipts: Sequence[dict[str, Any]],
    *,
    run_id: str,
    entrypoint: str,
) -> list[CallRecord]:
    def identity(row: dict[str, Any]) -> str:
        return json.dumps(
            [run_id, row["kind"], row["label"], row["request_sha256"], row["dispatched_at"]],
            separators=(",", ":"),
        )

    starts = {identity(row): row for row in admissions}
    if len(starts) != len(admissions):
        raise ValueError("duplicate admission identity")
    finishes: dict[str, dict[str, Any]] = {}
    for row in receipts:
        key = identity(row)
        if key not in starts:
            raise ValueError("unmatched receipt")
        if key in finishes and finishes[key] != row:
            raise ValueError("conflicting receipt")
        finishes[key] = row
    records = []
    for key, admission in starts.items():
        receipt = finishes.get(key)
        embedding = admission["kind"] == "embeddings"
        metadata: dict[str, str | int | bool | None] = {
            "cohort": admission["label"],
            "source_kind": "historical_http",
            "request_bytes": admission.get("request_bytes"),
            "stream": admission.get("stream"),
            "outcome_scope": "http_transport_only",
        }
        record = CallRecord(
            hashlib.sha256(key.encode()).hexdigest(),
            run_id,
            entrypoint,
            "embedding"
            if embedding
            else "judge"
            if admission["label"] == "judge"
            else "repository_generation",
            "embedding" if embedding else "generation",
            admission["dispatched_at"],
            provider="elice_mlapi",
            requested_model=admission["requested_model"],
            request_sha256=admission["request_sha256"],
            metadata=metadata,
        )
        if receipt is not None:
            status = receipt.get("status_code")
            record = replace(
                record,
                status="succeeded" if type(status) is int and 200 <= status < 300 else "failed",
                elapsed_seconds=receipt.get("elapsed_seconds"),
                actual_model=receipt.get("actual_model"),
                error_code=receipt.get("transport_error"),
                metadata={
                    **metadata,
                    "status_code": status,
                    "response_bytes": receipt.get("response_bytes"),
                },
                **usage_details(receipt.get("usage")),
            )
        records.append(record)
    return records
