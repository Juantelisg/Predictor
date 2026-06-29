"""Resolución de nombres de selección -> dataset (alias de nombres cortos/nativos de Linemate)."""
import soccer

TEAMS = {"Turkey", "United States", "Germany", "Spain", "South Korea", "DR Congo", "Curaçao"}


def test_linemate_short_names_resolve():
    assert soccer.resolve("Turkiye", TEAMS) == "Turkey"        # nombre nativo de Linemate
    assert soccer.resolve("USA", TEAMS) == "United States"     # abreviatura, sin match por similitud


def test_exact_and_spanish_alias():
    assert soccer.resolve("Germany", TEAMS) == "Germany"
    assert soccer.resolve("espana", TEAMS) == "Spain"
    assert soccer.resolve("estados unidos", TEAMS) == "United States"


def test_accent_insensitive():
    assert soccer.resolve("Curacao", TEAMS) == "Curaçao"
