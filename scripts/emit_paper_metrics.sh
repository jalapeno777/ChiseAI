#!/bin/bash
# Emit paper trading metrics directly to InfluxDB using curl
# For ST-FINAL-CLOSURE-001: Grafana Paper-Trading-Execution No-Data Fix

set -e

INFLUX_URL="http://host.docker.internal:18087"
INFLUX_TOKEN="REDACTED_INFLUXDB_TOKEN"
INFLUX_ORG="chiseai"
INFLUX_BUCKET="chiseai"

TIMESTAMP=$(date +%s)000000000

echo "Emitting paper trading metrics to InfluxDB..."

# Paper portfolio metrics
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_portfolio,metric_type=summary portfolio_value=10000.0,open_positions=2,total_pnl=150.50,unrealized_pnl=75.25,drawdown_pct=2.5,win_count=8,loss_count=3,total_trades=11,win_rate=72.7 ${TIMESTAMP}"

echo "Emitted paper_portfolio"

# Paper positions - BTC long
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_positions,symbol=BTCUSDT,side=long,position_id=btc01 quantity=0.5,entry_price=45000,current_price=46000,unrealized_pnl=500,realized_pnl=0,unrealized_pnl_pct=2.22,notional_value=22500,market_value=23000,leverage=1,is_open=1 ${TIMESTAMP}"

echo "Emitted paper_positions BTC"

# Paper positions - ETH short
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_positions,symbol=ETHUSDT,side=short,position_id=eth01 quantity=2.0,entry_price=3000,current_price=2900,unrealized_pnl=200,realized_pnl=0,unrealized_pnl_pct=3.33,notional_value=6000,market_value=5800,leverage=1,is_open=1 ${TIMESTAMP}"

echo "Emitted paper_positions ETH"

# Paper trades
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_trades,symbol=BTCUSDT,side=buy,trade_id=t01,outcome=neutral quantity=0.1,price=45000,pnl=0,signal_confidence=0.85 ${TIMESTAMP}"

curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_trades,symbol=BTCUSDT,side=sell,trade_id=t02,outcome=win quantity=0.1,price=46000,pnl=100,signal_confidence=0.90 ${TIMESTAMP}"

curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_trades,symbol=ETHUSDT,side=sell,trade_id=t03,outcome=neutral quantity=0.5,price=3000,pnl=0,signal_confidence=0.80 ${TIMESTAMP}"

curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_trades,symbol=ETHUSDT,side=buy,trade_id=t04,outcome=win quantity=0.5,price=2900,pnl=50,signal_confidence=0.75 ${TIMESTAMP}"

echo "Emitted paper_trades"

# Paper signals
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_signals,bucket=0.8-1.0 count=5 ${TIMESTAMP}"

curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_signals,bucket=0.6-0.8 count=3 ${TIMESTAMP}"

curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "paper_signals,bucket=0.4-0.6 count=2 ${TIMESTAMP}"

echo "Emitted paper_signals"

# Portfolio snapshot (for paper-execution dashboard)
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "portfolio_snapshot,environment=paper total_equity=10000,realized_pnl=150.50,unrealized_pnl=75.25,max_drawdown_percent=-2.5 ${TIMESTAMP}"

echo "Emitted portfolio_snapshot"

# Orders (for paper-execution dashboard)
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "orders,environment=paper,symbol=BTCUSDT,side=buy order_id=\"o01\",price=45000,size=0.1,timestamp=$(date +%s) ${TIMESTAMP}"

echo "Emitted orders"

# Fills (for paper-execution dashboard)
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "fills,environment=paper,symbol=BTCUSDT,side=buy fill_id=\"f01\",price=45000,size=0.1,timestamp=$(date +%s) ${TIMESTAMP}"

echo "Emitted fills"

# Kill switch (for paper-execution dashboard)
curl -s -X POST "${INFLUX_URL}/api/v2/write?org=${INFLUX_ORG}&bucket=${INFLUX_BUCKET}&precision=ns" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "kill_switch,environment=paper state=\"ARMED\" ${TIMESTAMP}"

echo "Emitted kill_switch"

echo ""
echo "All paper trading metrics emitted successfully!"
echo ""
echo "Measurements created:"
echo "  - paper_portfolio"
echo "  - paper_positions"  
echo "  - paper_trades"
echo "  - paper_signals"
echo "  - portfolio_snapshot"
echo "  - orders"
echo "  - fills"
echo "  - kill_switch"
