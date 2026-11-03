"""Testes das retentativas automáticas na obtenção de JSON do modelo."""

from unittest.mock import patch

import pytest

from src.main import obter_json_modelo

JSON_OK = '{"titulo":"A","descricao":"B","categorias":["x"]}'


def test_sucesso_a_primeira():
    with patch("src.main.chamar_modelo", return_value=JSON_OK) as mock_chamar:
        conteudo, tentativa = obter_json_modelo("http://x", "m", "p", "img", {})
    assert tentativa == 1
    assert conteudo["titulo"] == "A"
    assert mock_chamar.call_count == 1


def test_recupera_de_resposta_vazia():
    respostas = iter(["", JSON_OK])
    with patch("src.main.chamar_modelo", side_effect=lambda *a, **k: next(respostas)), \
         patch("src.main.time.sleep"):
        conteudo, tentativa = obter_json_modelo("http://x", "m", "p", "img", {})
    assert tentativa == 2
    assert conteudo["categorias"] == ["x"]


def test_ultima_tentativa_desliga_formato_json():
    capturadas = []

    def falso_chamar(url, modelo, prompt, b64, opcoes, api_key=""):
        capturadas.append(dict(opcoes))
        if len(capturadas) < 3:
            return ""
        return JSON_OK

    with patch("src.main.chamar_modelo", side_effect=falso_chamar), \
         patch("src.main.time.sleep"):
        conteudo, tentativa = obter_json_modelo("http://x", "m", "p", "img", {}, tentativas=3)

    assert tentativa == 3
    assert capturadas[0].get("texto_livre") is None
    assert capturadas[1].get("texto_livre") is None
    assert capturadas[2].get("texto_livre") is True


def test_esgota_tentativas_e_lanca_ultimo_erro():
    with patch("src.main.chamar_modelo", return_value=""), \
         patch("src.main.time.sleep"):
        with pytest.raises(ValueError, match="JSON válido"):
            obter_json_modelo("http://x", "m", "p", "img", {}, tentativas=3)
