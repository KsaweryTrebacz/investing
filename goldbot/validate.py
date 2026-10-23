"""Walk-forward: ocena strategii z i bez reżimu na okresie do strojenia i okresie kontrolnym."""
import backtest
from config import Costs
from strategy import Params


def walk_forward(df, p: Params = Params(), split: float = 0.7, costs: Costs | None = None,
                 expire_hours: float | None = 48) -> dict:
    """df: wynik pipeline.prepare. Pierwsze `split` świec to okres do strojenia, reszta to kontrolny.

    Wskaźniki są policzone na całości (są przyczynowe), więc podział nie wprowadza wycieku.
    Warianty `_bez_rezimu` handlują surowy sygnał M15, żeby zobaczyć, czy reżim cokolwiek daje.
    """
    k = int(len(df) * split)
    res = {}
    for name, part in (("in_sample", df.iloc[:k]), ("out_of_sample", df.iloc[k:])):
        part = part.reset_index(drop=True)
        res[name] = backtest.run(part, p, costs=costs, expire_hours=expire_hours)[1]
        res[f"{name}_bez_rezimu"] = backtest.run(part.assign(signal=part["signal_raw"]), p, costs=costs,
                                                 expire_hours=expire_hours)[1]
    return res
