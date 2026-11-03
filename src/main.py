#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps

# ---------------------------------------------------------------- CONFIGURAÇÃO BASE
PASTA_CONFIG = Path.home() / ".config" / "fotoscan"
FICHEIRO_CONFIG = PASTA_CONFIG / "config.json"

CONFIG_PADRAO = {
    "max_size": 768,
    "max_title": 30,
    "max_desc": 200,
    "max_categories": 3,
    "deepseek": {
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com"
    },
    "caminhos": {
        "categories": "categories.json",
        "criteria": "criteria.json",
        "look": "look.json",
        "filtro": "filtro.json"
    },
    "inferencia": {
        "num_ctx": 4096,
        "num_predict": 300,
        "temperature": 0.2
    }
}


# ---------------------------------------------------------------- AUXILIARES / STRINGS
def slugificar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def carregar_config() -> dict:
    PASTA_CONFIG.mkdir(parents=True, exist_ok=True)
    if FICHEIRO_CONFIG.exists():
        try:
            with open(FICHEIRO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
            config = {**CONFIG_PADRAO, **dados}
            config["caminhos"] = {**CONFIG_PADRAO["caminhos"], **dados.get("caminhos", {})}
            config["inferencia"] = {**CONFIG_PADRAO["inferencia"], **dados.get("inferencia", {})}
            config["deepseek"] = {**CONFIG_PADRAO["deepseek"], **dados.get("deepseek", {})}
            return config
        except Exception:
            pass
    with open(FICHEIRO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(CONFIG_PADRAO, f, indent=2, ensure_ascii=False)
    return CONFIG_PADRAO.copy()


def resolver_caminho_dados(nome_ficheiro: str, config: dict) -> Path:
    p = Path(config.get("caminhos", {}).get(nome_ficheiro, f"{nome_ficheiro}.json"))
    candidatos = (
        p,
        PASTA_CONFIG / p.name,
        Path.cwd() / p.name,
        Path(__file__).resolve().parent.parent / "config" / p.name,
    )
    for candidato in candidatos:
        if candidato.exists():
            return candidato
    raise FileNotFoundError(
        f"Ficheiro de referência '{p.name}' não encontrado. "
        "Execute 'bash install.sh' ou indique o caminho em config.json → caminhos."
    )


def carregar_referencias(config: dict):
    # Categories
    caminho_cat = resolver_caminho_dados("categories", config)
    with open(caminho_cat, "r", encoding="utf-8") as f:
        dados_cat = json.load(f)

    mapa_grupos = {g["id"]: g["name"] for g in dados_cat.get("groups", [])}
    categorias = []
    for c in dados_cat.get("categories", []):
        nome = c.get("name", "").strip()
        gid = c.get("groupId", "")
        ident = slugificar(nome)
        if ident:
            categorias.append({
                "id": ident,
                "name": nome,
                "description": c.get("description", "").strip(),
                "grupo": mapa_grupos.get(gid, gid)
            })

    # Criteria
    caminho_crit = resolver_caminho_dados("criteria", config)
    with open(caminho_crit, "r", encoding="utf-8") as f:
        dados_crit = json.load(f)

    criterios = {slugificar(k): {"nome": k, "desc": v} for k, v in dados_crit.items()}
    return categorias, criterios


# ---------------------------------------------------------------- PROCESSAMENTO DE IMAGEM
def preparar_imagem(caminho: str, max_size: int):
    """
    Gera bytes em memória para a inferência (lado maior <= max_size)
    e um thumbnail JPEG pronto para arquivar.
    """
    with Image.open(caminho) as img:
        # Corrige a rotação física da câmara antes de redimensionar.
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        img_rgb = img.convert("RGB")
        img_rgb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        img_rgb.save(buffer, format="JPEG", quality=85, optimize=True)
        img_bytes = buffer.getvalue()
        b64_str = base64.b64encode(img_bytes).decode("ascii")
        return b64_str, img_bytes


# ---------------------------------------------------------------- PROMPT E INFERÊNCIA
def construir_prompt(criterios_selecionados: list, todas_cats: list, todos_crits: dict,
                     filtro_ativo: bool = False, situacoes_filtro: dict = None,
                     olhar: str = None, olhares: dict = None) -> str:
    linhas_cat = []
    for c in todas_cats:
        desc = f" — {c['description']}" if c["description"] else ""
        linhas_cat.append(f"- {c['id']} ({c['grupo']}){desc}")
    lista_cats_str = "\n".join(linhas_cat)

    linhas_crit = []
    for chave in criterios_selecionados:
        if chave in todos_crits:
            item = todos_crits[chave]
            linhas_crit.append(f"- {item['nome']}: {item['desc']}")
    foco_str = "\n".join(linhas_crit)

    campos = ['"titulo": "título curto"', '"descricao": "resumo objetivo"', '"categorias": ["id"]']
    if filtro_ativo and situacoes_filtro:
        campos.append('"alerta": null')
    esquema = "{" + ", ".join(campos) + "}"

    prompt = (
        "Analisa a imagem e responde APENAS com um objeto JSON válido, sem cercas markdown nem texto adicional:\n"
        + esquema + "\n\n"
        "Regras obrigatórias:\n"
        "1. 'titulo': conciso, baseado apenas no que é visível, no máximo 30 caracteres.\n"
        "2. 'descricao': texto claro em português, no máximo 200 caracteres.\n"
        "3. 'categorias': escolhe entre 1 e 3 IDs estritamente da lista de categorias válidas. Não inventes IDs.\n"
    )

    regra_n = 4
    if filtro_ativo and situacoes_filtro:
        linhas_sit = [f"- {desc}" for desc in situacoes_filtro.values()]
        prompt += (
            f"{regra_n}. 'alerta': se a imagem contém alguma das situações abaixo, devolve uma string curta "
            "com os motivos separados por '; '; caso contrário devolve null.\n"
            "   Situações a detetar:\n" + "\n".join(linhas_sit) + "\n"
        )
        regra_n += 1

    if olhar and olhares and olhar in olhares:
        prompt += (
            f"Interpreta a imagem segundo este olhar — {olhares[olhar]} "
            "Usa-o para orientar o título e a descrição.\n\n"
        )

    if foco_str:
        prompt += f"Na descrição e classificação, concentra-te nestes aspetos:\n{foco_str}\n\n"

    prompt += f"Categorias válidas (IDs disponíveis):\n{lista_cats_str}"
    return prompt


def extrair_json_resposta(texto: str) -> dict:
    """
    Extrai o objeto JSON da resposta do modelo, tolerando cercas markdown e
    truncagem no fim (causada por `num_predict` baixo).

    Raises:
        ValueError: Se não for possível recuperar um JSON válido.
    """
    texto = (texto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-zA-Z]*\s*", "", texto)
        texto = re.sub(r"\s*```$", "", texto).strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # Isola o primeiro objeto {...} equilibrado
    inicio = texto.find("{")
    if inicio != -1:
        profundidade = 0
        dentro_de_string = False
        escape = False
        for i in range(inicio, len(texto)):
            ch = texto[i]
            if dentro_de_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    dentro_de_string = False
                continue
            if ch == '"':
                dentro_de_string = True
            elif ch == "{":
                profundidade += 1
            elif ch == "}":
                profundidade -= 1
                if profundidade == 0:
                    try:
                        return json.loads(texto[inicio:i + 1])
                    except json.JSONDecodeError:
                        break

    # Última tentativa: rematar strings, arrays e objetos truncados
    recuperado = texto.rstrip()
    if recuperado.startswith("{"):
        if recuperado.count('"') % 2 == 1:
            recuperado += '"'
        if recuperado.count("[") > recuperado.count("]"):
            recuperado += "]"
        if recuperado.count("{") > recuperado.count("}"):
            recuperado += "}"
        try:
            return json.loads(recuperado)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Resposta do modelo não é JSON válido: {texto[:200]!r}")


# ---------------------------------------------------------------- INFERÊNCIA (DeepSeek)
def chamar_modelo(url: str, modelo: str, prompt: str, b64_img: str,
                  opcoes: dict, api_key: str = "") -> str:
    """Chama o modelo DeepSeek (API compatível com OpenAI) e devolve o texto gerado."""
    num_predict = opcoes.get("num_predict", 300)
    num_predict = opcoes.get("num_predict", 300)
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": "Responde apenas com um objeto JSON válido, sem texto adicional."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
            ]}
        ],
        "response_format": {"type": "json_object"},
        "temperature": opcoes.get("temperature", 0.2),
        "max_tokens": num_predict
    }
    if opcoes.get("texto_livre"):
        payload.pop("response_format", None)
    dados = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/chat/completions",
        data=dados,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "fotoscan/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        try:
            detalhe = erro.read().decode("utf-8", "replace")
        except Exception:
            detalhe = ""
        raise RuntimeError(f"DeepSeek devolveu HTTP {erro.code}: {detalhe}") from erro
    except urllib.error.URLError as erro:
        raise RuntimeError(f"Não foi possível conectar ao DeepSeek: {erro}") from erro

    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError(f"Resposta DeepSeek sem choices: {body}")
    return choices[0].get("message", {}).get("content") or ""


