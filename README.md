# FotoScan

Catalogação automática de fotografias com o modelo de visão DeepSeek (API
paga). Cada imagem recebe um título curto, uma descrição objetiva e 1–3
categorias escolhidas de um catálogo controlado.

## Requisitos

- Linux
- Python 3.10+
- Chave da API DeepSeek em `DEEPSEEK_API_KEY`:

```bash
export DEEPSEEK_API_KEY='sk-...'
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

# modelo DeepSeek diferente
fotoscan *.jpg -o catalogo.json -m deepseek-flash

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
  "deepseek": {
    "model": "deepseek-flash",        // modelo DeepSeek usado por omissão
    "base_url": "https://api.deepseek.com"
    // "api_key": "sk-..."            // alternativa a DEEPSEEK_API_KEY
  },
  "max_size": 512,          // lado maior da imagem enviada ao modelo
  "max_title": 30,          // limite de caracteres do título
  "max_desc": 200,          // limite de caracteres da descrição
  "max_categories": 3,      // máximo de categorias por foto
  "caminhos": {
    "categories": "categories.json",
    "criteria": "criteria.json",
    "look": "look.json",
    "filtro": "filtro.json"
  },
  "inferencia": {
    "num_predict": 300,     // teto de tokens gerados por foto
    "temperature": 0.2
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
| DeepSeek (pago) | `deepseek-flash` | 1M | Predefinição. ~$0,0004/foto. Requer `DEEPSEEK_API_KEY` |

Se o modelo devolver uma resposta vazia ou inválida, o `fotoscan` repete
automaticamente a chamada (até 3 tentativas por fotografia).

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
| `Formato de resposta inválido` | JSON truncado | aumente `inferencia.num_predict` no config.json |
| `Ficheiro de referência não encontrado` | configs não instaladas | `bash install.sh` |
| Fotos de telemóvel "deitadas" | EXIF | já corrigido automaticamente em `preparar_imagem` |

## Licença

Uso pessoal. Adicione um ficheiro `LICENSE` se for distribuir.
