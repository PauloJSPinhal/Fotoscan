"""Testes das retentativas automáticas na obtenção de JSON do modelo."""

from unittest.mock import patch

import pytest

from src.main import obter_json_modelo, obter_json_modelo_com_fallback

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


def test_rate_limit_nao_repite_mesmo_modelo():
    chamadas = []

    def falso_chamar(url, modelo, prompt, b64, opcoes, api_key=""):
        chamadas.append(modelo)
        raise RuntimeError("DeepSeek devolveu HTTP 429: rate limit")

    with patch("src.main.chamar_modelo", side_effect=falso_chamar), \
         patch("src.main.time.sleep"):
        with pytest.raises(RuntimeError, match="429"):
            obter_json_modelo("http://x", "m", "p", "img", {}, tentativas=5)

    assert len(chamadas) == 1  # não repete o mesmo modelo em caso de 429


def test_fallback_troca_de_modelo_em_rate_limit():
    def falso_chamar(url, modelo, prompt, b64, opcoes, api_key=""):
        if modelo == "m1":
            raise RuntimeError("DeepSeek devolveu HTTP 429: rate limit")
        return JSON_OK

    with patch("src.main.chamar_modelo", side_effect=falso_chamar), \
         patch("src.main.time.sleep"):
        conteudo, usado, tentativa = obter_json_modelo_com_fallback(
            "http://x", ["m1", "m2"], "p", "img", {}
        )

    assert usado == "m2"
    assert tentativa == 1
    assert conteudo["titulo"] == "A"


def test_fallback_esgota_todos_e_lanca_erro():
    def falso_chamar(url, modelo, prompt, b64, opcoes, api_key=""):
        raise RuntimeError("DeepSeek devolveu HTTP 429: rate limit")

    with patch("src.main.chamar_modelo", side_effect=falso_chamar), \
         patch("src.main.time.sleep"):
        with pytest.raises(RuntimeError, match="429"):
            obter_json_modelo_com_fallback("http://x", ["m1", "m2"], "p", "img", {})