def obter_json_modelo(url: str, modelo: str, prompt: str, b64_img: str,
                      opcoes: dict, api_key: str = "", tentativas: int = 3):
    """
    Chama o modelo com retentativas automáticas.

    Se o modelo devolver uma resposta vazia ou fora de esquema, a chamada é
    repetida. Na última tentativa o modo JSON rígido (response_format) é
    desligado e usa-se apenas o extrator tolerante (extrair_json_resposta).

    Returns:
        (dict, int): conteúdo JSON extraído e o número da tentativa em que
        foi obtido (1 = à primeira).

    Raises:
        Exception: o último erro, se todas as tentativas falharem.
    """
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        op_local = dict(opcoes)
        if tentativa == tentativas and tentativas > 1:
            op_local["texto_livre"] = True
        try:
            texto = chamar_modelo(url, modelo, prompt, b64_img, op_local, api_key)
            return extrair_json_resposta(texto), tentativa
        except Exception as erro:
            ultimo_erro = erro
            if tentativa < tentativas:
                time.sleep(1)
    raise ultimo_erro


# ---------------------------------------------------------------- COMANDO --GET-DATA
def acao_get_data(caminho_zip: str, caminho_saida: str = None):
    p_zip = Path(caminho_zip)
    if not p_zip.exists():
        sys.stderr.write(f"Erro: O ficheiro '{caminho_zip}' não existe.\n")
        sys.exit(1)

    try:
        with zipfile.ZipFile(p_zip, "r") as zf:
            if "data.json" not in zf.namelist():
                sys.stderr.write(f"Erro: O arquivo '{caminho_zip}' não contém 'data.json'.\n")
                sys.exit(1)
            conteudo = zf.read("data.json").decode("utf-8")
    except Exception as e:
        sys.stderr.write(f"Erro ao abrir arquivo ZIP: {e}\n")
        sys.exit(1)

    if caminho_saida:
        if str(caminho_saida).lower().endswith(".zip"):
            sys.stderr.write("Erro: --get-data extrai JSON; indique um destino .json, não .zip.\n")
            sys.exit(1)
        with open(caminho_saida, "w", encoding="utf-8") as f:
            f.write(conteudo)
        sys.stderr.write(f"✔ Dados exportados para '{caminho_saida}'.\n")
    else:
        sys.stdout.write(conteudo + "\n")
    sys.exit(0)


