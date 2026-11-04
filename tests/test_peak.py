"""Testes do aviso de horário peak da DeepSeek."""

from datetime import datetime, timezone

import pytest

from src.main import esta_em_horario_peak_deepseek


def utc(ano, mes, dia, hora, minuto=0):
    return datetime(ano, mes, dia, hora, minuto, tzinfo=timezone.utc)


# 2026-11-02 é segunda-feira; 2026-11-07 sábado; 2026-11-08 domingo.
@pytest.mark.parametrize(
    "momento,esperado",
    [
        (utc(2026, 11, 2, 0, 59), False),   # segunda, antes do 1º bloco
        (utc(2026, 11, 2, 1, 0), True),     # início do 1º bloco
        (utc(2026, 11, 2, 2, 30), True),    # dentro do 1º bloco
        (utc(2026, 11, 2, 4, 0), False),    # fim do 1º bloco
        (utc(2026, 11, 2, 5, 59), False),   # intervalo
        (utc(2026, 11, 2, 6, 0), True),     # início do 2º bloco
        (utc(2026, 11, 2, 9, 59), True),    # dentro do 2º bloco
        (utc(2026, 11, 2, 10, 0), False),   # fim do 2º bloco
        (utc(2026, 11, 2, 12, 0), False),   # off-peak
        (utc(2026, 11, 7, 2, 0), False),    # sábado
        (utc(2026, 11, 8, 7, 0), False),    # domingo
    ],
)
def test_horario_peak(momento, esperado):
    assert esta_em_horario_peak_deepseek(momento) is esperado
