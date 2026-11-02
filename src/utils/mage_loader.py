"""
Módulo utilitário para carregamento, validação e preparação de imagens.

Disponibiliza funções e classes para carregar ficheiros de imagem (JPG, PNG, WebP, etc.),
tratar rotação via metadados EXIF, redimensionar mantendo proporções e validar
a integridade antes do envio para modelos de visão computacional ou Ollama.
"""

import io
import logging
from pathlib import Path
from typing import Optional, Tuple, Union
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Extensões de imagem suportadas por omissão
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


class ImageLoaderError(Exception):
    """Exceção base para erros ocorridos durante o carregamento de imagens."""
    pass


class InvalidImageFormatError(ImageLoaderError):
    """Lançada quando o formato ou extensão da imagem não é suportado."""
    pass


class ImageCorruptError(ImageLoaderError):
    """Lançada quando o ficheiro está corrompido ou ilegível pela Pillow."""
    pass


def is_supported_image(file_path: Union[str, Path]) -> bool:
    """
    Verifica se o caminho possui uma extensão de imagem suportada.

    Args:
        file_path: Caminho ou string do ficheiro a verificar.

    Returns:
        bool: True se a extensão for suportada, False caso contrário.
    """
    path = Path(file_path)
    return path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def load_image(
    image_path: Union[str, Path],
    correct_orientation: bool = True,
    convert_rgb: bool = True
) -> Image.Image:
    """
    Carrega uma imagem do disco, corrige a rotação EXIF e converte para RGB se solicitado.

    Args:
        image_path: Caminho do ficheiro de imagem.
        correct_orientation: Se True, aplica a rotação necessária de acordo com a tag EXIF.
        convert_rgb: Se True, converte a imagem para modo RGB (eliminando canal alfa ou CMYK).

    Returns:
        Image.Image: Objeto PIL Image carregado e normalizado.

    Raises:
        FileNotFoundError: Se o ficheiro não existir no disco.
        InvalidImageFormatError: Se a extensão do ficheiro não for suportada.
        ImageCorruptError: Se o ficheiro não puder ser descodificado.
    """
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Imagem não encontrada: {path}")

    if not is_supported_image(path):
        raise InvalidImageFormatError(
            f"Formato não suportado para o ficheiro '{path.name}'. "
            f"Formatos aceites: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"
        )

    try:
        img = Image.open(path)
        img.load()  # Força a leitura completa do ficheiro para memória
    except (IOError, SyntaxError) as err:
        logger.error("Falha ao abrir ou descodificar o ficheiro %s: %s", path, err)
        raise ImageCorruptError(f"Ficheiro de imagem corrompido ou inválido: {path}") from err

    # Corrige rotação física da câmara com base nos metadados EXIF
    if correct_orientation:
        try:
            img = ImageOps.exif_transpose(img)
        except Exception as err:
            logger.warning("Não foi possível processar metadados EXIF para %s: %s", path, err)

    # Converte para RGB para compatibilidade universal com modelos de visão
    if convert_rgb and img.mode != "RGB":
        img = img.convert("RGB")

    return img


def resize_image_aspect_ratio(
    image: Image.Image,
    max_dimension: int = 1920
) -> Image.Image:
    """
    Redimensiona a imagem caso as suas dimensões excedam o limite máximo, mantendo a proporção.

    Args:
        image: Instância de imagem PIL.
        max_dimension: Comprimento/largura máxima permitida (em píxeis).

    Returns:
        Image.Image: Imagem original ou redimensionada proporcionalmente.
    """
    width, height = image.size
    if width <= max_dimension and height <= max_dimension:
        return image

    if width > height:
        new_width = max_dimension
        new_height = int((height / width) * max_dimension)
    else:
        new_height = max_dimension
        new_width = int((width / height) * max_dimension)

    logger.debug("Redimensionando imagem de %dx%d para %dx%d", width, height, new_width, new_height)
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def get_image_metadata(image_path: Union[str, Path]) -> dict:
    """
    Extrai metadados básicos de dimensões, formato e tamanho em bytes sem carregar todo o bitmap.

    Args:
        image_path: Caminho do ficheiro de imagem.

    Returns:
        dict: Dicionário contendo formato, dimensões (width, height), modo de cor e tamanho.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Ficheiro não encontrado: {path}")

    with Image.open(path) as img:
        width, height = img.size
        format_name = img.format
        mode = img.mode

    return {
        "filename": path.name,
        "format": format_name,
        "mode": mode,
        "width": width,
        "height": height,
        "filesize_bytes": path.stat().st_size
    }


def to_bytes(image: Image.Image, format_name: str = "JPEG", quality: int = 90) -> bytes:
    """
    Converte uma imagem PIL em bytes em memória para transmissão via stream ou base64.

    Args:
        image: Instância de imagem PIL.
        format_name: Formato de exportação ('JPEG', 'PNG', etc.).
        quality: Qualidade de compressão para JPEG/WebP (1-100).

    Returns:
        bytes: Buffer com o conteúdo binário da imagem.
    """
    buffer = io.BytesIO()
    save_kwargs = {}
    if format_name.upper() in {"JPEG", "JPG", "WEBP"}:
        save_kwargs["quality"] = quality

    image.save(buffer, format=format_name, **save_kwargs)
    return buffer.getvalue()