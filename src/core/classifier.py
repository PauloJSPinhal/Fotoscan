"""
Classificador de imagens do FotoScan.

Responsável por carregar as categorias e critérios de classificação, validar
o que o modelo devolve e orquestrar a chamada ao cliente Ollama.

Este módulo não fala HTTP diretamente: delega sempre em `src.api.client.OllamaClient`.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.api.client import OllamaClient

logger = logging.getLogger(__name__)

__all__ = ["Classifier", "OllamaClient", "load_categories", "load_criteria"]


# ---------------------------------------------------------------- carregamento
def load_categories(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Lê o ficheiro de categorias e devolve uma lista normalizada.

    Aceita os dois formatos usados no projeto:

    * ``{"categories": ["Paisagem", "Retrato"]}`` — lista simples de nomes;
    * ``{"groups": [...], "categories": [{"name": ..., "groupId": ...}]}`` — o
      formato completo de ``config/categories.json``.
    """
    caminho = Path(path)
    if not caminho.is_file():
        raise FileNotFoundError(f"Ficheiro de categorias não encontrado: {caminho}")

    with open(caminho, "r", encoding="utf-8") as ficheiro:
        dados = json.load(ficheiro)

    grupos = {g.get("id"): g.get("name", g.get("id")) for g in dados.get("groups", [])}
    categorias: List[Dict[str, Any]] = []

    for item in dados.get("categories", []):
        if isinstance(item, str):
            categorias.append({"name": item.strip(), "description": "", "group": ""})
            continue
        if not isinstance(item, dict):
            continue
        nome = str(item.get("name", "")).strip()
        if not nome:
            continue
        gid = item.get("groupId") or item.get("group") or ""
        categorias.append(
            {
                "name": nome,
                "description": str(item.get("description", "")).strip(),
                "group": grupos.get(gid, gid),
            }
        )

    return categorias


def load_criteria(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Lê o ficheiro de critérios e devolve sempre um dicionário com a chave ``rules``.

    Aceita ``{"rules": {...}}`` ou o formato plano ``{"Pessoas": "descrição"}``
    usado em ``config/criteria.json``.
    """
    caminho = Path(path)
    if not caminho.is_file():
        raise FileNotFoundError(f"Ficheiro de critérios não encontrado: {caminho}")

    with open(caminho, "r", encoding="utf-8") as ficheiro:
        dados = json.load(ficheiro)

    if isinstance(dados, dict) and "rules" in dados:
        return dict(dados)
    return {"rules": dict(dados)}


# ---------------------------------------------------------------- classificador
class Classifier:
    """Carrega as referências de classificação e valida as respostas do modelo."""

    def __init__(
        self,
        categories_path: Union[str, Path],
        criteria_path: Union[str, Path],
    ) -> None:
        self.categories_data = load_categories(categories_path)
        self.categories: List[str] = [c["name"] for c in self.categories_data]
        self.criteria = load_criteria(criteria_path)

        if not self.categories:
            raise ValueError(f"Nenhuma categoria válida em: {categories_path}")

    # ------------------------------------------------------------ validação
    def sanitize_category(self, raw_category: Any) -> str:
        """
        Normaliza a categoria devolvida pelo modelo.

        Remove espaços e quebras de linha e devolve o nome canónico da lista
        quando existe correspondência sem distinção de maiúsculas/minúsculas.
        """
        texto = str(raw_category or "").strip()
        if not texto:
            return ""

        for nome in self.categories:
            if nome.casefold() == texto.casefold():
                return nome
        return texto

    def is_valid_category(self, category: Any) -> bool:
        """Indica se a categoria pertence à lista oficial."""
        return self.sanitize_category(category) in self.categories

    # ------------------------------------------------------------ execução
    def process(
        self,
        image_path: Union[str, Path],
        client: Optional[OllamaClient] = None,
    ) -> Dict[str, Any]:
        """
        Classifica uma imagem e valida o resultado antes de o devolver.

        Args:
            image_path: Caminho da imagem.
            client: Cliente Ollama a usar; se omitido, cria um com os valores padrão.

        Returns:
            Dict com ``category``, ``confidence`` e ``description``.
        """
        cliente = client or OllamaClient()
        caminho = Path(image_path)

        resultado = cliente.classify_image(caminho)

        if not isinstance(resultado, dict):
            raise RuntimeError(f"Resposta inesperada do modelo: {resultado!r}")

        categoria = self.sanitize_category(resultado.get("category", ""))
        if categoria not in self.categories:
            logger.warning(
                "Categoria inválida devolvida pelo modelo (%r); a usar a primeira da lista.",
                resultado.get("category"),
            )
            categoria = self.categories[0]

        try:
            confianca = float(resultado.get("confidence", 0.0))
        except (TypeError, ValueError):
            confianca = 0.0
        confianca = min(max(confianca, 0.0), 1.0)

        return {
            "category": categoria,
            "confidence": confianca,
            "description": str(resultado.get("description", "")).strip(),
        }
