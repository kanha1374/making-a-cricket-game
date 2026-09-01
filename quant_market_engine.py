#!/usr/bin/env python3
"""
Quantitative Market Movement Engine

Implements:
- Minute-by-minute buyer/seller VAR forecasts
- Master price prediction equation with full telemetry
- Stage countdown ladder with pass/fail gates
- Auto-tuning on stage failure
- Crash-safe checkpoint persistence and resume

Data sources:
- Delta Exchange REST endpoints (primary)
- TradingView scanner endpoint (fallback)
"""

from __future__ import annotations

import argparse
import json
import math
import random
import signal
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib import error, parse, request


# --------------------------- Configuration Models --------------------------- #


@dataclass
class EngineParameters:
    """Calibrated model parameters that can be auto-tuned."""

    alpha: float = 0.18
    theta: float = 0.20
    gamma: float = 0.10
    phi: float = 0.15

    w1: float = 0.40
    w2: float = 0.35
    w3: float = 0.25

    var_lags: int = 5
    mu_b: float = 120.0
    mu_s: float = 120.0
    gamma_b: float = 0.025
    gamma_s: float = 0.025

    alpha_11: List[float] = field(default_factory=lambda: [0.11, 0.08, 0.06, 0.05, 0.04])
    alpha_12: List[float] = field(default_factory=lambda: [0.03, 0.03, 0.02, 0.02, 0.01])
    alpha_21: List[float] = field(default_factory=lambda: [0.03, 0.03, 0.02, 0.02, 0.01])
    alpha_22: List[float] = field(default_factory=lambda: [0.11, 0.08, 0.06, 0.05, 0.04])

    momentum_h_sqrt_power: float = 0.50
    ofi_h_sqrt_power: float = 0.50

    def normalized_weights(self) -> Tuple[float, float, float]:
        total = self.w1 + self.w2 + self.w3
        if total <= 0:
            return 1 / 3, 1 / 3, 1 / 3
        return self.w1 / total, self.w2 / total, self.w3 / total


@dataclass
class EngineState:
    """Persisted state to survive process or machine interruption."""

    symbol: str = "BTCUSDT"
    stage_minutes: List[int] = field(default_factory=lambda: [120, 60, 30, 10, 5])
    current_stage_index: int = 0
    stage_attempt: int = 1
    in_global_sweep: bool = False
    global_sweep_index: int = 0

    previous_prediction: Optional[float] = None
    completed_stages: List[int] = field(default_factory=list)
    stage_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    countdown_started_unix: Optional[float] = None
    countdown_target_unix: Optional[float] = None
    countdown_horizon: Optional[int] = None

    parameters: EngineParameters = field(default_factory=EngineParameters)
    telemetry_log: List[Dict[str, Any]] = field(default_factory=list)
    tuning_log: List[Dict[str, Any]] = field(default_factory=list)


# ------------------------------ Utility Layer ------------------------------ #


