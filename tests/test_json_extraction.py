"""Testes da extração tolerante de JSON devolvido pelo modelo."""

import pytest

from src.main import extrair_json_resposta


@pytest.mark.parametrize(
    "entrada",
    [
        '{"titulo":"A","descricao":"B","categorias":["x"]}',
        '```json\n{"titulo":"A","descricao":"B","categorias":["x"]}\n```',
        'Claro! Aqui está: {"titulo":"A","descricao":"B","categorias":["x"]} Fim.',
        '{"titulo":"A","descricao":"B","categorias":["x',
    ],
)
def test_extrai_json_mesmo_com_ruido(entrada):
    resultado = extrair_json_resposta(entrada)
    assert resultado["titulo"] == "A"
    assert resultado["categorias"] == ["x"]


def test_json_invalido_falha_com_erro_claro():
    with pytest.raises(ValueError):
        extrair_json_resposta("isto não é json de todo")
