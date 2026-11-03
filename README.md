# FotoScan

Catalogação automática de fotografias com um modelo de visão (Ollama local ou
DeepSeek pago). Cada imagem recebe um título curto, uma descrição objetiva e
1–3 categorias escolhidas de um catálogo controlado. Por defeito usa o
DeepSeek pago (configurável).

## Requisitos

- Linux
- Python 3.10+
- **Um dos backends:**
  - **DeepSeek pago** (predefinição): chave de API em `DEEPSEEK_API_KEY`.
  - **Ollama local**: [Ollama](https://ollama.com) instalado e um modelo multimodal
    (ex.: `qwen2.5vl:3b`).

```bash
# DeepSeek (pago)
export DEEPSEEK_API_KEY='sk-...'

# Ollama (local, gratuito)
ollama pull qwen2.5vl:3b
```

## Instalação

```bash
cd /mnt/dados/Projetos/1_Scripts/FotoScan
bash install.sh
```

O `install.sh` faz, por esta ordem:

1. cria o ambiente virtual `.venv/`;
2. instala `requirements.txt` (Pillow);
3. copia `config/*.json` para `~/.config/fotoscan/` (preserva os existentes);
4. torna `run.sh` executável;
5. cria um **symlink** `~/.local/bin/fotoscan → run.sh`.

Use `bash install.sh --force-config` para substituir configurações já existentes
(é criado um `.bak` antes de sobrescrever).

> `~/.local/bin` tem de estar no `$PATH`.

Para desenvolvimento (inclui `pytest`):

```bash
.venv/bin/pip install -r requirements-dev.txt
```

## Utilização

```bash
# catálogo simples em JSON
fotoscan *.jpg -o catalogo.json

# projeto completo: data.json + config.json + thumbnails/
fotoscan *.jpg -o projeto.zip

# foco em critérios específicos (viram flags --slug)
fotoscan *.jpg -o projeto.zip --pessoas --cenario --tecnica

# deteção de situações sensíveis (crianças, violência, nudez, vulnerabilidade, dados pessoais, conteúdo ofensivo)
fotoscan *.jpg -o projeto.zip --sensivel

# análise com um olhar (documental, poetico, formal, humano)
fotoscan *.jpg -o projeto.zip --olhar poetico
fotoscan *.jpg -o projeto.zip --poetico

# modelo diferente
fotoscan *.jpg -o catalogo.json -m granite3.2-vision:2b

# ler o data.json de um projeto já gerado
fotoscan --get-data projeto.zip
fotoscan --get-data projeto.zip -o dados.json

# ler os alertas de situações sensíveis de um projeto
fotoscan --get-alerts projeto.zip

# usar o DeepSeek pago (requer DEEPSEEK_API_KEY)
export DEEPSEEK_API_KEY='sk-...'
fotoscan *.jpg -o projeto.zip --deepseek
```

Sem `-o`, o JSON é impresso no `stdout` (útil para pipes).

**Formatos aceites:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`.

## Configuração

Configuração efetiva: `~/.config/fotoscan/config.json` (criada a partir de
`config/config.json` na instalação).

```jsonc
{
  "provider": "deepseek",   // "ollama" (local) ou "deepseek" (pago)
  "modelo": "qwen2.5vl:3b", // usado quando provider = "ollama"
  "deepseek": { "model": "deepseek-flash" },
  "max_size": 512,          // lado maior da imagem enviada ao modelo
  "max_title": 30,          // limite de caracteres do título
  "max_desc": 200,          // limite de caracteres da descrição
  "max_categories": 3,      // máximo de categorias por foto
  "servidor": {
    "auto_start": true,     // inicia `ollama serve` se não estiver a correr
    "url": "http://127.0.0.1:11434",
    "timeout": 30,          // segundos de espera pelo arranque
    "env": { "OLLAMA_NUM_PARALLEL": "1" }
  },
  "caminhos": {
    "categories": "categories.json",
    "criteria": "criteria.json",
    "look": "look.json",
    "filtro": "filtro.json"
  }
}
```

Referências:

- `config/categories.json` — catálogo com grupos e categorias.
- `config/criteria.json` — critérios de análise. **Cada chave vira uma flag CLI**
  (`Pessoas` → `--pessoas`, `Expressões` → `--expressoes`, `Cenário` → `--cenario`).
- `config/look.json` — olhares (lentes de análise) usados com `--olhar <slug>` (documental, poetico, formal, humano). O olhar orienta a IA na produção do título e da descrição (não adiciona campos ao resultado).
- `config/filtro.json` — situações sensíveis detetadas com `--sensivel` (crianças, violência,
  nudez, vulnerabilidade, dados pessoais, conteúdo ofensivo). Gera `alertas.json`.

## Modelos / Backends

| Backend | Modelo | Contexto | Notas |
| --- | --- | ---: | --- |
| DeepSeek (pago) | `deepseek-flash` | 1M | Predefinição. ~$0,0004/foto. Requer `DEEPSEEK_API_KEY` |
| Ollama (local) | `qwen2.5vl:3b` | 125K | Gratuito. Precisa de ~4–5 GB de RAM/VRAM |
| Ollama (local) | `qwen2.5vl:light` | 2048 | Variante leve para 4 GB de VRAM — ver `Modelfile` |
| Ollama (local) | `granite3.2-vision:2b` | 16K | Alternativa mais pequena, com suporte a tools |

Criar a variante leve:

```bash
ollama create qwen2.5vl:light -f Modelfile
```

O passo a passo técnico (VRAM, `num_ctx`, CPU-only, `keep_alive`) está em
[`docs/Guia Técnico de Ligação e Utilização do Ollama.md`](docs/Guia%20Técnico%20de%20Ligação%20e%20Utilização%20do%20Ollama.md).

## Estrutura

```text
FotoScan/
├── Modelfile                 # variante leve do modelo (opcional)
├── install.sh                # instalação (venv + configs + symlink)
├── run.sh                    # wrapper que executa src/main.py com o .venv
├── requirements.txt          # dependências de execução
├── requirements-dev.txt       # dependências de teste
├── config/
│   ├── config.json           # configuração de referência
│   ├── categories.json       # catálogo de categorias
│   ├── criteria.json         # critérios (geram as flags da CLI)
│   ├── look.json             # olhares (lentes de análise)
│   └── filtro.json           # situações sensíveis (--sensivel)
├── src/
│   ├── main.py               # CLI (argumentos, lote, exportação ZIP/JSON)
│   ├── api/client.py         # OllamaClient + chamadas (Ollama/DeepSeek)
│   ├── core/classifier.py    # Classifier — carrega referências e valida respostas
│   └── utils/mage_loader.py  # utilitários de imagem (EXIF, resize, metadados)
├── tests/                    # pytest
└── docs/                     # instalação e manual do Ollama
```

## Testes

```bash
.venv/bin/python -m pytest -q
```

## Resolução de problemas

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| `modelo '...' não está instalado` | modelo em falta | `ollama pull qwen2.5vl:3b` ou `ollama create qwen2.5vl:light -f Modelfile` |
| `failed to allocate ... buffer` | VRAM insuficiente | use `qwen2.5vl:light` ou force CPU (`CUDA_VISIBLE_DEVICES=""`) |
| `Formato de resposta inválido` | JSON truncado | aumente `num_predict` no `Modelfile` |
| `Ficheiro de referência não encontrado` | configs não instaladas | `bash install.sh` |
| Fotos de telemóvel "deitadas" | EXIF | já corrigido automaticamente em `preparar_imagem` |

## Licença

Uso pessoal. Adicione um ficheiro `LICENSE` se for distribuir.
