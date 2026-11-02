#!/usr/bin/env bash
set -e

DIRETORIO_PROJETO="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DESTINO_BIN="$HOME/.local/bin"
PASTA_CONFIG="$HOME/.config/fotoscan"

# Por omissão, configurações existentes em ~/.config são preservadas.
# Usa 'bash install.sh --force-config' para as substituir pelos ficheiros do projeto.
FORCAR_CONFIG=0
for arg in "$@"; do
    case "$arg" in
        --force-config) FORCAR_CONFIG=1 ;;
        *) echo "Opção desconhecida: $arg" >&2; exit 1 ;;
    esac
done

echo "==> A configurar o FotoScan em: $DIRETORIO_PROJETO"

# 1. Criar ambiente virtual se não existir
if [ ! -d "$DIRETORIO_PROJETO/.venv" ]; then
    echo "--> A criar ambiente virtual (.venv)..."
    python3 -m venv "$DIRETORIO_PROJETO/.venv"
fi

# 2. Instalar dependências via requirements.txt
echo "--> A instalar dependências a partir de requirements.txt..."
"$DIRETORIO_PROJETO/.venv/bin/pip" install --upgrade pip --quiet
"$DIRETORIO_PROJETO/.venv/bin/pip" install -r "$DIRETORIO_PROJETO/requirements.txt" --quiet

# 3. Copiar ficheiros de configuração para ~/.config/fotoscan
echo "--> A instalar ficheiros de configuração em $PASTA_CONFIG..."
mkdir -p "$PASTA_CONFIG"

if ! compgen -G "$DIRETORIO_PROJETO/config/*.json" > /dev/null; then
    echo "Erro: não foram encontrados ficheiros .json em '$DIRETORIO_PROJETO/config'." >&2
    exit 1
fi

for origem in "$DIRETORIO_PROJETO"/config/*.json; do
    nome="$(basename "$origem")"
    destino="$PASTA_CONFIG/$nome"

    if [ ! -f "$destino" ]; then
        install -m 644 "$origem" "$destino"
        echo "    ✔ $nome copiado"
    elif cmp -s "$origem" "$destino"; then
        echo "    = $nome já está atualizado"
    elif [ "$FORCAR_CONFIG" -eq 1 ]; then
        cp -p "$destino" "$destino.bak"
        install -m 644 "$origem" "$destino"
        echo "    ↻ $nome substituído (backup: $nome.bak)"
    else
        echo "    ! $nome existente difere do projeto; mantido"
        echo "      (usa 'bash install.sh --force-config' para substituir)"
    fi
done

# 4. Dar permissão de execução ao wrapper
chmod +x "$DIRETORIO_PROJETO/run.sh"

# 5. Criar diretório de binários local se não existir
mkdir -p "$DESTINO_BIN"

# 6. Instalar o wrapper globalmente como 'fotoscan' através de symlink.
#    Um symlink preserva a localização real do projeto; copiar o run.sh
#    faria com que este procurasse .venv e src/ em ~/.local/bin.
echo "--> A instalar executável em $DESTINO_BIN/fotoscan..."
ln -sfn "$DIRETORIO_PROJETO/run.sh" "$DESTINO_BIN/fotoscan"

echo "✔ Instalação concluída com sucesso!"
echo "Pode agora executar diretamente em qualquer pasta:"
echo "   fotoscan --help"
