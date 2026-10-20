"""Złożenie całości: świece M15 + D1 + makro -> ramka z sygnałami bramkowanymi reżimem."""
from regime import attach_regime, build_regime
from strategy import Params, add_signals, gate_by_regime


def prepare(m15, d1, usd=None, yld=None, p: Params = Params()):
    sig = add_signals(m15, p)
    reg = build_regime(d1, usd, yld)
    return gate_by_regime(attach_regime(sig, reg))
