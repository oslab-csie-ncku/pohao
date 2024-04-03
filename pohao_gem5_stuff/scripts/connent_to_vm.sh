#!/bin/bash

M5TERM_DIR=./util/term

if ! [ -e "$M5TERM_DIR/m5term" ]; then
    make -C "$M5TERM_DIR"
fi

if [ -z "$1" ]; then
    "$M5TERM_DIR/m5term" 127.0.0.1 3456
else
    "$M5TERM_DIR/m5term" 127.0.0.1 "$1"
fi