def acao_get_alerts(caminho: str, caminho_saida: str = None):
    p = Path(caminho)
    if not p.exists():
        sys.stderr.write(f"Erro: O ficheiro '{caminho}' não existe.\n")
        sys.exit(1)

    conteudo = None
    if p.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(p, "r") as zf:
                if "alertas.json" not in zf.namelist():
                    sys.stderr.write(f"Erro: O arquivo '{caminho}' não contém 'alertas.json' (filtro não foi usado?).\n")
                    sys.exit(1)
                conteudo = zf.read("alertas.json").decode("utf-8")
        except Exception as e:
            sys.stderr.write(f"Erro ao abrir arquivo ZIP: {e}\n")
            sys.exit(1)
    else:
        try:
            conteudo = p.read_text(encoding="utf-8")
            json.loads(conteudo)  # valida
        except Exception as e:
            sys.stderr.write(f"Erro ao ler ficheiro de alertas: {e}\n")
            sys.exit(1)

    # Resumo legível quando não há -o
    if not caminho_saida:
        try:
            alertas = json.loads(conteudo)
        except Exception:
            alertas = []
        if not alertas:
            sys.stderr.write("✔ Nenhuma situação sensível detetada.\n")
        else:
            sys.stderr.write(f"⚠ {len(alertas)} situação(ões) sensível(is) detetada(s):\n")
            for a in alertas:
                sys.stderr.write(f"  • {a.get('ficheiro')} — {a.get('motivo')}\n")
            sys.stderr.write("\n")
        sys.stdout.write(conteudo + "\n")
        sys.exit(0)

    if str(caminho_saida).lower().endswith(".zip"):
        sys.stderr.write("Erro: --get-alerts extrai JSON; indique um destino .json, não .zip.\n")
        sys.exit(1)
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(conteudo)
    sys.stderr.write(f"✔ Alertas exportados para '{caminho_saida}'.\n")
    sys.exit(0)


