# Configuração e Instalação — FotoScan

Guia de instalação e utilização do utilitário `fotoscan`.

> Caminho de referência neste documento: `/mnt/dados/Projetos/1_Scripts/FotoScan`.
> Se o projeto estiver noutro sítio, substitua esse caminho.

## 1. Estrutura dos Ficheiros

```text
FotoScan/
├── install.sh                # instalação automática
├── uninstall.sh              # desinstalação
├── run.sh                    # wrapper executável
├── requirements.txt          # dependências de execução (Pillow)
├── requirements-dev.txt      # dependências de teste (pytest)
├── README.md
├── config/
│   ├── config.json           # configuração de referência
│   ├── categories.json       # catálogo de categorias (grupos + categorias)
│   ├── criteria.json         # critérios de análise (geram as flags da CLI)
│   ├── look.json             # olhares (lentes de análise)
│   └── filtro.json           # situações sensíveis (--sensivel)
├── src/
│   └── main.py               # CLI
├── tests/
└── docs/
```

Não existe um script `fotoscan` na raiz: o executável é o `run.sh`, que
invoca `src/main.py` com o Python do `.venv` (o `install.sh` cria o atalho
`~/.local/bin/fotoscan` para esse wrapper).

---

## 2. Pré-requisitos

- Python 3.10+
- Chave da API DeepSeek (serviço pago):

```bash
export DEEPSEEK_API_KEY='sk-...'
```

Alternativa: definir `deepseek.api_key` em `~/.config/fotoscan/config.json`.

---

## 3. Instalação Automatizada

```bash
cd /mnt/dados/Projetos/1_Scripts/FotoScan
bash install.sh
```

O script:

1. cria o ambiente virtual `.venv/` (se não existir);
2. instala as dependências de `requirements.txt`;
3. copia `config/*.json` para `~/.config/fotoscan/`;
4. dá permissão de execução ao `run.sh`;
5. cria o symlink `~/.local/bin/fotoscan → run.sh`.

Para substituir configurações já existentes (cria `.bak` antes):

```bash
bash install.sh --force-config
```

Confirme que `~/.local/bin` está no `$PATH`:

```bash
echo "$PATH" | tr ':' '\n' | grep -qx "$HOME/.local/bin" || \
  echo 'Adicione: export PATH="$HOME/.local/bin:$PATH"'
```

Para desenvolvimento (inclui `pytest`):

```bash
.venv/bin/pip install -r requirements-dev.txt
```

### Desinstalação

```bash
bash uninstall.sh            # remove apenas ~/.local/bin/fotoscan
bash uninstall.sh --purge-config --purge-venv   # remove também configs e .venv/
```

O código-fonte do projeto nunca é tocado; o symlink só é removido se apontar
para este projeto.

---

## 4. Execução Manual via `run.sh`

Sem instalar nada globalmente:

```bash
chmod +x /mnt/dados/Projetos/1_Scripts/FotoScan/run.sh
/mnt/dados/Projetos/1_Scripts/FotoScan/run.sh *.jpg -o projeto.zip --pessoas --cenario
```

O `run.sh` falha com mensagem clara se o `.venv` não existir.

---

## 5. Instalação Manual (sem `install.sh`)

```bash
cd /mnt/dados/Projetos/1_Scripts/FotoScan

# 1. Ambiente virtual e dependências
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 2. Permissões
chmod +x run.sh

# 3. Configurações em ~/.config/fotoscan
mkdir -p ~/.config/fotoscan
cp config/*.json ~/.config/fotoscan/

# 4. Executável global (symlink, para manter a referência ao projeto)
mkdir -p ~/.local/bin
ln -sfn "$PWD/run.sh" ~/.local/bin/fotoscan
```

> **Nota:** o `install.sh` usa `ln -sfn` e **não** `install -m 755`. Copiar o
> `run.sh` para `~/.local/bin` quebraria o script, porque ele procura `.venv/`
> e `src/` a partir do próprio diretório.

---

## 6. Configuração

Configuração efetiva: `~/.config/fotoscan/config.json`.
Os ficheiros `categories.json` e `criteria.json` são procurados, por esta ordem,
em: caminho indicado em `caminhos`, `~/.config/fotoscan/`, `$PWD`.

Principais chaves:

| Chave | Efeito |
| --- | --- |
| `provedor` | fornecedor por omissão: `deepseek` (pago, predefinição) ou `openrouter` (grátis) |
| `deepseek.model` | modelo DeepSeek usado por omissão (`deepseek-flash`) |
| `deepseek.base_url` | endpoint da API (`https://api.deepseek.com`) |
| `deepseek.api_key` | chave da API (alternativa a `DEEPSEEK_API_KEY`) |
| `openrouter.model` | modelo grátis usado por omissão (`google/gemma-4-31b-it:free`) |
| `openrouter.base_url` | endpoint do OpenRouter (`https://openrouter.ai/api/v1`) |
| `openrouter.fallback` | lista de modelos de reserva quando o principal atinge o limite (429) |
| `openrouter.api_key` | chave do OpenRouter (alternativa a `OPENROUTER_API_KEY`) |
| `max_size` | lado maior (px) da imagem enviada ao modelo |
| `max_title` / `max_desc` | limites de caracteres aplicados à resposta (o corte é feito por palavras, sem partir palavras a meio) |
| `max_categories` | máximo de categorias por fotografia |
| `inferencia.num_predict` | teto de tokens gerados por fotografia |
| `inferencia.temperature` | criatividade do modelo (0.2 = factual) |
| `inferencia.thinking` | `"disabled"` desliga o raciocínio (evita respostas vazias) |
| `inferencia.avisar_peak` | `true` avisa quando a DeepSeek está em horário peak (tokens a 2x) |

Cada chave de `criteria.json` gera automaticamente uma flag:

| Critério | Flag |
| --- | --- |
| Pessoas | `--pessoas` |
| Expressões | `--expressoes` |
| Ação | `--acao` |
| Contexto | `--contexto` |
| Cenário | `--cenario` |
| Arquitetura | `--arquitetura` |
| Mensagens | `--mensagens` |
| Objetos | `--objetos` |
| Interação | `--interacao` |
| Técnica | `--tecnica` |

### Modelos de visão GRÁTIS (OpenRouter) — opcional

O FotoScan usa, por omissão, o modelo **pago** da DeepSeek. Para não gastar
créditos, podes mudar para um modelo de visão **grátis** via OpenRouter:

```bash
export OPENROUTER_API_KEY='sk-or-v1-...'

# opção A — pelo seletor de fornecedor
fotoscan *.jpg -o catalogo.json --provedor openrouter

# opção B — indicando o modelo diretamente (o '/' ativa o OpenRouter)
fotoscan *.jpg -o catalogo.json -m google/gemma-4-31b-it:free
```

Outros modelos de visão grátis: `nvidia/nemotron-3.5-super-vl:free`,
`google/gemma-4-26b-a4b-it:free`, `openrouter/free`.

> Os modelos "free" da **DeepSeek** no OpenRouter são só texto (sem visão), por
> isso não servem para o FotoScan. Os modelos grátis têm limites partilhados
> (~50 pedidos/dia por fornecedor).

**Fallback automático:** quando um modelo grátis atinge o limite (erro 429), o
FotoScan troca automaticamente para o modelo seguinte da lista `fallback`. Por
isso, para lotes grandes (mais de ~50 fotos), ele vai rodando pelos vários
fornecedores grátis em vez de parar.

Para voltar ao modelo PAGO da DeepSeek:
`fotoscan *.jpg --provedor deepseek` (define `DEEPSEEK_API_KEY`) ou define
`"provedor": "deepseek"` em `~/.config/fotoscan/config.json`.

### Poupar na DeepSeek (horário peak vs off-peak)

A DeepSeek cobra o **dobro** em horário *peak*: **01:00–04:00 e 06:00–10:00 UTC**,
de segunda a sexta. Todo o resto (incluindo sábados e domingos) é *off-peak*,
com **50% de desconto**.

O FotoScan mostra um aviso quando arrancas em horário peak (desligável com
`inferencia.avisar_peak: false`). Custo típico: ~$0,0004/foto off-peak,
ou seja ~$0,04 para 102 fotos.

---

## 7. Teste

```bash
fotoscan --help
fotoscan *.jpg -o projeto.zip --pessoas --cenario
fotoscan --get-data projeto.zip
```

Testes unitários:

```bash
.venv/bin/python -m pytest -q
```
