"""Engineering estimates from observed data; no fabricated failure probabilities."""

import math
from datetime import datetime, timezone, timedelta
from statistics import mean, median
from hospital import aware


def linear_fit(points):
    if len(points) < 3:
        return None
    xbar, ybar = mean(x for x, _ in points), mean(y for _, y in points)
    xx = sum((x - xbar) ** 2 for x, _ in points)
    if xx <= 1e-9:
        return None
    slope = sum((x - xbar) * (y - ybar) for x, y in points) / xx
    intercept = ybar - slope * xbar
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    yy = sum((y - ybar) ** 2 for _, y in points)
    return {
        "slope": slope,
        "intercept": intercept,
        "r_squared": max(0, 1 - residual / yy) if yy > 1e-9 else 1,
        "residual_std": math.sqrt(residual / max(1, len(points) - 2)),
    }


def asset_health(device, settings, observations):
    hours = device["runtime_hours"]
    remaining = max(0, device["design_life_hours"] - hours)
    threshold = settings.get("minimum_performance_percent")
    readings = sorted(observations, key=lambda r: (r["runtime_hours"], r["at"]))
    # A service changes the degradation regime. Do not extrapolate across a repair.
    service_at = (device.get("service_history") or [{}])[-1].get("at")
    segment = [
        r for r in readings if not service_at or aware(r["at"]) >= aware(service_at)
    ]
    points = [(r["runtime_hours"], r["performance_percent"]) for r in segment[-40:]]
    fit = linear_fit(points) if len({x for x, _ in points}) >= 5 else None
    performance = (
        readings[-1]["performance_percent"]
        if readings
        else device.get("inspection_efficiency_percent")
    )
    if service_at and (not readings or aware(service_at) > aware(readings[-1]["at"])):
        performance = device.get("inspection_efficiency_percent")
    projected = None
    if threshold is not None and performance is not None and performance <= threshold:
        projected = 0.0
    elif (
        fit
        and threshold is not None
        and fit["slope"] < -1e-6
        and fit["r_squared"] >= 0.6
    ):
        projected = max(0, (threshold - fit["intercept"]) / fit["slope"] - hours)
    calendar_left = None
    if settings.get("retire_on"):
        calendar_left = (
            aware(settings["retire_on"]) - datetime.now(timezone.utc)
        ).total_seconds() / 86400
    due = performance is not None and threshold is not None and performance < threshold
    return {
        "measured_performance_percent": performance,
        "minimum_performance_percent": threshold,
        "performance_below_limit": due,
        "calendar_life_days": calendar_left,
        "calendar_expired": calendar_left is not None and calendar_left <= 0,
        "life_remaining_hours": remaining,
        "performance_rul_hours": projected,
        "limiting_life_hours": (
            min(remaining, projected) if projected is not None else remaining
        ),
        "life_x_performance_percent": (
            remaining / device["design_life_hours"] * performance
            if performance is not None
            else None
        ),
        "trend": fit,
        "trend_samples": len(points),
        "inspection_count": len(readings),
        "replacement_cost_vnd": settings.get("replacement_cost_vnd", 0),
        "method": "OLS on last service segment, >=5 distinct runtimes, R²>=0.6. Conditional extrapolation, not a failure date or safety certificate.",
        "history": readings[-40:],
    }


def thermal_observe(data, room, now, source, fresh, sample_at=None):
    traits = data.setdefault("traits", {})
    key = source + ":" + room["id"]
    t = traits.setdefault(key, {"rates": {}, "samples": 0})
    stamp = aware(sample_at) if sample_at else now
    prev = t.get("previous")
    if not fresh:
        return
    if prev and (stamp - aware(prev["at"])).total_seconds() > 300:
        t.update(rates={}, samples=0)
        prev = None
    if prev and stamp > aware(prev["at"]):
        elapsed = (stamp - aware(prev["at"])).total_seconds()
        if (
            0.2 <= elapsed <= 60
            and room["airflow_m3h"] >= 0.5 * room["max_airflow_m3h"]
        ):
            for field, up, down, limit in (
                ("temp_c", "heating", "cooling", 2),
                ("humidity", "humidifying", "drying", 10),
            ):
                delta = room[field] - prev[field]
                rate = abs(delta) * 60 / elapsed
                if 0.002 < rate < limit:
                    name = up if delta > 0 else down
                    values = t["rates"].setdefault(name, [])
                    values.append(rate)
                    del values[:-120]
                    t["samples"] += 1
    if not prev or stamp > aware(prev["at"]):
        t["previous"] = {
            "at": stamp.isoformat(),
            "temp_c": room["temp_c"],
            "humidity": room["humidity"],
        }