# ---------------------------------------------------------------- FLUXO PRINCIPAL
def main():
    config = carregar_config()
    try:
        todas_cats, todos_crits = carregar_referencias(config)
    except FileNotFoundError as erro:
        if any(arg in ("-h", "--help", "--exemplos", "--exemples") for arg in sys.argv[1:]):
            todas_cats, todos_crits = [], {}
        else:
            sys.stderr.write(f"Erro: {erro}\n")
            sys.exit(1)

    # Carregar situações do filtro (opcional; se o ficheiro não existir, filtro desativado)
    situacoes_filtro = {}
    try:
        caminho_filtro = resolver_caminho_dados("filtro", config)
        with open(caminho_filtro, "r", encoding="utf-8") as f:
            situacoes_filtro = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        situacoes_filtro = {}

    # Carregar olhares (opcional)
    olhares_disponiveis = {}
    try:
        caminho_look = resolver_caminho_dados("look", config)
        with open(caminho_look, "r", encoding="utf-8") as f:
            olhares_disponiveis = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        olhares_disponiveis = {}

    exemplos = (
        "Exemplos de utilização:\n"
        "  fotoscan *.jpg -o catalogo.json\n"
        "      Catálogo simples em JSON (stdout se omitir -o).\n"
        "  fotoscan *.jpg -o projeto.zip\n"
        "      Projeto completo: data.json + config.json + thumbnails/.\n"
        "  fotoscan *.jpg -o projeto.zip --pessoas --cenario --tecnica\n"
        "      Foco em critérios específicos (viram flags --slug).\n"
        "  fotoscan *.jpg -o projeto.zip --sensivel\n"
        "      Deteção de situações sensíveis (crianças, violência, nudez, ...).\n"
        "  fotoscan *.jpg -o projeto.zip --olhar poetico\n"
        "      Análise com um olhar (documental, poetico, formal, humano).\n"
        "  fotoscan *.jpg -o projeto.zip --pessoas --sensivel --olhar formal\n"
        "      Combinação completa.\n"
        "  fotoscan --get-data projeto.zip -o dados.json\n"
        "      Lê o data.json de um projeto já gerado.\n"
        "  fotoscan --get-alerts projeto.zip\n"
        "      Lista as situações sensíveis detetadas (alertas.json).\n"
    )

    class _Formatador(argparse.RawDescriptionHelpFormatter):
        def __init__(self, prog):
            super().__init__(prog, max_help_position=34, width=100)

    parser = argparse.ArgumentParser(
        prog="fotoscan",
        description="Catalogação automática de fotografias com IA multimodal (DeepSeek).",
        epilog="Usa 'fotoscan --exemplos' para ver exemplos de utilização.",
        formatter_class=_Formatador
    )

    # Subcomando de inspeção direta
    parser.add_argument(
        "--get-data",
        dest="get_data_zip",
        metavar="PROJETO.ZIP",
        help="Lê e extrai o 'data.json' de um projeto existente sem descompactar"
    )
    parser.add_argument(
        "--get-alerts",
        dest="get_alerts",
        metavar="ARQUIVO",
        help="Lê o ficheiro de alertas (alertas.json) de um projeto (.zip) ou de um .json de alertas"
    )
    parser.add_argument(
        "--exemplos", "--exemples",
        action="store_true",
        help="Mostra exemplos de utilização e sai"
    )

    # Entradas e Saídas
    parser.add_argument(
        "imagens",
        nargs="*",
        help="Ficheiros de imagem a catalogar (ex: *.jpg, *.png)"
    )
    parser.add_argument(
        "-o", "--output",
        dest="saida",
        help="Ficheiro de destino (.json para catálogo simples, ou .zip para projeto completo)"
    )
    parser.add_argument(
        "-s", "--max-size",
        type=int,
        metavar="PX",
        default=config.get("max_size", 768),
        help=f"Dimensão máxima em px do lado maior (predefinição: {config.get('max_size', 768)})"
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        help=f"Modelo DeepSeek a utilizar (predefinição: '{config.get('deepseek', {}).get('model', 'deepseek-flash')}')"
    )

    # Registo dinâmico de flags booleanas para todos os critérios conhecidos
    for slug, info in todos_crits.items():
        parser.add_argument(
            f"--{slug}",
            action="store_true",
            help=f"Foco em {info['nome']}: {info['desc'][:60]}..."
        )

    parser.add_argument(
        "--sensivel",
        action="store_true",
        dest="sensivel",
        help="Ativa a deteção de situações sensíveis (crianças, violência, nudez, vulnerabilidade, dados pessoais, conteúdo ofensivo). Gera um ficheiro separado (alertas) com as fotos afetadas e o motivo."
    )
    # Alias retrocompatível (oculto)
    parser.add_argument(
        "--filtro",
        action="store_true",
        dest="sensivel",
        help=argparse.SUPPRESS
    )

    # Olhar (lente de análise): seletor + atalhos por chave
    if olhares_disponiveis:
        parser.add_argument(
            "--olhar",
            choices=sorted(olhares_disponiveis.keys()),
            default=None,
            dest="olhar",
            help="Lente de análise a aplicar (documental, poetico, formal, humano)."
        )
        for slug in olhares_disponiveis:
            parser.add_argument(
                f"--{slug}",
                action="store_const",
                const=slug,
                dest="olhar",
                help=argparse.SUPPRESS
            )

    args = parser.parse_args()

    if args.exemplos:
        sys.stdout.write(exemplos)
        sys.exit(0)

    # Operação de leitura direta de pacote ZIP existente
    if args.get_data_zip:
        acao_get_data(args.get_data_zip, args.saida)

    if getattr(args, "get_alerts", None):
        acao_get_alerts(args.get_alerts, args.saida)

    if not args.imagens:
        parser.print_help()
        sys.exit(1)

    # Identificar critérios ativos passados pela CLI
    criterios_ativos = [slug for slug in todos_crits if getattr(args, slug, False)]
    ids_validos = {c["id"] for c in todas_cats}

    # Backend de inferência: DeepSeek (API paga, compatível com OpenAI)
    modelo_ativo = args.model or config.get("deepseek", {}).get("model", "deepseek-flash")
    url_servidor = config.get("deepseek", {}).get("base_url", "https://api.deepseek.com")

    # Validar chave de API
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        sys.stderr.write(
            "Erro: DEEPSEEK_API_KEY não definida.\n"
            "  Defina-a com:  export DEEPSEEK_API_KEY='sk-...'\n"
            "  (opcionalmente em ~/.config/fotoscan/config.json → deepseek.api_key)\n"
        )
        # Tentar fallback do config.json
        api_key = (config.get("deepseek", {}) or {}).get("api_key", "").strip()
        if not api_key:
            sys.exit(1)
    os.environ["DEEPSEEK_API_KEY"] = api_key

    # Montagem do prompt
    prompt_completo = construir_prompt(
        criterios_ativos, todas_cats, todos_crits,
        filtro_ativo=args.sensivel, situacoes_filtro=situacoes_filtro,
        olhar=getattr(args, "olhar", None), olhares=olhares_disponiveis
    )
    opcoes_inferencia = config.get("inferencia", {}) or {}

    # Validação dos ficheiros
    extensoes = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    fotos_validas = [p for p in args.imagens if Path(p).is_file() and Path(p).suffix.lower() in extensoes]
    fotos_validas.sort(key=lambda x: Path(x).name.casefold())

    if not fotos_validas:
        sys.stderr.write("Aviso: Nenhuma imagem válida encontrada nos caminhos indicados.\n")
        sys.exit(1)

    sys.stderr.write(f"📁 A processar {len(fotos_validas)} fotografia(s) com o modelo '{modelo_ativo}' (DeepSeek)...\n")

    resultados = []
    thumbnails_gerados = {}  # nome_arquivo: bytes
    alertas = []  # fotos com situações críticas detetadas pelo filtro

    tempo_inicio = time.time()

    # Fase 1 — gerar thumbnails (lado maior <= max_size). É esta imagem
    # reduzida — nunca o original — que é enviada à IA e arquivada no ZIP.
    sys.stderr.write(f"🖼  Fase 1/2: a gerar {len(fotos_validas)} thumbnail(s)...\n")
    preparadas = {}  # nome_arquivo: b64 para a IA
    for foto in fotos_validas:
        nome_ficheiro = Path(foto).name
        try:
            b64_img, thumb_bytes = preparar_imagem(foto, args.max_size)
            preparadas[nome_ficheiro] = b64_img
            thumbnails_gerados[nome_ficheiro] = thumb_bytes
        except Exception as e:
            sys.stderr.write(f"   ✘ {nome_ficheiro}: erro ao gerar thumbnail ({e})\n")
            resultados.append({
                "ficheiro": nome_ficheiro,
                "erro": f"Falha ao gerar thumbnail: {e}"
            })

    # Fase 2 — análise pela IA sobre os thumbnails gerados
    sys.stderr.write(f"🤖 Fase 2/2: a analisar thumbnails com o modelo '{modelo_ativo}'...\n")
    for idx, foto in enumerate(fotos_validas, start=1):
        nome_ficheiro = Path(foto).name
        if nome_ficheiro not in preparadas:
            continue  # já registado como erro na fase 1

        sys.stderr.write(f"[{idx}/{len(fotos_validas)}] A analisar: {nome_ficheiro} ... ")
        sys.stderr.flush()

        try:
            b64_img = preparadas[nome_ficheiro]

            num_predict_base = opcoes_inferencia.get("num_predict", 300)
            num_predict = num_predict_base
            if args.sensivel:
                num_predict = max(num_predict, 500)
            opcoes_local = dict(opcoes_inferencia)
            opcoes_local["num_predict"] = num_predict

            conteudo, tentativa = obter_json_modelo(
                url_servidor, modelo_ativo, prompt_completo, b64_img, opcoes_local, api_key
            )
            if tentativa > 1:
                sys.stderr.write(f"(↻ recuperado à {tentativa}ª tentativa) ")

            # Validação e truncagem estrita de métricas
            titulo = str(conteudo.get("titulo", "")).strip()[:config.get("max_title", 30)]
            descricao = str(conteudo.get("descricao", "")).strip()[:config.get("max_desc", 200)]

            raw_cats = conteudo.get("categorias", [])
            if not isinstance(raw_cats, list):
                raw_cats = [raw_cats]

            cats = [c for c in raw_cats if isinstance(c, str) and c in ids_validos]
            if not cats and todas_cats:
                cats = [todas_cats[0]["id"]]
            cats = cats[:config.get("max_categories", 3)]

            # Filtro de situações críticas
            alerta = conteudo.get("alerta", None)
            if isinstance(alerta, str):
                alerta = alerta.strip()
                if not alerta or alerta.lower() in ("null", "none", "nenhuma", "n/a"):
                    alerta = None
            else:
                alerta = None

            resultados.append({
                "ficheiro": nome_ficheiro,
                "titulo": titulo,
                "descricao": descricao,
                "categorias": cats
            })

            if args.sensivel and alerta:
                alertas.append({"ficheiro": nome_ficheiro, "titulo": titulo, "motivo": alerta})
                sys.stderr.write("⚠\n")
            else:
                sys.stderr.write("✔\n")

        except Exception as e:
            sys.stderr.write(f"✘ (Erro: {e})\n")
            resultados.append({
                "ficheiro": nome_ficheiro,
                "erro": str(e)
            })

    duracao = round(time.time() - tempo_inicio, 1)
    sys.stderr.write(f"\n🎉 Concluído em {duracao}s ({round(duracao/len(fotos_validas), 1)}s/foto).\n")

    # Exportação dos resultados
    if args.saida and args.saida.lower().endswith(".zip"):
        caminho_zip = Path(args.saida).resolve()
        sys.stderr.write(f"📦 A empacotar projeto em '{caminho_zip.name}'...\n")

        info_projeto = {
            "versao": "1.0",
            "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "modelo": modelo_ativo,
            "max_size": args.max_size,
            "criterios_ativos": criterios_ativos,
            "filtro_ativo": bool(args.sensivel),
            "prompt_utilizado": prompt_completo
        }

        with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.json", json.dumps(resultados, indent=2, ensure_ascii=False))
            zf.writestr("config.json", json.dumps(info_projeto, indent=2, ensure_ascii=False))
            if args.sensivel:
                zf.writestr("alertas.json", json.dumps(alertas, indent=2, ensure_ascii=False))
            for nome_foto, b_bytes in thumbnails_gerados.items():
                zf.writestr(f"thumbnails/{nome_foto}", b_bytes)

        sys.stderr.write(f"✔ Projeto gravado com sucesso: {caminho_zip}\n")
        if args.sensivel:
            sys.stderr.write(f"   ⚠ {len(alertas)} foto(s) com situações críticas (ver alertas.json no ZIP).\n")

    elif args.saida:
        caminho_json = Path(args.saida).resolve()
        with open(caminho_json, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"✔ Catálogo JSON gravado em: {caminho_json}\n")

        if args.sensivel:
            caminho_alertas = caminho_json.with_name(caminho_json.stem + "_alertas.json")
            with open(caminho_alertas, "w", encoding="utf-8") as f:
                json.dump(alertas, f, indent=2, ensure_ascii=False)
            sys.stderr.write(f"   ⚠ {len(alertas)} foto(s) com situações críticas: {caminho_alertas}\n")

    else:
        # Se não houver -o, despeja o JSON formatado no stdout
        sys.stdout.write(json.dumps(resultados, indent=2, ensure_ascii=False) + "\n")
        if args.sensivel:
            caminho_alertas = Path.cwd() / "alertas.json"
            with open(caminho_alertas, "w", encoding="utf-8") as f:
                json.dump(alertas, f, indent=2, ensure_ascii=False)
            sys.stderr.write(f"   ⚠ {len(alertas)} foto(s) com situações críticas: {caminho_alertas}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nProcessamento interrompido pelo utilizador.\n")
        sys.exit(130)
