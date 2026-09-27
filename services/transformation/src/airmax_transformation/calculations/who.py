from ..pipeline import PreparedReadings, prepare_readings
from ..transformations.validation import iso, parse_time
from .input import (
    CalculationContext,
    CalculationPlan,
    input_digest,
    records,
    retained_history_covers,
    select_objects,
)
from .result_validation import validate_result
from .who_aggregation import aggregate_period

NAME = "who"
LOOKBACK_HOURS = 24
NON_OZONE_WINDOW_HOURS = LOOKBACK_HOURS
OZONE_WINDOW_HOURS = 8


def plan(context: CalculationContext) -> CalculationPlan:
    raw_objects = select_objects(context.raw_objects, NON_OZONE_WINDOW_HOURS)
    digest = input_digest(raw_objects)
    return CalculationPlan(
        raw_objects=raw_objects,
        input_digest=digest,
        recalculate=_is_due(context.previous_result, digest, context.generated_at),
    )


def _is_due(previous_result, input_digest, generated_at):
    previous_who = (previous_result or {}).get("who_24h", {})
    if previous_who.get("input_digest") == input_digest:
        return False

    previous_generated_at = previous_who.get("generated_at")
    if previous_generated_at is None:
        return True

    previous_hour = parse_time(previous_generated_at).replace(
        minute=0, second=0, microsecond=0
    )
    current_hour = generated_at.replace(minute=0, second=0, microsecond=0)
    return previous_hour < current_hour


def validate(result):
    for name in ("who_24h", "who_8h"):
        if name in result:
            validate_result(result[name], name)


def calculate(store, context: CalculationContext, plan: CalculationPlan, workdir):
    if not plan.recalculate:
        return _reuse_previous(context.previous_result)

    prepared_24h, cities_24h = _calculate_period(
        store,
        plan.raw_objects,
        workdir / "non_ozone",
        NON_OZONE_WINDOW_HOURS,
    )

    ozone_objects = select_objects(plan.raw_objects, OZONE_WINDOW_HOURS)
    prepared_8h, cities_8h = _calculate_period(
        store,
        ozone_objects,
        workdir / "ozone",
        OZONE_WINDOW_HOURS,
    )

    history_24h_complete = _retention_covers_period(
        context.previous_result,
        "who_24h",
        plan.raw_objects,
        prepared_24h.window["start"],
    )
    history_8h_complete = _retention_covers_period(
        context.previous_result,
        "who_8h",
        ozone_objects,
        prepared_8h.window["start"],
    )
    non_ozone_cities = [city for city in cities_24h if city["pollutant"] != "o3"]
    ozone_cities = [city for city in cities_8h if city["pollutant"] == "o3"]

    return {
        "who_24h": _period_result(
            generated_at=context.generated_at,
            prepared=prepared_24h,
            hours=NON_OZONE_WINDOW_HOURS,
            history_complete=history_24h_complete,
            cities=non_ozone_cities,
            input_digest=plan.input_digest,
        ),
        "who_8h": _period_result(
            generated_at=context.generated_at,
            prepared=prepared_8h,
            hours=OZONE_WINDOW_HOURS,
            history_complete=history_8h_complete,
            cities=ozone_cities,
        ),
    }


def _calculate_period(store, raw_objects, workdir, hours):
    workdir.mkdir(parents=True)
    prepared = prepare_readings(records(store, raw_objects), workdir, hours)
    cities = aggregate_period(prepared.readings, prepared.window["start"], hours)
    return prepared, cities


def _reuse_previous(previous_result):
    if not previous_result or not previous_result.get("who_24h"):
        return {}
    comparisons = {"who_24h": previous_result["who_24h"]}
    if previous_result.get("who_8h"):
        comparisons["who_8h"] = previous_result["who_8h"]
    return comparisons


def _retention_covers_period(previous_result, period_name, raw_objects, window_start):
    if previous_result:
        previous_period = previous_result.get(period_name)
        if previous_period:
            previous_window = previous_period.get("window")
            if previous_window and previous_window.get("history_complete"):
                return True

    if window_start is None:
        return False

    return retained_history_covers(raw_objects, window_start)


def _period_result(
    generated_at,
    prepared: PreparedReadings,
    hours,
    history_complete,
    cities,
    input_digest=None,
):
    result = {
        "generated_at": iso(generated_at),
        "window": {
            "end_t": iso(prepared.window["end"]),
            "start": iso(prepared.window["start"]),
            "hours": hours,
            "history_complete": history_complete,
        },
        "cities": cities,
    }
    if input_digest is not None:
        result["input_digest"] = input_digest
    return result
