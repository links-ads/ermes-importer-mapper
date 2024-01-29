#!/bin/sh

ProgName=$(basename $0)

cmd_help() {
    echo "Usage: $ProgName (help|importer|webserver)"
}

cmd_importer() {
    until python /wait.py; do
        sleep 1
    done
    echo "Applying migrations..."
    alembic upgrade head
    echo "Starting importer..."
    python3 -m importer
    exit $?
}

cmd_webserver() {
    until python /wait.py; do
        sleep 1
    done
    echo "Applying migrations..."
    alembic upgrade head
    echo "Starting webserver..."
    uvicorn importer.asgi:app --host 0.0.0.0 --port 7500 # --root-path ${ROOT_PATH:-/}
    exit $?
}

subcommand=$1
case ${subcommand} in
"" | "-h" | "--help")
    cmd_help
    ;;
*)
    shift
    cmd_${subcommand} $@
    echo "Done!"
    if [[ $? == 127 ]]; then
        echo "Error: '$subcommand' is not a known subcommand." >&2
        echo "       Run '$(basename $0) --help' for a list of known subcommands." >&2
        exit 1
    fi
    ;;
esac
