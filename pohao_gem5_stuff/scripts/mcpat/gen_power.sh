#!/bin/bash

SUFFIX=_mcpat
MCPAT=./pohao_gem5_stuff/mcpat/mcpat

if ! [ -e "$MCPAT" ]; then
    echo ""$MCPAT" not exist!"
    exit
fi

if [ -z "$1" ]; then
    echo "Usage: "$0" /path/to/power.xml"
    exit
fi

"$MCPAT" -infile "$1" -print_level 0 -opt_for_clk 0 > "$1""$SUFFIX"

echo "Successfully generated McPat result: "$1""$SUFFIX""
