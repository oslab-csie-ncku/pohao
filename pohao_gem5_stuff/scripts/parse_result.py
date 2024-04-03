#!/usr/bin/python

import sys
import os
import xml.etree.ElementTree

SUMMARY_SUFFIX = "_summary.xml"
MCPAT_SUFFIX = "_power.xml_mcpat"

def parse_summary(filename):
    root = xml.etree.ElementTree.parse(filename).getroot()

    # system
    for stat in root.findall('component/stat'):
        if stat.get('name') == "sim_ticks":
            print("system.sim_ticks (ps)\t%s" % stat.get('value'))
            break

    # itb
    for component in root.findall('component/component/component'):
        if component.get('id') == "system.cpu.itb":
            rdAccesses = ""
            wrAccesses = ""
            total_accesses = ""
            rdMisses = ""
            wrMisses = ""
            total_misses = ""
            for stat in component.findall('stat'):
                if (stat.get('name') == "rdAccesses"):
                    rdAccesses = stat.get('value')
                if (stat.get('name') == "wrAccesses"):
                    wrAccesses = stat.get('value')
                if (stat.get('name') == "total_accesses"):
                    total_accesses = stat.get('value')
                if (stat.get('name') == "rdMisses"):
                    rdMisses = stat.get('value')
                if (stat.get('name') == "wrMisses"):
                    wrMisses = stat.get('value')
                if (stat.get('name') == "total_misses"):
                    total_misses = stat.get('value')

            print("system.cpu.itb.rdAccesses\t%s" % rdAccesses)
            print("system.cpu.itb.wrAccesses\t%s" % wrAccesses)
            print("system.cpu.itb.total_accesses\t%s" % total_accesses)
            print("system.cpu.itb.rdMisses\t%s" % rdMisses)
            print("system.cpu.itb.wrMisses\t%s" % wrMisses)
            print("system.cpu.itb.total_misses\t%s" % total_misses)
            print("system.cpu.itb.total_miss_rate\t%s" % (float(total_misses) / float(total_accesses)))

            break

    # dtb
    for component in root.findall('component/component/component'):
        if component.get('id') == "system.cpu.dtb":
            rdAccesses = ""
            wrAccesses = ""
            total_accesses = ""
            rdMisses = ""
            wrMisses = ""
            total_misses = ""
            for stat in component.findall('stat'):
                if (stat.get('name') == "rdAccesses"):
                    rdAccesses = stat.get('value')
                if (stat.get('name') == "wrAccesses"):
                    wrAccesses = stat.get('value')
                if (stat.get('name') == "total_accesses"):
                    total_accesses = stat.get('value')
                if (stat.get('name') == "rdMisses"):
                    rdMisses = stat.get('value')
                if (stat.get('name') == "wrMisses"):
                    wrMisses = stat.get('value')
                if (stat.get('name') == "total_misses"):
                    total_misses = stat.get('value')

            print("system.cpu.dtb.rdAccesses\t%s" % rdAccesses)
            print("system.cpu.dtb.wrAccesses\t%s" % wrAccesses)
            print("system.cpu.dtb.total_accesses\t%s" % total_accesses)
            print("system.cpu.dtb.rdMisses\t%s" % rdMisses)
            print("system.cpu.dtb.wrMisses\t%s" % wrMisses)
            print("system.cpu.dtb.total_misses\t%s" % total_misses)
            print("system.cpu.dtb.total_miss_rate\t%s" % (float(total_misses) / float(total_accesses)))

            break

    # icache
    for component in root.findall('component/component/component'):
        if component.get('id') == "system.cpu.icache":
            demand_hits = ""
            demand_misses = ""
            demand_accesses = ""
            demand_miss_rate = ""
            for stat in component.findall('stat'):
                if (stat.get('name') == "demand_hits::total"):
                    demand_hits = stat.get('value')
                if (stat.get('name') == "demand_misses::total"):
                    demand_misses = stat.get('value')
                if (stat.get('name') == "demand_accesses::total"):
                    demand_accesses = stat.get('value')
                if (stat.get('name') == "demand_miss_rate::total"):
                    demand_miss_rate = stat.get('value')

            print("system.cpu.icache.demand_hits::total\t%s" % demand_hits)
            print("system.cpu.icache.demand_misses::total\t%s" % demand_misses)
            print("system.cpu.icache.demand_accesses::total\t%s" % demand_accesses)
            print("system.cpu.icache.demand_miss_rate::total\t%s" % demand_miss_rate)

            break

    # dcache
    for component in root.findall('component/component/component'):
        if component.get('id') == "system.cpu.dcache":
            demand_hits = ""
            demand_misses = ""
            demand_accesses = ""
            demand_miss_rate = ""
            for stat in component.findall('stat'):
                if (stat.get('name') == "demand_hits::total"):
                    demand_hits = stat.get('value')
                if (stat.get('name') == "demand_misses::total"):
                    demand_misses = stat.get('value')
                if (stat.get('name') == "demand_accesses::total"):
                    demand_accesses = stat.get('value')
                if (stat.get('name') == "demand_miss_rate::total"):
                    demand_miss_rate = stat.get('value')

            print("system.cpu.dcache.demand_hits::total\t%s" % demand_hits)
            print("system.cpu.dcache.demand_misses::total\t%s" % demand_misses)
            print("system.cpu.dcache.demand_accesses::total\t%s" % demand_accesses)
            print("system.cpu.dcache.demand_miss_rate::total\t%s" % demand_miss_rate)

            break

    # l2
    for component in root.findall('component/component'):
        if component.get('id') == "system.l2":
            demand_hits = ""
            demand_misses = ""
            demand_accesses = ""
            demand_miss_rate = ""
            for stat in component.findall('stat'):
                if (stat.get('name') == "demand_hits::total"):
                    demand_hits = stat.get('value')
                if (stat.get('name') == "demand_misses::total"):
                    demand_misses = stat.get('value')
                if (stat.get('name') == "demand_accesses::total"):
                    demand_accesses = stat.get('value')
                if (stat.get('name') == "demand_miss_rate::total"):
                    demand_miss_rate = stat.get('value')

            print("system.l2.demand_hits::total\t%s" % demand_hits)
            print("system.l2.demand_misses::total\t%s" % demand_misses)
            print("system.l2.demand_accesses::total\t%s" % demand_accesses)
            print("system.l2.demand_miss_rate::total\t%s" % demand_miss_rate)

            break

    # mc
    for component in root.findall('component/component'):
        if component.get('id') == "system.mc":
            mem_reads = ""
            mem_writes = ""
            mem_accesses = ""
            for stat in component.findall('stat'):
                if (stat.get('name') == "mem_reads"):
                    mem_reads = stat.get('value')
                if (stat.get('name') == "mem_writes"):
                    mem_writes = stat.get('value')
                if (stat.get('name') == "mem_accesses"):
                    mem_accesses = stat.get('value')

            print("system.mc.mem_reads\t%s" % mem_reads)
            print("system.mc.mem_writes\t%s" % mem_writes)
            print("system.mc.mem_accesses\t%s" % mem_accesses)

            break

def parse_mcpat(filename):
    f = open(filename, 'r')

    for s in f:
        if s.find('Total Leakage') != -1:
            leakage = s.split("=")[1].split(" ")[1]
            print("Total Leakage (W)\t%s" % leakage)
        if s.find('Runtime Dynamic') != -1:
            dynamic = s.split("=")[1].split(" ")[1]
            print("Runtime Dynamic (W)\t%s" % dynamic)
            break

    f.close()

def main(argv):
    # Check argv
    if len(argv) != 2:
        sys.exit("Usage: %s stats_filename" % argv[0])

    # Check file
    STATS_FILE = argv[1]
    SUMMARY_FILE = "%s%s" % (STATS_FILE, SUMMARY_SUFFIX)
    MCPAT_FILE = "%s%s" % (STATS_FILE, MCPAT_SUFFIX)

    if os.path.isfile(SUMMARY_FILE) == False:
        sys.exit("summary file %s not exist!" % SUMMARY_FILE)

    if os.path.isfile(MCPAT_FILE) == False:
        sys.exit("mcpat file %s not exist!" % MCPAT_FILE)

    # Start
    parse_summary(SUMMARY_FILE)
    parse_mcpat(MCPAT_FILE)

if __name__ == "__main__":
    main(sys.argv)
