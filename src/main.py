#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import atexit
import base64
import json
import os
import re
import signal
import subprocess
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

MODELO_PADRAO = "qwen2.5vl:3b"

CONFIG_PADRAO = {
    "modelo": MODELO_PADRAO,
    "max_size": 768,
    "max_title": 30,
    "max_desc": 200,
    "max_categories": 3,
    "servidor": {
        "auto_start": True,
        "url": "http://127.0.0.1:11434",
        "timeout": 25,
        "env": {
            "OLLAMA_NUM_PARALLEL": "1",
            "CUDA_VISIBLE_DEVICES": "",
            "OLLAMA_GPU_OVERHEAD": "0"
        }
    },
    "caminhos": {
        "categories": "categories.json",
        "criteria": "criteria.json"
    },
    "inferencia": {
        "num_ctx": 4096,
        "num_predict": 300,
        "temperature": 0.2
    }
}

PROCESSO_SERVIDOR = None
MODELO_ATIVO_REGISTADO = None
CONFIG_ATIVA = dict(CONFIG_PADRAO)


# ---------------------------------------------------------------- AUXILIARES / STRINGS
def slugificar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def carregar_config() -> dict:
    global CONFIG_ATIVA
    PASTA_CONFIG.mkdir(parents=True, exist_ok=True)
    if FICHEIRO_CONFIG.exists():
        try:
            with open(FICHEIRO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
            config = {**CONFIG_PADRAO, **dados}
            config["servidor"] = {**CONFIG_PADRAO["servidor"], **dados.get("servidor", {})}
            config["caminhos"] = {**CONFIG_PADRAO["caminhos"], **dados.get("caminhos", {})}
            config["inferencia"] = {**CONFIG_PADRAO["inferencia"], **dados.get("inferencia", {})}
            CONFIG_ATIVA = config
            return config
        except Exception:
            pass
    with open(FICHEIRO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(CONFIG_PADRAO, f, indent=2, ensure_ascii=False)
    CONFIG_ATIVA = CONFIG_PADRAO.copy()
    return CONFIG_ATIVA


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


# ---------------------------------------------------------------- GESTÃO DO OLLAMA
def api_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "fotoscan/1.0"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post(url: str, payload: dict):
    dados = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=dados,
        headers={"Content-Type": "application/json", "User-Agent": "fotoscan/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        # O Ollama devolve a causa real no corpo (ex.: contexto insuficiente).
        try:
            detalhe = erro.read().decode("utf-8", "replace")
        except Exception:
            detalhe = ""
        raise RuntimeError(f"Ollama devolveu HTTP {erro.code}: {detalhe}") from erro


def testar_servidor(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/", timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def garantir_servidor(config: dict):
    global PROCESSO_SERVIDOR
    url = config["servidor"]["url"]
    if testar_servidor(url):
        return

    if not config["servidor"].get("auto_start", True):
        raise RuntimeError(f"Ollama inativo em {url} e auto_start está desativado.")

    sys.stderr.write("⚙️  A iniciar servidor Ollama em segundo plano (modo CPU/seguro)...\n")
    ambiente = os.environ.copy()
    ambiente.update(config["servidor"].get("env", {}))

    PROCESSO_SERVIDOR = subprocess.Popen(
        ["ollama", "serve"],
        env=ambiente,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )

    limite = time.time() + config["servidor"].get("timeout", 25)
    while time.time() < limite:
        if testar_servidor(url):
            sys.stderr.write("✔ Servidor Ollama operacional.\n")
            return
        time.sleep(0.5)

    raise RuntimeError("Tempo limite esgotado ao aguardar pelo arranque do Ollama.")


def descarregar_modelo(url: str, modelo: str):
    try:
        api_post(f"{url}/api/generate", {"model": modelo, "keep_alive": 0})
        sys.stderr.write(f"🧹 Memória libertada: modelo '{modelo}' descarregado da RAM/VRAM.\n")
    except Exception:
        pass


def limpar_no_encerramento():
    global PROCESSO_SERVIDOR, MODELO_ATIVO_REGISTADO
    url = CONFIG_ATIVA.get("servidor", {}).get("url", CONFIG_PADRAO["servidor"]["url"])
    if MODELO_ATIVO_REGISTADO:
        descarregar_modelo(url, MODELO_ATIVO_REGISTADO)

    if PROCESSO_SERVIDOR:
        sys.stderr.write("🛑 A terminar instância local do Ollama...\n")
        try:
            os.killpg(os.getpgid(PROCESSO_SERVIDOR.pid), signal.SIGTERM)
            PROCESSO_SERVIDOR.wait(timeout=5)
        except Exception:
            pass


atexit.register(limpar_no_encerramento)


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
def construir_prompt(criterios_selecionados: list, todas_cats: list, todos_crits: dict) -> str:
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

    prompt = (
        "Analisa a imagem e responde APENAS com um objeto JSON válido, sem cercas markdown nem texto adicional:\n"
        '{"titulo": "título curto", "descricao": "resumo objetivo", "categorias": ["id"]}\n\n'
        "Regras obrigatórias:\n"
        "1. 'titulo': conciso, baseado apenas no que é visível, no máximo 30 caracteres.\n"
        "2. 'descricao': texto claro em português, no máximo 200 caracteres.\n"
        "3. 'categorias': escolhe entre 1 e 3 IDs estritamente da lista de categorias válidas. Não inventes IDs.\n\n"
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


def modelo_disponivel(url: str, modelo: str) -> bool:
    """Verifica se o modelo está instalado no Ollama (True se não for possível verificar)."""
    try:
        dados = api_get(f"{url}/api/tags")
        instalados = [m.get("name", "") for m in dados.get("models", [])]
    except Exception:
        return True

    if modelo in instalados:
        return True
    base = modelo.split(":", 1)[0]
    return any(nome.split(":", 1)[0] == base for nome in instalados)

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


# ---------------------------------------------------------------- FLUXO PRINCIPAL
def main():
    config = carregar_config()
    try:
        todas_cats, todos_crits = carregar_referencias(config)
    except FileNotFoundError as erro:
        if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
            todas_cats, todos_crits = [], {}
        else:
            sys.stderr.write(f"Erro: {erro}\n")
            sys.exit(1)

    parser = argparse.ArgumentParser(
        prog="fotoscan",
        description="Catalogação automática de fotografias com IA multimodal local (Ollama)."
    )

    # Subcomando de inspeção direta
    parser.add_argument(
        "--get-data",
        dest="get_data_zip",
        metavar="PROJETO.ZIP",
        help="Lê e extrai o 'data.json' de um projeto existente sem descompactar"
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
        default=config.get("max_size", 768),
        help=f"Dimensão máxima em pixeis do lado maior (predefinição: {config.get('max_size', 768)})"
    )
    parser.add_argument(
        "-m", "--model",
        default=config.get("modelo", MODELO_PADRAO),
        help=f"Modelo Ollama a utilizar (predefinição: {config.get('modelo', MODELO_PADRAO)})"
    )

    # Registo dinâmico de flags booleanas para todos os critérios conhecidos
    for slug, info in todos_crits.items():
        parser.add_argument(
            f"--{slug}",
            action="store_true",
            help=f"Foco em {info['nome']}: {info['desc'][:60]}..."
        )

    args = parser.parse_args()

    # Operação de leitura direta de pacote ZIP existente
    if args.get_data_zip:
        acao_get_data(args.get_data_zip, args.saida)

    if not args.imagens:
        parser.print_help()
        sys.exit(1)

    # Identificar critérios ativos passados pela CLI
    criterios_ativos = [slug for slug in todos_crits if getattr(args, slug, False)]
    ids_validos = {c["id"] for c in todas_cats}

    # Assegurar serviço e modelo
    global MODELO_ATIVO_REGISTADO
    MODELO_ATIVO_REGISTADO = args.model
    url_servidor = config["servidor"]["url"]

    garantir_servidor(config)

    if not modelo_disponivel(url_servidor, args.model):
        sys.stderr.write(
            f"Erro: o modelo '{args.model}' não está instalado no Ollama.\n"
            f"  Instale com:  ollama pull {args.model}\n"
            "  Ou crie a variante leve documentada em docs/:  "
            "ollama create qwen2.5vl:light -f Modelfile\n"
        )
        sys.exit(1)

    # Montagem do prompt
    prompt_completo = construir_prompt(criterios_ativos, todas_cats, todos_crits)
    opcoes_inferencia = config.get("inferencia", {}) or {}

    # Validação dos ficheiros
    extensoes = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    fotos_validas = [p for p in args.imagens if Path(p).is_file() and Path(p).suffix.lower() in extensoes]
    fotos_validas.sort(key=lambda x: Path(x).name.casefold())

    if not fotos_validas:
        sys.stderr.write("Aviso: Nenhuma imagem válida encontrada nos caminhos indicados.\n")
        sys.exit(1)

    sys.stderr.write(f"📁 A processar {len(fotos_validas)} fotografia(s) com o modelo '{args.model}'...\n")

    resultados = []
    thumbnails_gerados = {}  # nome_arquivo: bytes

    tempo_inicio = time.time()

    for idx, foto in enumerate(fotos_validas, start=1):
        nome_ficheiro = Path(foto).name
        sys.stderr.write(f"[{idx}/{len(fotos_validas)}] A analisar: {nome_ficheiro} ... ")
        sys.stderr.flush()

        try:
            b64_img, thumb_bytes = preparar_imagem(foto, args.max_size)
            thumbnails_gerados[nome_ficheiro] = thumb_bytes

            payload = {
                "model": args.model,
                "prompt": prompt_completo,
                "images": [b64_img],
                "stream": False,
                "format": "json",
                "options": {
                    "num_ctx": opcoes_inferencia.get("num_ctx", 2048),
                    "num_predict": opcoes_inferencia.get("num_predict", 300),
                    "temperature": opcoes_inferencia.get("temperature", 0.2)
                }
            }

            resp = api_post(f"{url_servidor}/api/generate", payload)
            conteudo = extrair_json_resposta(resp.get("response", "{}"))

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

            resultados.append({
                "ficheiro": nome_ficheiro,
                "titulo": titulo,
                "descricao": descricao,
                "categorias": cats
            })
            sys.stderr.write("✔\n")

        except Exception as e:
            sys.stderr.write(f"✘ (Erro: {e})\n")
            resultados.append({
                "ficheiro": nome_ficheiro,
                "erro": str(e)
            })

    duracao = round(time.time() - tempo_inicio, 1)
    sys.stderr.write(f"\n🎉 Concluído em {duracao}s ({round(duracao/len(fotos_validas), 1)}s/foto).\n")

    # Libertar a memória da máquina de imediato
    descarregar_modelo(url_servidor, args.model)
    MODELO_ATIVO_REGISTADO = None

    # Exportação dos resultados
    if args.saida and args.saida.lower().endswith(".zip"):
        caminho_zip = Path(args.saida).resolve()
        sys.stderr.write(f"📦 A empacotar projeto em '{caminho_zip.name}'...\n")

        info_projeto = {
            "versao": "1.0",
            "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "modelo": args.model,
            "max_size": args.max_size,
            "criterios_ativos": criterios_ativos,
            "prompt_utilizado": prompt_completo
        }

        with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.json", json.dumps(resultados, indent=2, ensure_ascii=False))
            zf.writestr("config.json", json.dumps(info_projeto, indent=2, ensure_ascii=False))
            for nome_foto, b_bytes in thumbnails_gerados.items():
                zf.writestr(f"thumbnails/{nome_foto}", b_bytes)

        sys.stderr.write(f"✔ Projeto gravado com sucesso: {caminho_zip}\n")

    elif args.saida:
        caminho_json = Path(args.saida).resolve()
        with open(caminho_json, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"✔ Catálogo JSON gravado em: {caminho_json}\n")

    else:
        # Se não houver -o, despeja o JSON formatado no stdout
        sys.stdout.write(json.dumps(resultados, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nProcessamento interrompido pelo utilizador.\n")
        sys.exit(130)
