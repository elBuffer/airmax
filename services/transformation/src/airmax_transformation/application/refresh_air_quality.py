import tempfile
from datetime import timedelta
from pathlib import Path
from time import monotonic

from ..calculations import current, who
from ..calculations.input import CalculationContext
from ..logging import log
from ..transformations.validation import parse_time

RAW_KEY_PREFIX = "raw/"
INVALID_RAW_KEY_PREFIX = f"{RAW_KEY_PREFIX}invalid/"
CALCULATIONS = (current, who)
LONGEST_LOOKBACK_HOURS = max(calculation.LOOKBACK_HOURS for calculation in CALCULATIONS)


def _list_candidate_raw_objects(store, previous_result):
    previous_end = None
    if previous_result is not None:
        previous_end = previous_result.get("window", {}).get("end_t")
    start = (
        parse_time(previous_end) - timedelta(hours=LONGEST_LOOKBACK_HOURS + 1)
        if previous_end
        else None
    )
    objects = store.raw_objects(
        RAW_KEY_PREFIX,
        start_after=f"{RAW_KEY_PREFIX}{start:%Y/%m/%d/%H}/" if start else "",
        stop_at=INVALID_RAW_KEY_PREFIX,
    )
    return sorted(objects, key=lambda item: item.modified)


def _can_reuse_previous_result(plans):
    for plan in plans.values():
        if plan.recalculate:
            return False
    return True


def _calculate_result(store, context, plans, workdir):
    result = {}
    for calculation, plan in plans.items():
        result.update(
            calculation.calculate(store, context, plan, workdir / calculation.NAME)
        )
    return result


def _validate_result(result):
    for calculation in CALCULATIONS:
        calculation.validate(result)


def _publish_empty_result(store, previous_result, etag, generated_at):
    result = current.empty_result(generated_at)
    if (
        previous_result
        and previous_result.get("input_digest") == result["input_digest"]
    ):
        return {"status": "unchanged"}
    _validate_result(result)
    latest_json_was_published = _try_publish_latest_json(store, result, etag)
    if not latest_json_was_published:
        return {"status": "superseded"}
    return {"status": "written", "result": result}


def _source_is_at_least_as_new(published_result, candidate_result):
    published_end = published_result.get("window", {}).get("end_t")
    candidate_end = candidate_result.get("window", {}).get("end_t")

    if candidate_end is None:
        return True
    if published_end is None:
        return False
    return parse_time(published_end) >= parse_time(candidate_end)


def _try_publish_latest_json(store, result, etag):
    while not store.write_result(result, etag):
        published_result, etag = store.read_result()
        if published_result and _source_is_at_least_as_new(published_result, result):
            return False
    return True


def refresh_air_quality(store, generated_at):
    started = monotonic()
    previous_result, etag = store.read_result()
    raw_objects = _list_candidate_raw_objects(store, previous_result)
    if not raw_objects:
        return _publish_empty_result(store, previous_result, etag, generated_at)

    context = CalculationContext(generated_at, previous_result, raw_objects)
    plans = {calculation: calculation.plan(context) for calculation in CALCULATIONS}
    if _can_reuse_previous_result(plans):
        log("input_unchanged", listed=len(raw_objects))
        return {"status": "unchanged"}

    with tempfile.TemporaryDirectory() as directory:
        workdir = Path(directory)
        result = _calculate_result(store, context, plans, workdir)
        _validate_result(result)
        latest_json_was_published = _try_publish_latest_json(store, result, etag)
        if not latest_json_was_published:
            return {"status": "superseded"}

    log(
        "calculation_complete",
        end_t=result["window"]["end_t"],
        input_digest=result["input_digest"],
        listed=len(raw_objects),
        recalculated=[
            calculation.NAME for calculation, plan in plans.items() if plan.recalculate
        ],
        seconds=round(monotonic() - started, 3),
    )
    return {"status": "written", "result": result}
