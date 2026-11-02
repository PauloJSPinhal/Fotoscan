"""
Módulo de Testes Unitários para o Classificador de Imagens (Classifier).

Este módulo utiliza a framework pytest para validar:
1. O carregamento e validação de configurações locais (categories.json e criteria.json).
2. A sanitização e validação das categorias devolvidas pelo modelo.
3. O fluxo completo de classificação com recurso a mocks para isolar a API do Ollama.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Importação dos componentes principais a partir da estrutura modular em src/
from src.core.classifier import Classifier
from src.api.client import OllamaClient


@pytest.fixture
def mock_config_dir(tmp_path: Path) -> Path:
    """
    Fixture do pytest que provisiona um diretório e ficheiros de configuração temporários.

    Garante o isolamento dos testes em relação aos ficheiros reais do projeto,
    criando instâncias limpas de 'categories.json' e 'criteria.json'.
    
    Args:
        tmp_path: Objeto Path fornecido pelo pytest apontando para uma pasta temporária exclusiva.

    Returns:
        Path: Caminho para a pasta 'config' temporária criada.
    """
    # Cria o subdiretório 'config' no ambiente temporário
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Define os caminhos dos ficheiros JSON de configuração
    categories_file = config_dir / "categories.json"
    criteria_file = config_dir / "criteria.json"

    # Estruturas de dados simuladas para categorias e critérios de classificação
    categories_data = {
        "categories": ["Paisagem", "Retrato", "Arquitetura", "Documental"]
    }
    criteria_data = {
        "rules": {
            "Paisagem": "Presença dominante de elementos naturais, céu, mar ou campo.",
            "Retrato": "Foco principal numa pessoa ou grupo de pessoas."
        }
    }

    # Escrita síncrona dos ficheiros JSON com codificação UTF-8
    categories_file.write_text(json.dumps(categories_data), encoding="utf-8")
    criteria_file.write_text(json.dumps(criteria_data), encoding="utf-8")

    return config_dir


@pytest.fixture
def classifier(mock_config_dir: Path) -> Classifier:
    """
    Fixture que instancia a classe Classifier injetando as configurações temporárias.

    Args:
        mock_config_dir: Fixture que fornece o caminho para a pasta com os ficheiros de teste.

    Returns:
        Classifier: Instância do classificador devidamente inicializada.
    """
    cat_path = mock_config_dir / "categories.json"
    crit_path = mock_config_dir / "criteria.json"
    return Classifier(categories_path=cat_path, criteria_path=crit_path)


def test_load_configurations_success(classifier: Classifier):
    """
    Testa o carregamento bem-sucedido de categorias e critérios.

    Verifica se:
    - O número total de categorias carregadas coincide com a configuração fornecida.
    - Determinadas categorias esperadas constam na coleção em memória.
    - As regras de critérios estão corretamente mapeadas no dicionário interno.
    """
    # Valida a quantidade de categorias presentes
    assert len(classifier.categories) == 4

    # Valida a presença da categoria pretendida
    assert "Paisagem" in classifier.categories

    # Valida o mapeamento do critério para a categoria 'Retrato'
    assert "Retrato" in classifier.criteria["rules"]


def test_load_configurations_missing_file():
    """
    Garante que o inicializador lança FileNotFoundError quando os ficheiros não existem.

    Simula a passagem de caminhos inválidos para verificar a robustez do tratamento de erros.
    """
    with pytest.raises(FileNotFoundError):
        Classifier(
            categories_path=Path("ficheiro_inexistente.json"),
            criteria_path=Path("outro_inexistente.json")
        )


def test_validate_valid_category(classifier: Classifier):
    """
    Testa a validação e sanitização de uma categoria estritamente válida.

    Garante que uma string limpa pertencente à lista oficial é confirmada como válida.
    """
    raw_response = "Paisagem"
    clean_cat = classifier.sanitize_category(raw_response)

    # Verifica se a sanitização preserva o nome esperado
    assert clean_cat == "Paisagem"
    # Confirma se o método de validação aceita a categoria
    assert classifier.is_valid_category(clean_cat) is True


def test_validate_category_with_whitespace_and_casing(classifier: Classifier):
    """
    Testa a resiliência a variações de formatação (espaços excedentes e minúsculas).

    Garante que o parser lida com quebras de linha e espaços à volta do texto,
    normalizando a resposta gerada pelo modelo de visão.
    """
    raw_response = "  paisagem \n"
    clean_cat = classifier.sanitize_category(raw_response)

    # Verifica se os espaços foram removidos e a capitalização padronizada
    assert clean_cat.capitalize() == "Paisagem"


def test_validate_unknown_category(classifier: Classifier):
    """
    Valida a rejeição de categorias que não pertençam à lista aprovada.

    Impede que alucinações ou termos fora do domínio sejam aceites como categorias válidas.
    """
    raw_response = "Automóvel"
    assert classifier.is_valid_category(raw_response) is False


@patch.object(OllamaClient, "classify_image")
def test_classify_workflow_mocked(mock_classify: MagicMock, classifier: Classifier, tmp_path: Path):
    """
    Testa o fluxo completo de inferência e pós-processamento utilizando um mock do OllamaClient.

    Evita chamadas de rede ou dependência de uma instância local do Ollama em execução,
    garantindo testes rápidos, determinísticos e integráveis em pipelines de CI/CD.
    """
    # 1. Criação de um ficheiro de imagem simulado (dummy)
    dummy_image = tmp_path / "teste.jpg"
    dummy_image.write_bytes(b"dummy image bytes")

    # 2. Configuração do comportamento esperado do mock da API do Ollama
    mock_classify.return_value = {
        "category": "Paisagem",
        "confidence": 0.95,
        "description": "Fotografia de um campo aberto com horizonte visível."
    }

    # 3. Execução do fluxo de classificação
    mock_client = OllamaClient()
    result = classifier.process(image_path=dummy_image, client=mock_client)

    # 4. Asserções sobre o resultado retornado pelo classificador
    assert result["category"] == "Paisagem"
    assert result["confidence"] >= 0.90
    assert "description" in result

    # 5. Confirmação de que o cliente Ollama foi chamado exatamente uma vez com o caminho correto
    mock_classify.assert_called_once_with(dummy_image)