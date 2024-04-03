#!/bin/bash
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 FILE REMOTE_PORT"
    exit
fi

gdb \
    -q \
    -ex "file $1" \
    -ex "target remote :$2"
