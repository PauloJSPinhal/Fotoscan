#!/usr/bin/env bash
set -e

# Localizar o diretório base do projeto de forma robusta
DIRETORIO_PROJETO="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PYTHON_VENV="$DIRETORIO_PROJETO/.venv/bin/python3"
SCRIPT_PYTHON="$DIRETORIO_PROJETO/src/main.py"

# Garantir que o ambiente virtual existe
if [ ! -f "$PYTHON_VENV" ]; then
    echo "Erro: Ambiente virtual não encontrado em $DIRETORIO_PROJETO/.venv" >&2
    echo "Execute 'bash install.sh' primeiro para configurar o ambiente." >&2
    exit 1
fi

# Executar o script Python passando todos os argumentos recebidos na CLI
exec "$PYTHON_VENV" "$SCRIPT_PYTHON" "$@"