class JsonCheckpoint:
    """JSON persistence with atomic writes."""

    def __init__(self, path: Path):
        self.path = path

    def save(self, state: EngineState) -> None:
        payload = self._encode_state(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> Optional[EngineState]:
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return self._decode_state(raw)

    def _encode_state(self, state: EngineState) -> Dict[str, Any]:
        payload = asdict(state)
        payload["parameters"] = asdict(state.parameters)
        return payload

    def _decode_state(self, raw: Dict[str, Any]) -> EngineState:
        params = EngineParameters(**raw.get("parameters", {}))
        raw = dict(raw)
        raw["parameters"] = params
        return EngineState(**raw)


class Logger:
    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def line(message: str) -> None:
        print(f"[{Logger.now()}] {message}", flush=True)

    @staticmethod
    def section(title: str) -> None:
        print("\n" + "=" * 80)
        print(title)
        print("=" * 80, flush=True)


# ----------------------------- Market Data APIs ---------------------------- #


class DataSourceError(RuntimeError):
    pass


class BaseDataSource:
    name: str = "base"

    def fetch_price(self, symbol: str) -> float:
        raise NotImplementedError

    def fetch_level_1_5(self, symbol: str) -> Dict[str, Any]:
        raise NotImplementedError

    def fetch_recent_trades(self, symbol: str, limit: int = 250) -> List[Dict[str, Any]]:
        raise NotImplementedError


class DeltaExchangeSource(BaseDataSource):
    name = "delta.exchange"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.base_candidates = [
            "https://api.delta.exchange",
            "https://api.india.delta.exchange",
        ]

    def _get_json(self, url: str) -> Dict[str, Any]:
        req = request.Request(url, headers={"User-Agent": "quant-market-engine/1.0"})
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"Delta request failed for {url}: {exc}") from exc

    def _resolve_product(self, symbol: str) -> Dict[str, Any]:
        symbol_u = symbol.upper()
        aliases = {
            "BTCUSD": ["BTCUSD", "XBTUSD", "BTCUSDT"],
            "BTCUSDT": ["BTCUSDT", "BTCUSD", "XBTUSD"],
            "ETHUSD": ["ETHUSD", "ETHUSDT"],
            "ETHUSDT": ["ETHUSDT", "ETHUSD"],
        }
        lookup = aliases.get(symbol_u, [symbol_u])

        for base in self.base_candidates:
            payload = self._get_json(f"{base}/v2/products")
            products = payload.get("result", [])
            for p in products:
                p_symbol = str(p.get("symbol", "")).upper()
                if p_symbol in lookup:
                    return {"base": base, "product": p}
        raise DataSourceError(f"Unable to resolve Delta product for symbol={symbol}")

    def fetch_price(self, symbol: str) -> float:
        resolved = self._resolve_product(symbol)
        base = resolved["base"]
        product = resolved["product"]
        product_id = product.get("id")
        mark_url = f"{base}/v2/tickers/{product.get('symbol')}"

        try:
            payload = self._get_json(mark_url)
            maybe = payload.get("result", {})
            for key in ("mark_price", "spot_price", "close", "last_price"):
                val = maybe.get(key)
                if val is not None:
                    return float(val)
        except DataSourceError:
            pass

        if product_id is None:
            raise DataSourceError(f"Delta product missing id for symbol={symbol}")
        payload = self._get_json(f"{base}/v2/l2orderbook/{product_id}")
        result = payload.get("result", {})
        bids = result.get("buy", [])
        asks = result.get("sell", [])
        if not bids or not asks:
            raise DataSourceError("No orderbook data to infer price")
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        return (best_bid + best_ask) / 2.0

    def fetch_level_1_5(self, symbol: str) -> Dict[str, Any]:
        resolved = self._resolve_product(symbol)
        base = resolved["base"]
        product = resolved["product"]
        product_id = product.get("id")
        if product_id is None:
            raise DataSourceError("Missing product id for orderbook")

        payload = self._get_json(f"{base}/v2/l2orderbook/{product_id}")
        result = payload.get("result", {})
        bids_raw = result.get("buy", [])[:5]
        asks_raw = result.get("sell", [])[:5]
        if len(bids_raw) < 1 or len(asks_raw) < 1:
            raise DataSourceError("Level 1-5 orderbook missing")

        bids = [{"price": float(p), "size": float(s)} for p, s, *_ in bids_raw]
        asks = [{"price": float(p), "size": float(s)} for p, s, *_ in asks_raw]
        return {
            "symbol": product.get("symbol", symbol),
            "best_bid": bids[0]["price"],
            "best_ask": asks[0]["price"],
            "bids": bids,
            "asks": asks,
            "timestamp": Logger.now(),
        }

    def fetch_recent_trades(self, symbol: str, limit: int = 250) -> List[Dict[str, Any]]:
        resolved = self._resolve_product(symbol)
        base = resolved["base"]
        product = resolved["product"]
        product_id = product.get("id")
        if product_id is None:
            raise DataSourceError("Missing product id for trades")

        url = f"{base}/v2/trades/{product_id}?page_size={min(max(limit, 10), 1000)}"
        payload = self._get_json(url)
        rows = payload.get("result", [])
        trades = []
        for row in rows:
            try:
                trades.append(
                    {
                        "price": float(row.get("price")),
                        "size": float(row.get("size", 0.0)),
                        "side": str(row.get("side", "")).lower(),
                        "timestamp": row.get("created_at"),
                    }
                )
            except (TypeError, ValueError):
                continue
        if not trades:
            raise DataSourceError("No trades returned")
        return trades