def thermal_forecast(data, room, now, source, target_temp, target_rh, fresh=True):
    t = data.get("traits", {}).get(source + ":" + room["id"], {})
    recent = bool(
        t.get("previous")
        and 0 <= (now - aware(t["previous"]["at"])).total_seconds() < 300
    )
    dims = []
    for field, target, tolerance, up, down in (
        ("temp_c", target_temp, 1.5, "heating", "cooling"),
        ("humidity", target_rh, 5, "humidifying", "drying"),
    ):
        gap = max(0, abs(room[field] - target) - tolerance)
        direction = up if room[field] < target else down
        rates = sorted(t.get("rates", {}).get(direction, []))
        eligible = fresh and recent and len(rates) >= 10
        eta = gap / median(rates) if eligible and gap else (0 if gap == 0 else None)
        interval = (
            [
                gap / rates[min(len(rates) - 1, int(len(rates) * 0.8))],
                gap / rates[int(len(rates) * 0.2)],
            ]
            if gap and eligible
            else ([0, 0] if gap == 0 else None)
        )
        dims.append(
            {
                "dimension": field,
                "direction": direction,
                "samples": len(rates),
                "eta_minutes": eta,
                "range_minutes": interval,
            }
        )
    known = all(d["eta_minutes"] is not None for d in dims)
    eta = max(d["eta_minutes"] for d in dims) if known else None
    upper = max(d["range_minutes"][1] for d in dims) if known else None
    rule_lead = min(
        32,
        max(12, 10 + max(0, room["temp_c"] - target_temp) * 3 + room["area_m2"] / 55),
    )
    lead = min(90, max(rule_lead, (upper + 5) if upper is not None else 30))
    return {
        "source": source,
        "dimensions": dims,
        "eligible": known and recent and fresh,
        "eta_minutes": eta,
        "upper_eta_minutes": upper,
        "lead_minutes": lead,
        "last_sample_at": t.get("previous", {}).get("at"),
        "sensor_fresh": fresh,
        "method": "Median rate, empirical p20–p80 rate envelope; temperature AND RH; fallback 30 min. Extrapolation is load-dependent.",
    }


def finance(state, data, scope="facility", source=None, start=None, end=None):
    source = source or state.hospital.config["mode"]
    if scope != "facility" and scope not in state.rooms:
        raise ValueError("Unknown finance scope")
    if source not in {"SIMULATION", "CONNECTED", "LEGACY_MIXED", "ALL"}:
        raise ValueError("Unknown finance source")
    query = "SELECT SUM(cost) cost,SUM(seconds) seconds,SUM(actual) actual,SUM(baseline) baseline,SUM(measured) measured FROM energy_by_source WHERE tier=3600 AND scope=?"
    args = [scope]
    if source != "ALL":
        query += " AND source=?"
        args.append(source)
    if start is not None:
        query += " AND bucket>=?"
        args.append(int(start // 3600) * 3600)
    if end is not None:
        query += " AND bucket<?"
        args.append(end)
    row = state.store.db.execute(query, args).fetchone()
    config = state.hospital.config
    allocations = data.get("room_finance", {})
    share = (
        1
        if scope == "facility"
        else allocations.get(scope, {}).get("allocation_percent", 0) / 100
    )
    capex = config["capex_vnd"] * share
    annual_opex = config["annual_opex_vnd"] * share
    seconds, saved = float(row["seconds"] or 0), float(row["cost"] or 0)
    events = [
        e
        for e in data.get("cost_events", [])
        if (scope == "facility" or e["room_id"] == scope)
        and (source == "ALL" or e["source"] == source)
        and (start is None or aware(e["at"]).timestamp() >= start)
        and (end is None or aware(e["at"]).timestamp() < end)
    ]
    service = sum(e["cost_vnd"] for e in events)
    opex = annual_opex * seconds / (365.25 * 86400)
    net = saved - opex - service
    annual = (
        (saved - service) / seconds * 365.25 * 86400 - annual_opex
        if seconds >= 86400
        else None
    )
    return {
        "scope": scope,
        "source": source,
        "period": (
            "SELECTED" if start is not None or end is not None else "ALL_RETAINED"
        ),
        "observed_seconds": seconds,
        "measured_seconds": float(row["measured"] or 0),
        "actual_kwh": float(row["actual"] or 0),
        "baseline_kwh": float(row["baseline"] or 0),
        "saved_kwh": float(row["baseline"] or 0) - float(row["actual"] or 0),
        "observed_savings_vnd": saved,
        "capex_vnd": capex,
        "allocation_percent": share * 100,
        "unallocated_percent": max(
            0, 100 - sum(v.get("allocation_percent", 0) for v in allocations.values())
        ),
        "allocated_opex_vnd": opex,
        "service_cost_vnd": service,
        "net_operating_savings_vnd": net,
        "roi_percent": 100 * (net - capex) / capex if capex > 0 else None,
        "projected_annual_net_vnd": annual,
        "projected_payback_years": (
            capex / annual if annual and annual > 0 and capex > 0 else None
        ),
        "method": "Signed savings minus observed-time OPEX and separately recorded incremental BMS maintenance; allocation across rooms <=100%. Projection requires 24 observed hours; not normalized M&V.",
    }
