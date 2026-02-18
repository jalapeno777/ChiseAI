"""Fill model for paper trading order execution simulation.

Provides realistic fill price calculation and slippage modeling
for paper trading simulations.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.paper.models import OrderSide, OrderType, PaperOrder

logger = logging.getLogger(__name__)

# Import new market realism models
try:
    from execution.paper.slippage_model import SlippageModel, SlippageConfig
    from execution.paper.latency_model import LatencyModel, LatencyConfig
    from execution.paper.market_impact import MarketImpact, MarketImpactConfig
    from execution.paper.fill_probability import FillProbability, FillProbabilityConfig
    from execution.paper.config_loader import MarketRealismConfig

    MARKET_REALISM_AVAILABLE = True
except ImportError:
    MARKET_REALISM_AVAILABLE = False
    logger.warning("Market realism models not available, using legacy fill model")


@dataclass
class FillModelConfig:
    """Configuration for fill model behavior.

    Attributes:
        base_slippage_bps: Base slippage in basis points (default 5 bps = 0.05%)
        volatility_factor: Multiplier for volatility-based slippage
        max_slippage_bps: Maximum allowed slippage
        min_fill_delay_ms: Minimum fill delay in milliseconds
        max_fill_delay_ms: Maximum fill delay in milliseconds
        partial_fill_probability: Probability of partial fill (0.0-1.0)
        market_order_fill_probability: Probability of immediate fill for market orders
        use_market_realism: Whether to use new market realism models
        symbol: Trading symbol for per-symbol config lookup
        exchange: Exchange name for per-exchange config lookup
    """

    base_slippage_bps: float = 5.0
    volatility_factor: float = 1.0
    max_slippage_bps: float = 50.0  # 0.5% max slippage
    min_fill_delay_ms: float = 50.0
    max_fill_delay_ms: float = 200.0
    partial_fill_probability: float = 0.1
    market_order_fill_probability: float = 0.95
    use_market_realism: bool = True
    symbol: str | None = None
    exchange: str | None = None
    market_data: dict[str, Any] = field(default_factory=dict)


class FillModel:
    """Models realistic order fills for paper trading.

    Calculates fill prices with slippage and simulates fill delays.
    Provides deterministic fills for reproducible backtesting.

    Supports both legacy fill model and new market realism models
    (SlippageModel, LatencyModel, MarketImpact, FillProbability).
    """

    def __init__(self, config: FillModelConfig | None = None, seed: int | None = None):
        """Initialize fill model.

        Args:
            config: Fill model configuration
            seed: Random seed for reproducible fills
        """
        self.config = config or FillModelConfig()
        self._rng = random.Random(seed)

        # Initialize market realism models if enabled and available
        self._slippage_model: SlippageModel | None = None
        self._latency_model: LatencyModel | None = None
        self._market_impact: MarketImpact | None = None
        self._fill_probability: FillProbability | None = None
        self._config_loader: MarketRealismConfig | None = None

        if self.config.use_market_realism and MARKET_REALISM_AVAILABLE:
            self._init_market_realism_models()

        logger.info(
            f"FillModel initialized: base_slippage={self.config.base_slippage_bps}bps, "
            f"use_market_realism={self.config.use_market_realism}, seed={seed}"
        )

    def _init_market_realism_models(self) -> None:
        """Initialize market realism models with configuration."""
        try:
            # Load configuration
            self._config_loader = MarketRealismConfig()

            symbol = self.config.symbol
            exchange = self.config.exchange

            # Initialize models with appropriate configs
            slippage_config = self._config_loader.get_slippage_config(symbol)
            self._slippage_model = SlippageModel(slippage_config)

            latency_config = self._config_loader.get_latency_config(exchange)
            self._latency_model = LatencyModel(
                latency_config, seed=self._rng.randint(0, 2**31)
            )

            impact_config = self._config_loader.get_market_impact_config(symbol)
            self._market_impact = MarketImpact(impact_config)

            prob_config = self._config_loader.get_fill_probability_config()
            self._fill_probability = FillProbability(
                prob_config, seed=self._rng.randint(0, 2**31)
            )

            logger.info(
                f"Market realism models initialized for symbol={symbol}, exchange={exchange}"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize market realism models: {e}")
            self._slippage_model = None
            self._latency_model = None
            self._market_impact = None
            self._fill_probability = None

    def calculate_fill_price(
        self,
        order: PaperOrder,
        market_price: float,
        volatility: float = 0.0,
    ) -> float:
        """Calculate realistic fill price with slippage.

        Args:
            order: The order being filled
            market_price: Current market price
            volatility: Current volatility as decimal (e.g., 0.02 = 2%)

        Returns:
            Fill price with slippage applied
        """
        # Calculate base slippage in price terms
        base_slippage_pct = self.config.base_slippage_bps / 10000

        # Add volatility-based slippage
        volatility_slippage = volatility * self.config.volatility_factor

        # Total slippage
        total_slippage_pct = base_slippage_pct + volatility_slippage

        # Cap at max slippage
        max_slippage_pct = self.config.max_slippage_bps / 10000
        total_slippage_pct = min(total_slippage_pct, max_slippage_pct)

        # Apply slippage based on order side
        # Buy orders fill higher, sell orders fill lower
        if order.side.value == "buy":
            fill_price = market_price * (1 + total_slippage_pct)
        else:
            fill_price = market_price * (1 - total_slippage_pct)

        # Add small random variation (-10% to +10% of slippage)
        variation = self._rng.uniform(-0.1, 0.1) * total_slippage_pct
        fill_price = fill_price * (1 + variation)

        logger.debug(
            f"Fill price for {order.symbol}: market={market_price:.2f}, "
            f"fill={fill_price:.2f}, slippage={total_slippage_pct * 100:.3f}%"
        )

        return fill_price

    def calculate_fill_delay_ms(self) -> float:
        """Calculate simulated fill delay.

        Returns:
            Fill delay in milliseconds
        """
        return self._rng.uniform(
            self.config.min_fill_delay_ms,
            self.config.max_fill_delay_ms,
        )

    def should_fill_immediately(self, order: PaperOrder) -> bool:
        """Determine if order should fill immediately.

        Args:
            order: The order to check

        Returns:
            True if order should fill immediately
        """
        if order.order_type.value == "market":
            return self._rng.random() < self.config.market_order_fill_probability

        # Limit orders may not fill immediately depending on price
        return False

    def calculate_partial_fill_quantity(
        self,
        order: PaperOrder,
        available_liquidity: float,
    ) -> float:
        """Calculate partial fill quantity.

        Args:
            order: The order being filled
            available_liquidity: Available market liquidity

        Returns:
            Quantity to fill (may be less than order quantity)
        """
        # Determine if partial fill should occur
        if self._rng.random() > self.config.partial_fill_probability:
            # Full fill (or as much as liquidity allows)
            return min(order.quantity, available_liquidity)

        # Partial fill - random portion of order
        fill_ratio = self._rng.uniform(0.1, 0.9)
        partial_quantity = order.quantity * fill_ratio

        # Cap at available liquidity
        return min(partial_quantity, available_liquidity)

    def calculate_fee(self, notional_value: float, fee_rate: float = 0.0006) -> float:
        """Calculate trading fee.

        Args:
            notional_value: Value of the fill
            fee_rate: Fee rate as decimal (default 0.06% = 0.0006)

        Returns:
            Fee amount
        """
        return notional_value * fee_rate

    def reset_seed(self, seed: int) -> None:
        """Reset random seed for reproducible fills.

        Args:
            seed: New random seed
        """
        self._rng = random.Random(seed)
        logger.debug(f"FillModel seed reset to {seed}")

    # =========================================================================
    # Market Realism Model Integration Methods
    # =========================================================================

    def calculate_fill_price_realistic(
        self,
        order: PaperOrder,
        market_price: float,
        market_data: dict[str, Any] | None = None,
    ) -> float:
        """Calculate realistic fill price using SlippageModel and MarketImpact.

        Args:
            order: The order being filled
            market_price: Current market price
            market_data: Market data for slippage/impact calculation

        Returns:
            Fill price with slippage and market impact applied
        """
        if not self._slippage_model:
            # Fall back to legacy calculation
            return self.calculate_fill_price(order, market_price)

        # Use market data from config if not provided
        if market_data is None:
            market_data = self.config.market_data or {}

        # Calculate slippage
        slippage = self._slippage_model.calculate_slippage(
            symbol=order.symbol,
            order_size=order.quantity,
            side=order.side,
            market_data=market_data,
        )

        # Apply slippage to get base fill price
        fill_price = self._slippage_model.apply_slippage_to_price(
            price=market_price,
            slippage=slippage,
            side=order.side,
        )

        # Add market impact for large orders
        if self._market_impact:
            adv = market_data.get("avg_daily_volume", 0.0)
            volatility = market_data.get("volatility", 0.0)

            if adv > 0:
                impact_price = self._market_impact.estimate_price_impact(
                    price=fill_price,
                    order_size=order.quantity,
                    adv=adv,
                    volatility=volatility,
                    is_buy=(order.side.value == "buy"),
                )
                fill_price = impact_price

        logger.debug(
            f"Realistic fill price for {order.symbol}: market={market_price:.2f}, "
            f"fill={fill_price:.2f}, slippage={slippage * 10000:.2f}bps"
        )

        return fill_price

    def simulate_latency_ms(self, latency_type: str = "total") -> float:
        """Simulate latency using LatencyModel.

        Args:
            latency_type: Type of latency ("submission", "fill", "total")

        Returns:
            Simulated latency in milliseconds
        """
        if not self._latency_model:
            # Fall back to legacy calculation
            return self.calculate_fill_delay_ms()

        if latency_type == "submission":
            return self._latency_model.simulate_order_submission_latency()
        elif latency_type == "fill":
            return self._latency_model.simulate_fill_notification_latency()
        else:
            return self._latency_model.simulate_total_latency()

    def should_fill_realistic(
        self,
        order: PaperOrder,
        mid_price: float,
        book_depth: float = 0.0,
    ) -> bool:
        """Determine if order should fill using FillProbability model.

        Args:
            order: The order to check
            mid_price: Current mid price
            book_depth: Available book depth at relevant price level

        Returns:
            True if order should be filled
        """
        if not self._fill_probability:
            # Fall back to legacy calculation
            return self.should_fill_immediately(order)

        return self._fill_probability.should_fill(
            order_type=order.order_type,
            limit_price=order.price,
            mid_price=mid_price,
            book_depth=book_depth,
            order_size=order.quantity,
        )

    def calculate_fill_probability(
        self,
        order: PaperOrder,
        mid_price: float,
        book_depth: float = 0.0,
        time_elapsed_ms: float = 0.0,
    ) -> float:
        """Calculate fill probability for an order.

        Args:
            order: The order to check
            mid_price: Current mid price
            book_depth: Available book depth
            time_elapsed_ms: Time elapsed since order submission

        Returns:
            Fill probability (0.0-1.0)
        """
        if not self._fill_probability:
            # Legacy: market orders have high probability
            if order.order_type.value == "market":
                return self.config.market_order_fill_probability
            return 0.0

        return self._fill_probability.calculate_fill_probability(
            order_type=order.order_type,
            limit_price=order.price,
            mid_price=mid_price,
            book_depth=book_depth,
            order_size=order.quantity,
            time_elapsed_ms=time_elapsed_ms,
        )

    def get_latency_statistics(self, samples: int = 10000) -> dict:
        """Get latency statistics from LatencyModel.

        Args:
            samples: Number of samples for statistics

        Returns:
            Dictionary with latency statistics
        """
        if not self._latency_model:
            return {
                "legacy": {
                    "min": self.config.min_fill_delay_ms,
                    "max": self.config.max_fill_delay_ms,
                    "mean": (
                        self.config.min_fill_delay_ms + self.config.max_fill_delay_ms
                    )
                    / 2,
                }
            }

        return self._latency_model.get_statistics(samples)

    def get_slippage_config(self) -> dict:
        """Get current slippage configuration.

        Returns:
            Dictionary with slippage configuration
        """
        if self._slippage_model:
            config = self._slippage_model.get_config()
            return {
                "base_slippage_bps": config.base_slippage_bps,
                "volatility_factor": config.volatility_factor,
                "min_slippage_bps": config.min_slippage_bps,
                "max_slippage_bps": config.max_slippage_bps,
            }
        return {
            "base_slippage_bps": self.config.base_slippage_bps,
            "volatility_factor": self.config.volatility_factor,
            "max_slippage_bps": self.config.max_slippage_bps,
        }

    def get_market_impact_config(self) -> dict:
        """Get current market impact configuration.

        Returns:
            Dictionary with market impact configuration
        """
        if self._market_impact:
            config = self._market_impact.get_config()
            return {
                "base_coefficient": config.base_coefficient,
                "volatility_sensitivity": config.volatility_sensitivity,
                "adv_threshold": config.adv_threshold,
            }
        return {"base_coefficient": 1.0, "adv_threshold": 0.001}
