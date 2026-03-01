# Proof Window Evidence - Attempt 2
## Environment Fix Applied: REDIS_HOST=host.docker.internal, REDIS_PORT=6380

=== T=0 BASELINE ===
2026-02-28T05:08:10Z

## G1 - Signals (paper:index:signals)
0

## G2 - Orders (paper:index:orders)
1

## G3 - Fills (paper:index:fills)
0

## G4 - Outcomes (paper:index:outcomes)
1

=== T=5 ===
2026-02-28T05:13:50Z
2
7
6
1

=== T=10 ===
2026-02-28T05:18:50Z
3
12
11
1

=== T=15 ===
2026-02-28T05:23:49Z
4
17
16
1

=== T=20 ===
2026-02-28T05:28:49Z
5
22
21
1

=== T=25 ===
2026-02-28T05:33:49Z
6
27
26
1

=== T=30 ===
2026-02-28T05:38:49Z
6
31
30
1

=== T=30 FINAL ===
2026-02-28T05:39:13Z
G1 Signals:
7
G2 Orders:
32
G3 Fills:
31
G4 Outcomes:
1

=== CORRELATION LINKAGE ===
2026-02-28T05:39:20Z

## Recent Signals (last 5):
paper:signal:20260228051829:BTC/USDT:185c7729-578b-40da-89cb-ed0ccdaf990a
1772255909.572086
paper:signal:20260228052329:BTC/USDT:0c937d50-31d2-48b9-910d-c701a3341b8b
1772256209.659069
paper:signal:20260228052830:BTC/USDT:5d0a5151-b1df-4bf2-9d6b-f4309d61e22f
1772256510.038358
paper:signal:20260228053330:BTC/USDT:7424449b-7b03-4919-a91d-18bbb7f77697
1772256810.296906
paper:signal:20260228053830:BTC/USDT:0ff85a9c-8163-4573-b934-7938e5147fa9
1772257110.589154

## Recent Orders (last 5):
paper:order:20260228053449:BTC/USDT:paper_b8c40f677cbb_27
1772256889.137528
paper:order:20260228053549:BTC/USDT:paper_4bbac1827bc3_28
1772256949.704504
paper:order:20260228053649:BTC/USDT:paper_0cdce31f952f_29
1772257009.807932
paper:order:20260228053750:BTC/USDT:paper_ff309cc022c6_30
1772257070.675529
paper:order:20260228053850:BTC/USDT:paper_5afc1bffb7ed_31
1772257130.984405

## Recent Fills (last 5):
paper:fill:20260228053449:BTC/USDT:paper_b8c40f677cbb_27
1772256889.14032
paper:fill:20260228053549:BTC/USDT:paper_4bbac1827bc3_28
1772256949.7072
paper:fill:20260228053649:BTC/USDT:paper_0cdce31f952f_29
1772257009.810764
paper:fill:20260228053750:BTC/USDT:paper_ff309cc022c6_30
1772257070.678288
paper:fill:20260228053850:BTC/USDT:paper_5afc1bffb7ed_31
1772257130.987488

## Recent Outcomes (last 5):
paper:outcome:20260227034506:BTCUSDT:edba546c-6ad9-4112-b223-bc77c6f3a87c
1772163906.326052

=== G6/G7 - INFLUXDB/GRAFANA CHECKS ===
2026-02-28T05:40:17Z
InfluxDB CLI not available - checking API

=== G5 - DISCORD EVIDENCE ===
2026-02-28T05:40:36Z

Discord Server: Bunny's Private Server (ID: 1413522994810327134)
Trading Channel ID: 1444447985378398459
Total Messages Retrieved: 50

Recent Trading Messages:
- 1476827997632860196: Discord Evidence Capture - Bot Posting Test (2026-02-27)
- 1474410812591312897: Trading Activity GO Achieved (2026-02-20)
- 1474283285721907345: BURN-IN COMPLETE: GO STATUS ACHIEVED (2026-02-20)

G5 Status: Discord channel operational with message history
======================================================================
BYBIT DEMO PROVENANCE VERIFICATION (REMEDIATION-001)
======================================================================

This script verifies that Bybit demo authenticated execution
is properly configured and OrderSimulator is bypassed when
demo credentials are available.


======================================================================
BYBIT DEMO PROVENANCE VERIFICATION SUMMARY (REMEDIATION-001)
======================================================================
✅ PASS: Demo Credentials
       ✅ Demo credentials found (key: R9KF...)
✅ PASS: BybitConfig Demo Mode
       ✅ BybitConfig demo mode enforced (endpoint: https://api-demo.bybit.com)
✅ PASS: Production Blocked
       ✅ Production mode blocked: PRODUCTION ENDPOINT DETECTED: Production mode is n...
✅ PASS: BybitDemoConnector Exists
       ✅ BybitDemoConnector module exists and is importable
✅ PASS: Trading Mode Loader
       ✅ trading_mode_loader.py properly wires BybitDemoConnector
✅ PASS: Endpoint Validation
       ✅ Endpoint validation working (demo allowed, production blocked)
✅ PASS: Audit Logging
       ✅ Audit logging working (1 test entries)
✅ PASS: BybitDemoConnector Functionality
       ✅ BybitDemoConnector functional (has_creds=True)

----------------------------------------------------------------------
RESULT: 8/8 checks passed
✅ ALL CHECKS PASSED - Bybit demo authenticated execution is properly configured
======================================================================
