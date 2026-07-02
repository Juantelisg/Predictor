"""Maquina +EV multi-book de props: fair de consenso (mediana de-vig), mejor precio, Beta-Binomial
shrunk, y la regla de 2 senales (mercado +EV Y hit-rate propio corrobora)."""
import prop_value


def test_consensus_fair_median():
    books = {"a": {"over": 2.0, "under": 2.0}, "b": {"over": 1.9, "under": 2.1},
             "c": {"over": 2.1, "under": 1.9}}
    fo, fu, n = prop_value._consensus_fair(books)
    assert n == 3 and abs(fo + fu - 1.0) < 1e-9 and abs(fo - 0.5) < 0.05


def test_consensus_needs_min_books():
    books = {"a": {"over": 2.0, "under": 2.0}, "b": {"over": 2.0, "under": 2.0}}   # solo 2 pares
    assert prop_value._consensus_fair(books) is None


def test_consensus_ignores_one_sided_books():
    books = {"a": {"over": 2.0, "under": 2.0}, "b": {"over": 2.0, "under": 2.0},
             "c": {"over": 2.5}}                                   # c no aporta al de-vig (sin under)
    assert prop_value._consensus_fair(books) is None              # solo 2 pares completos -> None


def test_best_price_is_highest():
    books = {"a": {"over": 2.0}, "b": {"over": 2.5}, "c": {"under": 1.8}}
    assert prop_value._best_price(books, "over") == 2.5
    assert prop_value._best_price(books, "under") == 1.8


def test_shrunk_hitrate_toward_half():
    # 18/20 = 90% crudo -> shrunk hacia 0.5 con K=30: (18+15)/(20+30) = 0.66
    assert abs(prop_value._shrunk_hitrate(18, 20) - 0.66) < 1e-9
    assert prop_value._shrunk_hitrate(0, 0) is None


def test_evaluate_flags_book_disagreement():
    # 3 books en 2.0/2.0 (fair 0.5) + un book pagando over a 2.5 (implied 0.40) -> edge 0.10 > 4%.
    # hit-rate season 60% (games 20) corrobora el over -> FLAG.
    books = {"a": {"over": 2.0, "under": 2.0}, "b": {"over": 2.0, "under": 2.0},
             "c": {"over": 2.0, "under": 2.0}, "d": {"over": 2.5}}
    row = {"who": "X", "market": "SHOTS", "line": 0.5, "books": books, "game": "g", "team": "T",
           "splits": {"SEASON": 60}, "games_season": 20}
    res = prop_value.evaluate_prop(row)
    over = next(r for r in res if r["side"] == "over")
    assert over["verdict"] == "FLAG"
    assert over["best_odds"] == 2.5 and over["edge"] >= 0.04


def test_evaluate_pasar_efficient_market():
    # mercado eficiente (todos 2.0/2.0): sin edge -> PASAR
    books = {k: {"over": 2.0, "under": 2.0} for k in ("a", "b", "c", "d")}
    row = {"who": "X", "market": "SHOTS", "line": 0.5, "books": books, "game": "g", "team": "T",
           "splits": {"SEASON": 55}, "games_season": 20}
    res = prop_value.evaluate_prop(row)
    assert all(r["verdict"].startswith("PASAR") for r in res)


def test_evaluate_no_consensus_returns_empty():
    row = {"who": "X", "market": "SHOTS", "line": 0.5, "game": "g", "team": "T",
           "books": {"a": {"over": 2.0, "under": 2.0}}, "splits": {"SEASON": 55}, "games_season": 20}
    assert prop_value.evaluate_prop(row) == []


def test_flag_requires_corroboration():
    # edge de mercado alto pero el hit-rate propio contradice (season 5%, over improbable) -> NO FLAG
    books = {"a": {"over": 2.0, "under": 2.0}, "b": {"over": 2.0, "under": 2.0},
             "c": {"over": 2.0, "under": 2.0}, "d": {"over": 2.5}}
    row = {"who": "X", "market": "SHOTS", "line": 0.5, "books": books, "game": "g", "team": "T",
           "splits": {"SEASON": 5}, "games_season": 20}
    res = prop_value.evaluate_prop(row)
    over = next(r for r in res if r["side"] == "over")
    assert over["verdict"] == "PASAR-sin-corrob"    # mercado ve +EV pero el modelo no lo apoya
