#!/bin/bash
COMPILE_OPTIONS='--gold-linker --colors'
COMPILE_JOBS=`nproc`
GLOBAL_BUILD_VARIABLES=""

##
 # $1 = arch 
 # $2 = gem5 binary type
 # $3 = build variables
function compile_gem5()
{
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo "Usage: compile_gem5 ARCH BINARY_TYPE BUILD_VARIABLES"
    fi

    if [ "$3" ]; then
        GLOBAL_BUILD_VARIABLES="$GLOBAL_BUILD_VARIABLES $3"
    fi

    scons \
        $COMPILE_OPTIONS \
        -j "$COMPILE_JOBS" \
        $GLOBAL_BUILD_VARIABLES \
        ./build/"$1"/gem5."$2"
}