class TradingViewSource(BaseDataSource):
    """Fallback for spot-like last-trade values via TradingView scanner endpoint."""

    name = "tradingview.com"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                "User-Agent": "quant-market-engine/1.0",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"TradingView request failed: {exc}") from exc

    def _resolve_tv_symbol(self, symbol: str) -> str:
        s = symbol.upper().replace("/", "")
        if s in {"BTCUSD", "BTCUSDT", "XBTUSD"}:
            return "BINANCE:BTCUSDT"
        if s in {"ETHUSD", "ETHUSDT"}:
            return "BINANCE:ETHUSDT"
        if s in {"EURUSD", "USDJPY", "GBPUSD"}:
            return f"FX:{s}"
        return s

    def fetch_price(self, symbol: str) -> float:
        tv_symbol = self._resolve_tv_symbol(symbol)
        payload = {
            "symbols": {"tickers": [tv_symbol], "query": {"types": []}},
            "columns": ["close", "bid", "ask", "volume"],
        }
        data = self._post_json("https://scanner.tradingview.com/crypto/scan", payload)
        rows = data.get("data", [])
        if not rows:
            data = self._post_json("https://scanner.tradingview.com/forex/scan", payload)
            rows = data.get("data", [])
        if not rows:
            raise DataSourceError(f"No TradingView scanner rows for {symbol}")
        values = rows[0].get("d", [])
        numeric = [v for v in values if isinstance(v, (int, float))]
        if not numeric:
            raise DataSourceError(f"No numeric TradingView fields for {symbol}")
        return float(numeric[0])

    def fetch_level_1_5(self, symbol: str) -> Dict[str, Any]:
        # TradingView scanner does not expose full L2 depth in public API.
        # Return a synthetic narrow book around live price for fallback continuity.
        px = self.fetch_price(symbol)
        spread = max(px * 0.0001, 0.5)
        bids = [{"price": px - spread * (i + 1), "size": 1.0 + i * 0.2} for i in range(5)]
        asks = [{"price": px + spread * (i + 1), "size": 1.0 + i * 0.2} for i in range(5)]
        return {
            "symbol": symbol,
            "best_bid": bids[0]["price"],
            "best_ask": asks[0]["price"],
            "bids": bids,
            "asks": asks,
            "timestamp": Logger.now(),
            "synthetic": True,
        }

    def fetch_recent_trades(self, symbol: str, limit: int = 250) -> List[Dict[str, Any]]:
        # Public TradingView scanner does not provide tape-level prints.
        # Build lightweight synthetic prints around current spot as fallback.
        px = self.fetch_price(symbol)
        trades: List[Dict[str, Any]] = []
        for i in range(min(max(limit, 10), 300)):
            side = "buy" if i % 2 == 0 else "sell"
            drift = random.uniform(-0.002, 0.002) * px
            trades.append(
                {
                    "price": px + drift,
                    "size": random.uniform(0.05, 0.8),
                    "side": side,
                    "timestamp": Logger.now(),
                }
            )
        return trades


