#!/usr/bin/env bash
set -e

DIRETORIO_PROJETO="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DESTINO_BIN="$HOME/.local/bin"
PASTA_CONFIG="$HOME/.config/fotoscan"

# Por omissão, remove apenas o executável 'fotoscan' (~/.local/bin/fotoscan).
# As tuas configurações e o ambiente virtual são preservados.
#
#   --purge-config   remove também ~/.config/fotoscan (inclui backups .bak)
#   --purge-venv     remove também o ambiente virtual .venv/ do projeto
PURGAR_CONFIG=0
PURGAR_VENV=0
for arg in "$@"; do
    case "$arg" in
        --purge-config) PURGAR_CONFIG=1 ;;
        --purge-venv) PURGAR_VENV=1 ;;
        *) echo "Opção desconhecida: $arg" >&2
           echo "Uso: bash uninstall.sh [--purge-config] [--purge-venv]" >&2
           exit 1 ;;
    esac
done

echo "==> A desinstalar o FotoScan de: $DIRETORIO_PROJETO"

# 1. Remover o symlink/executável global (apenas se apontar para este projeto)
ALVO="$DESTINO_BIN/fotoscan"
if [ -L "$ALVO" ]; then
    if [ "$(readlink -f "$ALVO")" = "$DIRETORIO_PROJETO/run.sh" ]; then
        rm -f "$ALVO"
        echo "    ✔ $ALVO removido"
    else
        echo "    ! $ALVO é um symlink para outro local ($(readlink -f "$ALVO")); mantido"
    fi
elif [ -e "$ALVO" ]; then
    echo "    ! $ALVO existe mas não é um symlink; mantido (remove manualmente se for teu)"
else
    echo "    = $ALVO não existe; nada a remover"
fi

# 2. Remover configurações do utilizador (opcional)
if [ "$PURGAR_CONFIG" -eq 1 ]; then
    if [ -d "$PASTA_CONFIG" ]; then
        rm -rf "$PASTA_CONFIG"
        echo "    ✔ $PASTA_CONFIG removido"
    else
        echo "    = $PASTA_CONFIG não existe; nada a remover"
    fi
else
    echo "    = configurações em $PASTA_CONFIG preservadas"
    echo "      (usa 'bash uninstall.sh --purge-config' para as remover)"
fi

# 3. Remover o ambiente virtual do projeto (opcional)
if [ "$PURGAR_VENV" -eq 1 ]; then
    if [ -d "$DIRETORIO_PROJETO/.venv" ]; then
        rm -rf "$DIRETORIO_PROJETO/.venv"
        echo "    ✔ .venv/ removido"
    else
        echo "    = .venv/ não existe; nada a remover"
    fi
else
    echo "    = ambiente virtual .venv/ preservado"
    echo "      (usa 'bash uninstall.sh --purge-venv' para o remover)"
fi

echo "✔ Desinstalação concluída."
echo "O código-fonte do projeto em '$DIRETORIO_PROJETO' não foi tocado."
