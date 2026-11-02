# Configuração e Instalação — FotoScan

Guia de instalação e utilização do utilitário `fotoscan`.

> Caminho de referência neste documento: `/mnt/dados/Projetos/1_Scripts/Taksinomos`.
> Se o projeto estiver noutro sítio, substitua esse caminho.

## 1. Estrutura dos Ficheiros

```text
Taksinomos/   # diretório do projeto (o utilitário chama-se fotoscan)
├── Modelfile                 # variante leve do modelo (opcional)
├── install.sh                # instalação automática
├── run.sh                    # wrapper executável
├── requirements.txt          # dependências de execução (Pillow)
├── requirements-dev.txt      # dependências de teste (pytest)
├── README.md
├── config/
│   ├── config.json           # configuração de referência
│   ├── categories.json       # catálogo de categorias (grupos + categorias)
│   └── criteria.json         # critérios de análise (geram as flags da CLI)
├── src/
│   ├── main.py               # CLI
│   ├── api/client.py         # OllamaClient (HTTP)
│   ├── core/classifier.py    # Classifier (validação)
│   └── utils/mage_loader.py  # utilitários de imagem
├── tests/
└── docs/
```

Não existe um script `fotoscan` na raiz: o executável é o `run.sh`, que
invoca `src/main.py` com o Python do `.venv` (o `install.sh` cria o atalho
`~/.local/bin/fotoscan` para esse wrapper).

---

## 2. Pré-requisitos

```bash
# Ollama instalado e no PATH
ollama --version

# Modelo multimodal (padrão do projeto)
ollama pull qwen2.5vl:3b
```

---

## 3. Instalação Automatizada

```bash
cd /mnt/dados/Projetos/1_Scripts/Taksinomos
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

---

## 4. Execução Manual via `run.sh`

Sem instalar nada globalmente:

```bash
chmod +x /mnt/dados/Projetos/1_Scripts/Taksinomos/run.sh
/mnt/dados/Projetos/1_Scripts/Taksinomos/run.sh *.jpg -o projeto.zip --pessoas --cenario
```

O `run.sh` falha com mensagem clara se o `.venv` não existir.

---

## 5. Instalação Manual (sem `install.sh`)

```bash
cd /mnt/dados/Projetos/1_Scripts/Taksinomos

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
| `modelo` | modelo Ollama usado por omissão |
| `max_size` | lado maior (px) da imagem enviada ao modelo |
| `max_title` / `max_desc` | limites de caracteres aplicados à resposta |
| `max_categories` | máximo de categorias por fotografia |
| `servidor.url` | endpoint do Ollama |
| `servidor.auto_start` | arranca `ollama serve` se estiver em baixo |
| `servidor.timeout` | segundos de espera pelo arranque |

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
