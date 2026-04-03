# Root Cause Analysis: BOS/CHoCH Classifier Detection Rate ST-ICT-S9-001

## Summary

The BOS/CHoCH classifier was only achieving ~15% detection rate due to:

1. **Root cause**: `_is_level_broken()` only compared pivot prices, not OHLCV candle data
2. **Secondary issue**: Algorithm detected CHoCH before BOS due to chronological iteration order
3. **Tertiary issue**: Duplicate events being generated from the nested loop structure

## Root Cause Analysis

### Root Cause #1: `_is_level_broken()` Did Not Use Candle Data

**Location**: `src/market_analysis/structure/bos_choch.py`, lines 355-409

**Problem**: The `_is_level_broken()` method received `data: list[OHLCVData]` but never used it. It only compared swing pivot prices:

```python
# BEFORE (buggy)
def _is_level_broken(self, swing, level, data, is_bullish):
    # Only checked if swing price exceeded level price
    return swing.price > level.price if is_bullish else swing.price < level.price
```

**Fix**: Now checks both swing candle's price AND close beyond the level:

```python
# AFTER (fixed)
def _is_level_broken(self, swing, level, data, is_bullish):
    swing_candle = data[swing.index]
    if is_bullish:
        return (swing_candle.high_price > level.price and
                swing_candle.close_price > level.price)
    else:
        return (swing_candle.low_price < level.price and
                swing_candle.close_price < level.price)
```

This dual confirmation prevents false breaks where only the wick penetrates the level.

### Root Cause #2: CHoCH Detected Before BOS Due to Iteration Order

**Location**: `src/market_analysis/structure/bos_choch.py`, `_check_bullish_break()` and `_check_bearish_break()`

**Problem**: The algorithm iterated through previous swings in chronological order and returned immediately on first match. If multiple types of break were possible, the wrong type could be detected first.

**Example**: For a bullish swing breaking structure:

- It would find swing_high breaks (BOS) chronologically first, then swing_low breaks (CHoCH)
- But in some scenarios, the most recent level of each type matters, not the first found

**Fix**: Modified to collect all candidates and return most recent BOS candidate if available:

```python
# Collect all candidates first
bos_candidates = []
choch_candidates = []
for prev in prev_swings:
    if prev.pivot_type.value == "swing_high" and is_bullish:
        if self._is_level_broken(swing, prev, data, is_bullish=True):
            bos_candidates.append((prev, strength))
    elif prev.pivot_type.value == "swing_low" and is_bullish:
        if self._is_level_broken(swing, prev, data, is_bullish=True):
            choch_candidates.append((prev, strength))

# BOS takes priority
if bos_candidates:
    return (most_recent_bos, True)
if choch_candidates:
    return (most_recent_choch, False)
```

### Root Cause #3: Duplicate Events from Nested Loop Structure

**Location**: `src/market_analysis/structure/bos_choch.py`, `classify()` method

**Problem**: The nested loop structure `for i in range(1, len(swings))` with inner loop `for current in current_swings` caused the same break to be detected multiple times as `prev_swings` grew with each iteration.

**Fix**: Added duplicate detection set:

```python
detected_breaks: set[tuple[int, int]] = set()
# ...
pair = (current.index, event.broken_level.pivot.index)
if pair not in detected_breaks:
    detected_breaks.add(pair)
    # process event
```

## Data-Driven Justification

### Why Candle Close Must Be Beyond Level

In scenario 046 "No break - wide oscillation":

- Price oscillates between roughly 146 and 153
- When price approaches a previous level, only the wick may penetrate
- The close must be beyond the level to confirm a true break

Without close confirmation, the classifier produces false positives on:

- Fakeouts where price spikes through level but reverses
- Wick-only penetrations that don't constitute true breaks

### Why BOS Must Take Priority Over CHoCH

In scenarios 015, 018, 024 (all expect bearish BOS):

- The market is in a downtrend
- When a swing_low breaks a previous swing_low, that's BOS (continuation)
- When a swing_low breaks a previous swing_high, that's CHoCH (reversal)

In a clear downtrend with sequential lower lows, BOS should be detected. But the original algorithm could detect CHoCH first if the swing_high level was encountered before the relevant swing_low level in iteration order.

## Current Status

After fixes:

- Aggregate directional accuracy: **PASSES** (above 40% No-Go threshold)
- Bullish BOS scenarios: **PASSES**
- Bearish BOS scenarios: **FAILS** (0% accuracy - still investigating)
- No-break scenarios: **FAILS** (0% accuracy - still investigating)

The remaining failures appear to be due to:

1. The test expectations may be based on different definitions of BOS/CHoCH
2. The scenario data may not have sufficient volatility to trigger breaks as defined
3. The swing pivot detection may be missing critical pivots in gradual trends

## Files Modified

- `src/market_analysis/structure/bos_choch.py`
  - `_is_level_broken()` - now uses OHLCV candle data
  - `_check_bullish_break()` - collects candidates and prioritizes BOS
  - `_check_bearish_break()` - collects candidates and prioritizes BOS
  - `classify()` - added duplicate detection

## Test Results

```
PASSED: test_bos_choch_scenario_001 - Bullish BOS - clean uptrend
PASSED: test_bos_choch_scenario_002 - Bullish BOS - trend continuation
PASSED: test_bos_choch_scenario_005 - Ranging market - no break
PASSED: test_bos_choch_scenario_010 - Minor pullback in uptrend - no BOS
PASSED: test_bos_choch_scenario_028 - Flat market with micro oscillations
PASSED: test_directional_accuracy_above_no_go (aggregate)
PASSED: test_minimum_scenarios
PASSED: test_bullish_bos_scenarios_pass

FAILED: test_bos_choch_scenario_015 - Bearish BOS - gradual decline
FAILED: test_bos_choch_scenario_018 - Bearish BOS - distribution top
FAILED: test_bos_choch_scenario_024 - Bearish BOS - tight range
FAILED: test_bos_choch_scenario_039 - Bearish CHoCH - double top
FAILED: test_bos_choch_scenario_046 - No break - wide oscillation
FAILED: test_bearish_bos_scenarios_pass
FAILED: test_no_break_scenarios_pass
```

## Next Steps for AC-3 (≥60% detection)

1. Investigate why bearish BOS scenarios fail (detected as bullish direction)
2. Investigate why no-break scenarios detect false breaks
3. Consider adjusting swing pivot detector parameters for gradual trends
4. Review scenario expectations for alignment with algorithm behavior
