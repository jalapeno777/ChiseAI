"""Premium/Discount Zones Module.

ICT premium and discount zones are determined relative to fair value,
which can be calculated using Volume Profile POC or VWAP.

- Premium zone: price above fair value (overbought, look for shorts)
- Discount zone: price below fair value (oversold, look for longs)
- Equilibrium zone: price near fair value (neutral)

Zone classification refreshes every 5 minutes by default.
"""

from src.ict.zones.classifier import (
    FairValueMethod,
    FairValueResult,
    PremiumDiscountClassifier,
    ZoneClassification,
    ZoneType,
)

__all__ = [
    "FairValueMethod",
    "FairValueResult",
    "PremiumDiscountClassifier",
    "ZoneClassification",
    "ZoneType",
]
