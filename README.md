# FotoScan

Catalogação automática de fotografias com o modelo de visão DeepSeek (API
paga). Cada imagem recebe um título curto, uma descrição objetiva e 1–3
categorias escolhidas de um catálogo controlado.

## Requisitos

- Linux
- Python 3.10+
- Chave de API de um dos fornecedores (apenas o que usares é necessário):
  - **DeepSeek** (predefinição, pago) → `DEEPSEEK_API_KEY`
  - **OpenRouter** (modelos de visão **grátis**) → `OPENROUTER_API_KEY`

```bash
# predefinição — DeepSeek (pago, mais rápido/estável)
export DEEPSEEK_API_KEY='sk-...'

# opcional — OpenRouter (grátis, com limites de pedidos/dia)
export OPENROUTER_API_KEY='sk-or-v1-...'
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
# catálogo simples em JSON — usa o modelo DeepSeek por omissão
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

# usar um modelo de visão GRÁTIS via OpenRouter (define OPENROUTER_API_KEY)
fotoscan *.jpg -o catalogo.json --provedor openrouter
fotoscan *.jpg -o catalogo.json -m google/gemma-4-31b-it:free   # o '/' ativa o OpenRouter

# ler o data.json de um projeto já gerado
fotoscan --get-data projeto.zip
fotoscan --get-data projeto.zip -o dados.json

# ler os alertas de situações sensíveis de um projeto
fotoscan --get-alerts projeto.zip
```

A ajuda (`fotoscan -h`) lista apenas as opções; os exemplos completos ficam em
`fotoscan --exemplos`.

Sem `-o`, o JSON é impresso no `stdout` (útil para pipes).

**Formatos aceites:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`.

## Configuração

Configuração efetiva: `~/.config/fotoscan/config.json` (criada a partir de
`config/config.json` na instalação).

```jsonc
{
  "provedor": "deepseek",       // "deepseek" (pago, predefinição) ou "openrouter" (grátis)
  "deepseek": {
    "model": "deepseek-flash",        // modelo DeepSeek usado por omissão
    "base_url": "https://api.deepseek.com"
    // "api_key": "sk-..."            // alternativa a DEEPSEEK_API_KEY
  },
  "openrouter": {
    "model": "google/gemma-4-31b-it:free",  // modelo de visão GRÁTIS
    "base_url": "https://openrouter.ai/api/v1",
    "fallback": [                            // modelos de reserva quando há limite (429)
      "nvidia/nemotron-3.5-super-vl:free",
      "google/gemma-4-26b-a4b-it:free",
      "openrouter/free"
    ]
    // "api_key": "sk-or-v1-..."      // alternativa a OPENROUTER_API_KEY
  },
  "max_size": 512,          // lado maior da imagem enviada ao modelo
  "max_title": 50,          // limite de caracteres do título (corte por palavras)
  "max_desc": 200,          // limite de caracteres da descrição
  "max_categories": 3,      // máximo de categorias por foto
  "caminhos": {
    "categories": "categories.json",
    "criteria": "criteria.json",
    "look": "look.json",
    "filtro": "filtro.json"
  },
  "inferencia": {
    "num_predict": 600,     // teto de tokens gerados por foto
    "temperature": 0.2,
    "thinking": "disabled"  // desliga o raciocínio (evita respostas vazias)
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

## Modelo

| Backend | Modelo | Contexto | Notas |
| --- | --- | ---: | --- |
| DeepSeek (pago) | `deepseek-flash` | 1M | **Predefinição.** ~$0,0004/foto. Requer `DEEPSEEK_API_KEY` |
| OpenRouter (grátis) | `google/gemma-4-31b-it:free` | 262K | Visão grátis. Requer `OPENROUTER_API_KEY`. Tem limites (~50 pedidos/dia). Usado com `--provedor openrouter` |

Outros modelos de visão grátis do OpenRouter podem ser escolhidos com `-m`
(ex.: `-m nvidia/nemotron-3.5-super-vl:free`,
`-m google/gemma-4-26b-a4b-it:free`,
`-m openrouter/free`). Qualquer `-m` com `/` ativa o OpenRouter automaticamente.

**Fallback automático:** como os modelos grátis têm limites partilhados
(~50 pedidos/dia por fornecedor), o FotoScan troca automaticamente de modelo
quando um atinge o limite (erro 429). A ordem é a principal → `fallback` da
config (ver `openrouter.fallback`).

> Os modelos "free" da **DeepSeek** no OpenRouter são só texto (não têm visão),
> por isso não servem para o FotoScan.

Se o modelo devolver uma resposta vazia ou inválida, o `fotoscan` repete
automaticamente a chamada. Os modelos da família V4 têm o modo "thinking"
(raciocínio) desligado por omissão — é o raciocínio que, quando ativo, consumia
o orçamento de tokens e devolvia `content` vazio (`finish_reason=length`).

## Estrutura

```text
FotoScan/
├── install.sh                # instalação (venv + configs + symlink)
├── uninstall.sh              # desinstalação (remove o symlink; configs/.venv opcionais)
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
│   └── main.py               # CLI (argumentos, lote, exportação ZIP/JSON)
├── tests/                    # pytest
└── docs/                     # instalação e configuração
```

## Desinstalação

```bash
bash uninstall.sh                          # remove apenas ~/.local/bin/fotoscan
bash uninstall.sh --purge-config           # remove também ~/.config/fotoscan
bash uninstall.sh --purge-config --purge-venv   # remove também o .venv/
```

O código-fonte do projeto nunca é tocado.

## Testes

```bash
.venv/bin/python -m pytest -q
```

## Resolução de problemas

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| `DEEPSEEK_API_KEY não definida` | chave em falta | `export DEEPSEEK_API_KEY='sk-...'` ou `deepseek.api_key` no config.json |
| `DeepSeek devolveu HTTP 4xx/5xx` | chave inválida, saldo ou limite | verifique a chave e o saldo na conta DeepSeek |
| `Resposta do modelo não é JSON válido: ''` | modelo devolveu `content` vazio (raciocínio a consumir os tokens) | garanta `inferencia.thinking: "disabled"` e aumente `inferencia.num_predict` |
| `Formato de resposta inválido` | JSON truncado | aumente `inferencia.num_predict` no config.json |
| `Ficheiro de referência não encontrado` | configs não instaladas | `bash install.sh` |
| Fotos de telemóvel "deitadas" | EXIF | já corrigido automaticamente em `preparar_imagem` |

## Licença

Uso pessoal. Adicione um ficheiro `LICENSE` se for distribuir.
