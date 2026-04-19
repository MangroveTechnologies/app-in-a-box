"""Unit tests for trade_log — evaluation/trade/position writes and reads."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402

from src.models.domain import Evaluation, OrderIntent, Position, Trade  # noqa: E402


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_tradelog.db"
    from src.config import app_config
    from src.shared.db import sqlite as db_mod

    monkeypatch.setattr(app_config, "DB_PATH", str(db_file))
    db_mod.reset_connection()
    from src.shared.db.sqlite import init_db
    init_db()

    # Seed a strategy row because trades/evaluations/positions FK to it.
    from src.shared.db.sqlite import get_connection
    get_connection().execute(
        """INSERT INTO strategies
           (id, mangrove_id, name, asset, timeframe, status,
            entry_json, exit_json, execution_config_json,
            generation_report_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("s1", "mg-s1", "test strat", "ETH", "1h", "paper",
         "[]", "[]", "{}", None,
         "2026-04-18T00:00:00+00:00", "2026-04-18T00:00:00+00:00"),
    )
    get_connection().commit()

    yield db_file
    db_mod.reset_connection()


def _oi(action="enter", side="buy", reason="test") -> OrderIntent:
    return OrderIntent(action=action, side=side, symbol="ETH", amount=0.1, reason=reason)


def _now():
    return datetime.now(timezone.utc)


def test_log_evaluation_round_trip(temp_db):
    from src.services.trade_log import list_evaluations, log_evaluation

    e = Evaluation(
        id=str(uuid.uuid4()),
        strategy_id="s1",
        timestamp=_now(),
        market_snapshot={"close": 2500.0},
        sdk_response={"raw": "whatever"},
        order_intents=[_oi()],
        duration_ms=42,
        status="ok",
    )
    eid = log_evaluation(e)
    assert eid == e.id

    fetched = list_evaluations("s1")
    assert len(fetched) == 1
    assert fetched[0].id == e.id
    assert fetched[0].market_snapshot == {"close": 2500.0}
    assert fetched[0].sdk_response == {"raw": "whatever"}
    assert len(fetched[0].order_intents) == 1
    assert fetched[0].order_intents[0].symbol == "ETH"


def test_log_evaluation_autogens_id(temp_db):
    from src.services.trade_log import log_evaluation

    e = Evaluation(
        id="",
        strategy_id="s1",
        timestamp=_now(),
        duration_ms=1,
        status="ok",
    )
    eid = log_evaluation(e)
    assert eid != ""
    uuid.UUID(eid)


def test_log_trade_round_trip(temp_db):
    from src.services.trade_log import list_trades, log_trade

    t = Trade(
        id=str(uuid.uuid4()),
        strategy_id="s1",
        evaluation_id=None,
        order_intent=_oi(),
        mode="paper",
        tx_hash=None,
        input_token="USDC",
        input_amount=100.0,
        output_token="ETH",
        output_amount=0.04,
        fill_price=2500.0,
        fees={"gas_usd": 0.0},
        status="simulated",
        executed_at=_now(),
    )
    tid = log_trade(t)
    assert tid == t.id

    fetched = list_trades("s1")
    assert len(fetched) == 1
    assert fetched[0].mode == "paper"
    assert fetched[0].status == "simulated"
    assert fetched[0].fees == {"gas_usd": 0.0}


def test_list_trades_filters_by_strategy(temp_db):
    from src.services.trade_log import list_all_trades, log_trade
    from src.shared.db.sqlite import get_connection

    # Second strategy row.
    get_connection().execute(
        """INSERT INTO strategies
           (id, mangrove_id, name, asset, timeframe, status,
            entry_json, exit_json, execution_config_json,
            generation_report_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("s2", "mg-s2", "other", "BTC", "1h", "paper",
         "[]", "[]", "{}", None,
         "2026-04-18T00:00:00+00:00", "2026-04-18T00:00:00+00:00"),
    )
    get_connection().commit()

    for sid, token in [("s1", "ETH"), ("s2", "BTC")]:
        log_trade(Trade(
            id=str(uuid.uuid4()), strategy_id=sid, order_intent=_oi(),
            mode="paper", input_token="USDC", input_amount=10.0,
            output_token=token, output_amount=0.001, fill_price=1.0,
            status="simulated", executed_at=_now(),
        ))

    all_s1 = list_all_trades(strategy_id="s1")
    assert len(all_s1) == 1
    assert all_s1[0].output_token == "ETH"

    both = list_all_trades()
    assert len(both) == 2


def test_list_trades_filters_by_mode(temp_db):
    from src.services.trade_log import list_all_trades, log_trade

    for mode, status in [("paper", "simulated"), ("live", "confirmed")]:
        log_trade(Trade(
            id=str(uuid.uuid4()), strategy_id="s1", order_intent=_oi(),
            mode=mode, input_token="USDC", input_amount=1.0,
            output_token="ETH", output_amount=0.0004, fill_price=2500.0,
            status=status, executed_at=_now(),
            tx_hash="0xabc" if mode == "live" else None,
        ))

    live_only = list_all_trades(mode="live")
    assert len(live_only) == 1
    assert live_only[0].mode == "live"
    assert live_only[0].tx_hash == "0xabc"


def test_trades_ordered_newest_first(temp_db):
    from src.services.trade_log import list_trades, log_trade

    t0 = _now() - timedelta(hours=2)
    t1 = _now() - timedelta(hours=1)
    for ts, tag in [(t0, "older"), (t1, "newer")]:
        log_trade(Trade(
            id=str(uuid.uuid4()), strategy_id="s1", order_intent=_oi(reason=tag),
            mode="paper", input_token="USDC", input_amount=1.0,
            output_token="ETH", output_amount=0.0004, fill_price=2500.0,
            status="simulated", executed_at=ts,
        ))

    out = list_trades("s1")
    assert out[0].order_intent.reason == "newer"
    assert out[1].order_intent.reason == "older"


def test_update_position_upsert(temp_db):
    from src.services.trade_log import log_trade, update_position
    from src.shared.db.sqlite import get_connection

    # Trades for FK linkage
    for tid in ("entry-1", "exit-1"):
        log_trade(Trade(
            id=tid, strategy_id="s1", order_intent=_oi(),
            mode="paper", input_token="USDC", input_amount=1.0,
            output_token="ETH", output_amount=0.0004, fill_price=2500.0,
            status="simulated", executed_at=_now(),
        ))

    p = Position(
        id="p1", strategy_id="s1", asset="ETH",
        entry_trade_id="entry-1", entry_price=2500.0, entry_amount=0.04,
        entry_time=_now(), status="open",
    )
    update_position(p)
    row = get_connection().execute("SELECT * FROM positions WHERE id = ?", ("p1",)).fetchone()
    assert row["status"] == "open"
    assert row["exit_trade_id"] is None

    # Upsert to closed
    closed = p.model_copy(update={
        "exit_trade_id": "exit-1",
        "exit_price": 2600.0,
        "exit_amount": 0.04,
        "exit_time": _now(),
        "status": "closed",
    })
    update_position(closed)
    row2 = get_connection().execute("SELECT * FROM positions WHERE id = ?", ("p1",)).fetchone()
    assert row2["status"] == "closed"
    assert row2["exit_trade_id"] == "exit-1"
    assert row2["exit_price"] == 2600.0
