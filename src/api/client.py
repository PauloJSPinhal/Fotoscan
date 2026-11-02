"""
Módulo de comunicação com o serviço local do Ollama.

Disponibiliza o cliente OllamaClient, responsável por preparar imagens,
construir prompts multimodais e obter respostas estruturadas de inferência.

Este é o único ponto do projeto que fala HTTP com o Ollama: `src.core.classifier`
e `src.main` consomem esta classe em vez de duplicarem a lógica.
"""

import base64
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MODELO_PADRAO = "qwen2.5vl:3b"


class OllamaClient:
    """Cliente HTTP para comunicação com a API REST do Ollama."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = MODELO_PADRAO,
        timeout: int = 300,
    ) -> None:
        """
        Inicializa as configurações de ligação ao servidor Ollama.

        Args:
            base_url: Endereço base do serviço Ollama.
            model: Nome do modelo multimodal carregado no Ollama.
            timeout: Tempo limite da requisição em segundos.
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------ utilidades
    @staticmethod
    def encode_image_to_base64(image_path: Path) -> str:
        """
        Codifica uma imagem binária numa string em Base64 para envio via JSON.

        Args:
            image_path: Caminho para o ficheiro de imagem.

        Returns:
            str: Conteúdo da imagem codificado em Base64 (ASCII).

        Raises:
            FileNotFoundError: Se a imagem não for encontrada no disco.
        """
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Imagem não encontrada: {path}")

        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _get_json(self, endpoint: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """GET simples que devolve o corpo já descodificado como JSON."""
        req = urllib.request.Request(
            endpoint, headers={"User-Agent": "fotoscan/1.1"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout or 5) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_models(self) -> List[str]:
        """Devolve os nomes dos modelos instalados localmente no Ollama."""
        dados = self._get_json(f"{self.base_url}/api/tags")
        return [m.get("name", "") for m in dados.get("models", []) if m.get("name")]

    def has_model(self, model: Optional[str] = None) -> bool:
        """
        Verifica se um modelo está instalado (compara também o prefixo sem tag).

        Se a API não responder, devolve True para não bloquear a execução por
        uma falha de verificação que não impede a inferência.
        """
        alvo = (model or self.model).strip()
        try:
            instalados = self.list_models()
        except Exception:
            return True

        if alvo in instalados:
            return True
        base = alvo.split(":", 1)[0]
        return any(nome.split(":", 1)[0] == base for nome in instalados)

    def is_available(self) -> bool:
        """Indica se o servidor Ollama está a responder."""
        try:
            self._get_json(f"{self.base_url}/api/version", timeout=3)
            return True
        except Exception:
            return False

    def unload_model(self, model: Optional[str] = None) -> None:
        """Descarrega o modelo da RAM/VRAM imediatamente (`keep_alive: 0`)."""
        payload = {"model": model or self.model, "keep_alive": 0}
        dados = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=dados,
            headers={"Content-Type": "application/json", "User-Agent": "fotoscan/1.1"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30):
                pass
        except Exception as err:
            logger.debug("Não foi possível descarregar o modelo %s: %s", model, err)

    # ------------------------------------------------------------ prompt
    def _build_prompt(
        self,
        categories: Optional[List[str]] = None,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Monta as instruções do sistema orientando o modelo a devolver JSON estrito.

        Args:
            categories: Lista opcional de categorias permitidas.
            criteria: Regras ou critérios específicos associados a cada categoria.

        Returns:
            str: Prompt contextual formatado.
        """
        prompt = (
            "Analisa a imagem fornecida e classifica-a de acordo com as regras.\n"
            "Responde ESTRITAMENTE em formato JSON com o seguinte esquema:\n"
            "{\n"
            '  "category": "NomeDaCategoria",\n'
            '  "confidence": 0.95,\n'
            '  "description": "Breve explicação objetiva da imagem."\n'
            "}\n"
        )

        if categories:
            prompt += f"\nCategorias válidas permitidas:\n{', '.join(categories)}\n"

        if criteria and "rules" in criteria:
            prompt += "\nCritérios de classificação:\n"
            for cat, rule in criteria["rules"].items():
                prompt += f"- {cat}: {rule}\n"

        prompt += "\nLembra-te: apenas responde com o objeto JSON sem texto adicional antes ou depois."
        return prompt

    # ------------------------------------------------------------ inferência
    def classify_image(
        self,
        image_path: Path,
        categories: Optional[List[str]] = None,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Envia a imagem codificada e o prompt para o endpoint /api/generate do Ollama.

        Args:
            image_path: Caminho para a imagem a classificar.
            categories: Lista de categorias válidas para condicionar o modelo.
            criteria: Regras de seleção para inclusão no prompt.

        Returns:
            Dict[str, Any]: Dicionário com 'category', 'confidence' e 'description'.

        Raises:
            RuntimeError: Se houver falha de rede, timeout ou erro de parsing do JSON.
        """
        endpoint = f"{self.base_url}/api/generate"
        image_b64 = self.encode_image_to_base64(image_path)
        prompt = self._build_prompt(categories=categories, criteria=criteria)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "format": "json",  # Garante retorno de JSON estruturado no Ollama
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "fotoscan/1.1"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as err:
            try:
                detalhe = err.read().decode("utf-8", "replace")
            except Exception:
                detalhe = ""
            logger.error("Ollama devolveu HTTP %s: %s", err.code, detalhe)
            raise RuntimeError(f"Ollama devolveu HTTP {err.code}: {detalhe}") from err
        except urllib.error.URLError as err:
            logger.error("Falha ao comunicar com o Ollama em %s: %s", endpoint, err)
            raise RuntimeError(f"Não foi possível conectar ao Ollama: {err}") from err
        except TimeoutError as err:
            logger.error("Timeout ao aguardar resposta do modelo %s", self.model)
            raise RuntimeError("Tempo limite excedido na chamada ao Ollama.") from err

        try:
            response_json = json.loads(raw_body)
        except json.JSONDecodeError as err:
            raise RuntimeError(
                f"Ollama devolveu uma resposta ilegível: {raw_body[:200]!r}"
            ) from err

        # A resposta gerada pelo modelo encontra-se na chave 'response'
        model_output_text = str(response_json.get("response", "")).strip()

        try:
            return json.loads(model_output_text)
        except json.JSONDecodeError as err:
            logger.error("Modelo não devolveu JSON válido: %s", model_output_text)
            raise RuntimeError(f"Formato de resposta inválido: {model_output_text}") from err
