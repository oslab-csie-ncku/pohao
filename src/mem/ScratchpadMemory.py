from m5.params import *
from m5.objects.SimpleMemory import SimpleMemory

class ScratchpadMemory(SimpleMemory):
    type = 'ScratchpadMemory'
    cxx_header = "mem/scratchpad_mem.hh"

    ## SPM latency is equal to 2 cycles, which is based on gem5 default
    ## configuration.
    ## SPM bandwidth is equal to L1 cache bandwidth, which is based on:
    ## [1] Wiki - Memory hierarchy
    ##     (https://en.wikipedia.org/wiki/Memory_hierarchy)
    latency = '0.12ns'
    bandwidth = '700GB/s'

    support_flush = Param.Bool(False, "Support cache flush")
    reg_flush_addr = Param.Addr(0, "Flush addr register address")
    reg_flush_size = Param.Addr(0, "Flush size register address")
