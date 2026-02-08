import pytest

from chiseai.risk import size_notional_for_stop_loss


def test_size_notional_for_stop_loss_basic() -> None:
    # Portfolio 10k, risk 1% => $100. Stop loss 2% away => notional $5,000.
    res = size_notional_for_stop_loss(
        portfolio_usd=10_000,
        entry_price=100.0,
        stop_loss_price=98.0,
        max_risk_fraction=0.01,
    )
    assert res.risk_usd == pytest.approx(100.0)
    assert res.notional_usd == pytest.approx(5_000.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(portfolio_usd=0, entry_price=100, stop_loss_price=99),
        dict(portfolio_usd=10_000, entry_price=0, stop_loss_price=99),
        dict(portfolio_usd=10_000, entry_price=100, stop_loss_price=0),
        dict(portfolio_usd=10_000, entry_price=100, stop_loss_price=100),
        dict(
            portfolio_usd=10_000,
            entry_price=100,
            stop_loss_price=99,
            max_risk_fraction=0,
        ),
    ],
)
def test_size_notional_for_stop_loss_validation(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        size_notional_for_stop_loss(**kwargs)