class LiveFeed:
    """Tries multiple live sources and records which one succeeds."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.sources: Sequence[BaseDataSource] = (DeltaExchangeSource(), TradingViewSource())

    def _attempt(self, fn_name: str, *args: Any, **kwargs: Any) -> Tuple[Any, str]:
        errors: List[str] = []
        for source in self.sources:
            try:
                fn = getattr(source, fn_name)
                return fn(*args, **kwargs), source.name
            except Exception as exc:  # noqa: BLE001 - intentional fallback chain
                errors.append(f"{source.name}: {exc}")
                continue
        raise DataSourceError(f"All data sources failed for {fn_name}. Details: {' | '.join(errors)}")

    def fetch_price(self) -> Tuple[float, str]:
        return self._attempt("fetch_price", self.symbol)

    def fetch_orderbook(self) -> Tuple[Dict[str, Any], str]:
        return self._attempt("fetch_level_1_5", self.symbol)

    def fetch_trades(self, limit: int = 250) -> Tuple[List[Dict[str, Any]], str]:
        return self._attempt("fetch_recent_trades", self.symbol, limit)


# -------------------------- Mathematical Engine Core ----------------------- #


class QuantEngine:
    def __init__(self, state: EngineState, checkpoint: JsonCheckpoint, speed_multiplier: float = 1.0):
        self.state = state
        self.checkpoint = checkpoint
        self.feed = LiveFeed(state.symbol)
        self.speed_multiplier = max(speed_multiplier, 1e-6)
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        Logger.line(f"Signal {signum} received. Saving checkpoint and exiting safely.")
        self.shutdown_requested = True
        self.save_checkpoint()

    def save_checkpoint(self) -> None:
        self.checkpoint.save(self.state)

    def explain_formula_variables(self) -> None:
        Logger.section("MASTER FORMULA VARIABLE EXPLANATION")
        explanations = {
            "B(t+m), S(t+m)": "Minute m forecasted aggressive buyer/seller volume from VAR over L1-L5 deltas.",
            "mu_B, mu_S": "Baseline Poisson-like arrival rates for buyers/sellers.",
            "alpha_ij^(k)": "Cross-excitation lag-k momentum between buy/sell flows.",
            "M(t)": "Exogenous market factor proxy built from spread, imbalance and tape pressure.",
            "epsilon_B, epsilon_S": "Innovation noise terms for microstructure randomness.",
            "P_t": "Current live spot/mark price.",
            "V*_t": "Dynamic intrinsic equilibrium from weighted SMA + EMA + VWAP.",
            "Delta P_t": "Recent 5-minute price change estimate.",
            "V_avg": "Average trade size volume baseline from live tape.",
            "alpha": "Momentum sensitivity multiplier.",
            "theta": "Mean-reversion pull strength to V*_t.",
            "gamma": "Order flow imbalance impact multiplier.",
            "phi": "Residual error correction feedback gain.",
            "sigma_1m": "Std-dev of 1-minute log returns from recent trade history.",
        }
        for k, v in explanations.items():
            Logger.line(f"{k}: {v}")

    def _derive_microstructure_factors(self, orderbook: Dict[str, Any], trades: List[Dict[str, Any]]) -> Dict[str, float]:
        bids = orderbook["bids"][:5]
        asks = orderbook["asks"][:5]

        bid_depth = sum(x["size"] for x in bids)
        ask_depth = sum(x["size"] for x in asks)
        depth_total = max(bid_depth + ask_depth, 1e-9)
        depth_imbalance = (bid_depth - ask_depth) / depth_total

        best_bid = float(orderbook["best_bid"])
        best_ask = float(orderbook["best_ask"])
        spread = max(best_ask - best_bid, 1e-9)

        buy_aggr = sum(t["size"] for t in trades if "buy" in t["side"])
        sell_aggr = sum(t["size"] for t in trades if "sell" in t["side"])
        tape_total = max(buy_aggr + sell_aggr, 1e-9)
        tape_imbalance = (buy_aggr - sell_aggr) / tape_total

        return {
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "depth_imbalance": depth_imbalance,
            "spread": spread,
            "buy_aggr": buy_aggr,
            "sell_aggr": sell_aggr,
            "tape_imbalance": tape_imbalance,
            "m_t": 0.6 * depth_imbalance + 0.4 * tape_imbalance,
        }

    def _compute_vstar(self, prices: List[float], trades: List[Dict[str, Any]], params: EngineParameters) -> float:
        w1, w2, w3 = params.normalized_weights()
        sma_n = statistics.fmean(prices[-20:]) if prices else prices[-1]

        ema_period = 20
        multiplier = 2 / (ema_period + 1)
        ema = prices[0]
        for px in prices[1:]:
            ema = (px - ema) * multiplier + ema

        pv = sum(t["price"] * t["size"] for t in trades)
        tv = sum(t["size"] for t in trades)
        vwap = pv / tv if tv > 0 else prices[-1]

        return (w1 * sma_n) + (w2 * ema) + (w3 * vwap)

    def _estimate_sigma_1m(self, prices: List[float]) -> float:
        if len(prices) < 3:
            return 0.0
        returns = []
        for i in range(1, len(prices)):
            p0 = max(prices[i - 1], 1e-9)
            p1 = max(prices[i], 1e-9)
            returns.append(math.log(p1 / p0))
        if len(returns) < 2:
            return 0.0
        return statistics.pstdev(returns)

    def _prepare_price_series(self, spot: float, trades: List[Dict[str, Any]], bars: int = 60) -> List[float]:
        tape = [float(t["price"]) for t in trades]
        if not tape:
            tape = [spot]
        if len(tape) >= bars:
            return tape[-bars:]
        padded = [tape[0]] * (bars - len(tape)) + tape
        return padded

    def forecast_var_flows(
        self,
        horizon: int,
        params: EngineParameters,
        m_t: float,
        init_buy: float,
        init_sell: float,
    ) -> Tuple[List[float], List[float]]:
        lags = max(1, min(params.var_lags, len(params.alpha_11), len(params.alpha_12), len(params.alpha_21), len(params.alpha_22)))

        b_hist: List[float] = [max(init_buy, 1e-6)] * lags
        s_hist: List[float] = [max(init_sell, 1e-6)] * lags
        b_forecast: List[float] = []
        s_forecast: List[float] = []

        for _m in range(1, horizon + 1):
            b_next = params.mu_b + params.gamma_b * m_t
            s_next = params.mu_s + params.gamma_s * m_t

            for k in range(1, lags + 1):
                b_lag = b_hist[-k]
                s_lag = s_hist[-k]
                b_next += params.alpha_11[k - 1] * b_lag + params.alpha_12[k - 1] * s_lag
                s_next += params.alpha_21[k - 1] * b_lag + params.alpha_22[k - 1] * s_lag

            eps_b = random.gauss(0, max(1.0, init_buy * 0.01))
            eps_s = random.gauss(0, max(1.0, init_sell * 0.01))
            b_next = max(1e-6, b_next + eps_b)
            s_next = max(1e-6, s_next + eps_s)

            b_hist.append(b_next)
            s_hist.append(s_next)
            b_forecast.append(b_next)
            s_forecast.append(s_next)

        return b_forecast, s_forecast

    def master_prediction(self, horizon: int) -> Dict[str, Any]:
        params = self.state.parameters
        spot, px_source = self.feed.fetch_price()
        orderbook, ob_source = self.feed.fetch_orderbook()
        trades, tr_source = self.feed.fetch_trades(limit=max(200, horizon * 6))

        prices = self._prepare_price_series(spot, trades, bars=120)
        factors = self._derive_microstructure_factors(orderbook, trades)
        v_star = self._compute_vstar(prices, trades, params)

        last_5_ago = prices[-6] if len(prices) >= 6 else prices[0]
        delta_p_t = spot - last_5_ago

        sigma_1m = self._estimate_sigma_1m(prices[-61:])
        v_avg = statistics.fmean([max(t["size"], 1e-9) for t in trades])

        init_buy = max(factors["buy_aggr"], 1.0)
        init_sell = max(factors["sell_aggr"], 1.0)
        b_path, s_path = self.forecast_var_flows(horizon, params, factors["m_t"], init_buy, init_sell)

        b_total = sum(b_path)
        s_total = sum(s_path)
        flow_total = max(b_total + s_total, 1e-9)
        ofi_h = max(-1.0, min(1.0, (b_total - s_total) / flow_total))

        p_prev = self.state.previous_prediction if self.state.previous_prediction is not None else spot

        base_term = (spot + ((v_star * v_star) / max(spot, 1e-9))) / 2.0
        momentum_term = delta_p_t * ((b_total + s_total) / max(v_avg, 1e-9)) * params.alpha * math.pow(horizon / 5.0, params.momentum_h_sqrt_power)
        mean_revert_term = params.theta * (v_star - spot)
        ofi_term = params.gamma * spot * ofi_h * math.pow(horizon, params.ofi_h_sqrt_power)
        residual_term = params.phi * (spot - p_prev)

        predicted = base_term + momentum_term + mean_revert_term + ofi_term + residual_term
        band = 0.5 * sigma_1m * math.sqrt(horizon)

        telemetry = {
            "timestamp": Logger.now(),
            "symbol": self.state.symbol,
            "horizon": horizon,
            "live_sources": {"price": px_source, "orderbook": ob_source, "trades": tr_source},
            "spot_price_P_t": spot,
            "v_star": v_star,
            "delta_p_t": delta_p_t,
            "sigma_1m": sigma_1m,
            "v_avg": v_avg,
            "b_total": b_total,
            "s_total": s_total,
            "ofi_h": ofi_h,
            "params": asdict(params),
            "terms": {
                "base_term": base_term,
                "momentum_term": momentum_term,
                "mean_revert_term": mean_revert_term,
                "ofi_term": ofi_term,
                "residual_term": residual_term,
            },
            "prediction": {
                "price": predicted,
                "upper": predicted + band,
                "lower": predicted - band,
                "band_half_width": band,
            },
            "microstructure": {
                "best_bid": orderbook["best_bid"],
                "best_ask": orderbook["best_ask"],
                "spread": factors["spread"],
                "bid_depth_l1_5": factors["bid_depth"],
                "ask_depth_l1_5": factors["ask_depth"],
                "depth_imbalance": factors["depth_imbalance"],
                "tape_buy": factors["buy_aggr"],
                "tape_sell": factors["sell_aggr"],
                "m_t": factors["m_t"],
            },
            "paths": {
                "buyer_forecast": b_path,
                "seller_forecast": s_path,
            },
        }

        self.state.previous_prediction = predicted
        self.state.telemetry_log.append(telemetry)
        if len(self.state.telemetry_log) > 2000:
            self.state.telemetry_log = self.state.telemetry_log[-2000:]

        return telemetry

    def _print_telemetry(self, telemetry: Dict[str, Any]) -> None:
        Logger.section(f"LIVE TELEMETRY H={telemetry['horizon']}m")
        Logger.line(f"Data sources => {telemetry['live_sources']}")
        Logger.line(f"P_t: {telemetry['spot_price_P_t']:.6f}")
        Logger.line(f"V*_t: {telemetry['v_star']:.6f}")
        Logger.line(f"Delta P_t: {telemetry['delta_p_t']:.6f}")
        Logger.line(f"B_total: {telemetry['b_total']:.6f}")
        Logger.line(f"S_total: {telemetry['s_total']:.6f}")
        Logger.line(f"OFI_H: {telemetry['ofi_h']:.6f}")
        Logger.line(f"V_avg: {telemetry['v_avg']:.6f}")
        Logger.line(f"sigma_1m: {telemetry['sigma_1m']:.8f}")
        for k, v in telemetry["terms"].items():
            Logger.line(f"{k}: {v:.6f}")
        p = telemetry["prediction"]
        Logger.line(
            "Prediction => "
            f"price={p['price']:.6f}, upper={p['upper']:.6f}, lower={p['lower']:.6f}, "
            f"half_band={p['band_half_width']:.6f}"
        )

    def _run_countdown(self, horizon_minutes: int) -> None:
        now = time.time()

        if self.state.countdown_target_unix and self.state.countdown_horizon == horizon_minutes:
            target = self.state.countdown_target_unix
            if target <= now:
                return
        else:
            duration_seconds = int(horizon_minutes * 60 / self.speed_multiplier)
            target = now + duration_seconds
            self.state.countdown_started_unix = now
            self.state.countdown_target_unix = target
            self.state.countdown_horizon = horizon_minutes
            self.save_checkpoint()

        Logger.section(f"COUNTDOWN START H={horizon_minutes}m")
        while True:
            if self.shutdown_requested:
                return
            remaining = int(max(0, self.state.countdown_target_unix - time.time()))
            mins, secs = divmod(remaining, 60)
            Logger.line(f"Remaining: {mins:02d}:{secs:02d}")
            if remaining <= 0:
                break
            time.sleep(1)
        Logger.line("Countdown completed.")

    def _clear_countdown(self) -> None:
        self.state.countdown_started_unix = None
        self.state.countdown_target_unix = None
        self.state.countdown_horizon = None

    def _stage_key(self, horizon: int, global_sweep: bool) -> str:
        return f"{'global' if global_sweep else 'stage'}_{horizon}m"

    def _evaluate_stage(self, horizon: int, allow_tuning: bool, global_sweep: bool) -> bool:
        telemetry = self.master_prediction(horizon)
        self._print_telemetry(telemetry)
        self.save_checkpoint()

        self._run_countdown(horizon)
        if self.shutdown_requested:
            return False

        real_price, source = self.feed.fetch_price()
        predicted = telemetry["prediction"]["price"]
        error_abs = abs(real_price - predicted)
        passed = error_abs <= 10.0

        stage_record = {
            "timestamp": Logger.now(),
            "horizon": horizon,
            "predicted": predicted,
            "real_price": real_price,
            "absolute_error": error_abs,
            "pass": passed,
            "source": source,
            "global_sweep": global_sweep,
            "attempt": self.state.stage_attempt,
        }
        self.state.stage_results[self._stage_key(horizon, global_sweep)] = stage_record
        self._clear_countdown()
        self.save_checkpoint()

        verdict = "PASS" if passed else "FAIL"
        Logger.section(f"STAGE RESULT H={horizon}m => {verdict}")
        Logger.line(f"Predicted: {predicted:.6f}")
        Logger.line(f"Real: {real_price:.6f} (source={source})")
        Logger.line(f"|Error|: {error_abs:.6f} (threshold=10.000000)")

        if passed:
            return True
        if allow_tuning:
            self._auto_tune(horizon, error_abs)
            self.save_checkpoint()
        return False

    def _auto_tune(self, horizon: int, error_abs: float) -> None:
        params = self.state.parameters
        before = asdict(params)

        lr = min(0.05, max(0.005, error_abs / max(10000.0, abs(error_abs) * 100)))
        direction = 1.0 if random.random() > 0.5 else -1.0

        def clamp(v: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, v))

        params.alpha = clamp(params.alpha * (1 + direction * lr), 0.01, 2.0)
        params.theta = clamp(params.theta * (1 - direction * lr * 0.7), 0.01, 2.0)
        params.gamma = clamp(params.gamma * (1 + direction * lr * 0.8), 0.001, 2.0)
        params.phi = clamp(params.phi * (1 - direction * lr * 0.6), 0.001, 2.0)

        params.momentum_h_sqrt_power = clamp(params.momentum_h_sqrt_power + direction * lr * 0.1, 0.35, 0.75)
        params.ofi_h_sqrt_power = clamp(params.ofi_h_sqrt_power + direction * lr * 0.1, 0.35, 0.75)

        after = asdict(params)
        change_log = {
            "timestamp": Logger.now(),
            "horizon": horizon,
            "error_abs": error_abs,
            "learning_rate": lr,
            "direction": direction,
            "before": before,
            "after": after,
            "delta": {k: after[k] - before[k] for k in before.keys() if isinstance(before[k], (float, int))},
        }
        self.state.tuning_log.append(change_log)

        Logger.section("AUTO-TUNING TRIGGERED")
        Logger.line(f"Horizon: {horizon}m | Error: {error_abs:.6f} | LR: {lr:.6f} | Direction: {direction:+.0f}")
        for key in ["alpha", "theta", "gamma", "phi", "momentum_h_sqrt_power", "ofi_h_sqrt_power"]:
            Logger.line(f"{key}: {before[key]:.8f} -> {after[key]:.8f} (delta={after[key] - before[key]:+.8f})")

    def run_stage_ladder(self) -> None:
        Logger.section("DESCENDING COUNTDOWN LADDER")
        while self.state.current_stage_index < len(self.state.stage_minutes):
            if self.shutdown_requested:
                return
            horizon = self.state.stage_minutes[self.state.current_stage_index]
            Logger.section(
                f"RUNNING STAGE {self.state.current_stage_index + 1}/{len(self.state.stage_minutes)} | "
                f"H={horizon}m | attempt={self.state.stage_attempt}"
            )
            passed = self._evaluate_stage(horizon, allow_tuning=True, global_sweep=False)
            if passed:
                if horizon not in self.state.completed_stages:
                    self.state.completed_stages.append(horizon)
                self.state.current_stage_index += 1
                self.state.stage_attempt = 1
                self.save_checkpoint()
            else:
                if self.shutdown_requested:
                    return
                self.state.stage_attempt += 1
                self.save_checkpoint()

    def run_global_sweep(self) -> None:
        Logger.section("GLOBAL ALL-STAGE CLEAN RECHECK SWEEP")
        self.state.in_global_sweep = True
        self.state.global_sweep_index = 0
        self.save_checkpoint()

        while True:
            all_pass = True
            for idx, horizon in enumerate(self.state.stage_minutes):
                if self.shutdown_requested:
                    return
                self.state.global_sweep_index = idx
                self.save_checkpoint()
                Logger.section(f"GLOBAL SWEEP CHECK {idx + 1}/{len(self.state.stage_minutes)} | H={horizon}m")
                passed = self._evaluate_stage(horizon, allow_tuning=False, global_sweep=True)
                if not passed:
                    all_pass = False
                    Logger.line("Global sweep failed; auto-tuning and restarting complete sweep.")
                    last_error = self.state.stage_results[self._stage_key(horizon, True)]["absolute_error"]
                    self._auto_tune(horizon, last_error)
                    self.save_checkpoint()
                    break
            if all_pass:
                Logger.section("GLOBAL SWEEP CLEAN PASS")
                Logger.line("All stages passed simultaneously without tuning during sweep checks.")
                self.state.in_global_sweep = False
                self.state.global_sweep_index = 0
                self.save_checkpoint()
                return

    def run(self) -> None:
        self.explain_formula_variables()

        if self.state.current_stage_index >= len(self.state.stage_minutes):
            Logger.line("Stage ladder already complete in checkpoint. Proceeding to global sweep.")
        else:
            self.run_stage_ladder()
            if self.shutdown_requested:
                return

        self.run_global_sweep()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quantitative market movement engine with live feeds + tuning")
    parser.add_argument("--symbol", default="BTCUSDT", help="Market symbol, e.g., BTCUSDT, ETHUSDT, EURUSD")
    parser.add_argument(
        "--checkpoint",
        default="quant_engine_checkpoint.json",
        help="Path to JSON checkpoint file",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing checkpoint if it exists",
    )
    parser.add_argument(
        "--speed-multiplier",
        type=float,
        default=1.0,
        help="Countdown acceleration factor for testing (2.0 = 2x faster, 60 = 1 minute per 1 second)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Ignore checkpoint and start from a clean state",
    )
    return parser.parse_args(argv)


def load_or_init_state(args: argparse.Namespace, checkpoint: JsonCheckpoint) -> EngineState:
    if args.reset:
        Logger.line("--reset supplied: starting new state.")
        return EngineState(symbol=args.symbol)

    if args.resume:
        loaded = checkpoint.load()
        if loaded:
            Logger.line(f"Checkpoint loaded from {checkpoint.path}")
            loaded.symbol = args.symbol or loaded.symbol
            return loaded
        Logger.line("--resume requested but checkpoint missing; starting new state.")

    existing = checkpoint.load()
    if existing and not args.resume:
        Logger.line(f"Existing checkpoint found at {checkpoint.path}; auto-resuming.")
        existing.symbol = args.symbol or existing.symbol
        return existing

    return EngineState(symbol=args.symbol)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    checkpoint = JsonCheckpoint(Path(args.checkpoint).expanduser().resolve())
    state = load_or_init_state(args, checkpoint)

    engine = QuantEngine(state=state, checkpoint=checkpoint, speed_multiplier=args.speed_multiplier)
    try:
        engine.run()
    except DataSourceError as exc:
        Logger.section("LIVE DATA SOURCE ERROR")
        Logger.line(str(exc))
        engine.save_checkpoint()
        return 2
    except Exception as exc:  # noqa: BLE001
        Logger.section("UNEXPECTED ERROR")
        Logger.line(repr(exc))
        engine.save_checkpoint()
        return 1

    engine.save_checkpoint()
    Logger.section("ENGINE COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
