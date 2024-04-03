#!/usr/bin/env python

"""
SYNOPSIS

    m5-mcpat-parse.py [-h] [...]

DESCRIPTION

    m5-mcpat-parse.py is a script for parsing M5 output and generating mcpat
    compatible xml. It is expected that you will want to modify this script to
    be compatible with your particular system.

    Note that comments are present in the code to direct your attention.
    #TODO  signifies that you should set the default value to match your systems
           parameters. If you have added this system parameter to the config.ini
           file, then you can put the related string filter in the m5_key field.
    #FIXME indicates a stat that I was not sure about and that you should check
           if you notice inconsistencies with expected behavior.

    Likely, most of the changes you will add are in the functions addPowerParam
    and addPowerStat.
    m5_key represents a unique string filter that identifies the stat in
    config.ini or stats output file.
    power_key is the corresponding McPat interface id that identifies the node
    in mcpat xml interface.
    By changing M5_keys, you can capture stats and params that you require.
    If you realize that you need to capture a stat that is dependent on other
    stats, please look at the function generateCalcStats() for an example of how
    to add calculated stats.

SOURCE

    https://bitbucket.org/rickshin/m5-mcpat-parser/src/default/m5-mcpat-parse-se.py

"""

import sys
import os
import traceback
import optparse
import time
import re
import math


def panic(msg, code = -1):
    print("Panic: %s" % msg)
    os.sys.exit(code)

def warning(msg):
    print("Warning: %s" % msg)

def sortComponentList(components):
    names = []
    temp_hash = {}

    for comp in components:
        names.append(comp.name)
        temp_hash[comp.name] = comp
    names.sort()

    ret = []
    for comp_name in names:
        ret.append(temp_hash[comp_name])

    return ret

class Component:
    UNKNOWN = None
    FILTER_TYPES = ["IsaFake", "SimpleDisk", "Terminal", "Crossbar",
                    "IntrControl", "IdeDisk", "ExeTracer",
                    "Tracer", "Bridge", "AtomicSimpleCPU", "FUPool", "BusConn",
                    "SetAssociative", "BaseSetAssoc", "SrcClockDomain",
                    "VoltageDomain", "X86PagetableWalker", "SnoopFilter"]

    def __init__(self, id, params, name = None):
        self.name = name if name != None else id.split('.')[-1]
        self.id = id
        self.params = params
        self.re_id = None
        self.re_name = None
        self.translated_params = {}
        self.translated_params_order = []
        self.children = []
        self.statistics = {}
        self.translated_statistics = {}
        self.calc_statistics = {}
        self.translator = Component.UNKNOWN
        self.power_xml_filter = False
        self.translated_statistics_order = []

    def formXml(self, parent_node, doc):
        new_component = doc.createElement("component")
        parent_node.appendChild(new_component)
        new_component.setAttribute("id", self.id)
        new_component.setAttribute("name", self.name)

        # Add params settings
        for param_key in self.params:
            new_param = doc.createElement("param")
            new_param.setAttribute("name", param_key)
            new_param.setAttribute("value", self.params[param_key])
            new_component.appendChild(new_param)

        # Add statistics
        for stat_key in self.statistics:
            new_stat = doc.createElement("stat")
            new_stat.setAttribute("name", stat_key)
            new_stat.setAttribute("value", self.statistics[stat_key])
            new_component.appendChild(new_stat)

        # Add architectural stats for this level
        for child in self.children:
            child.formXml(new_component, doc)

    def formXmlPower(self, parent_node, doc, options):
        if self.power_xml_filter == True:
            return

        new_component = doc.createElement("component")
        parent_node.appendChild(new_component)
        new_component.setAttribute("id", self.id if self.re_id == None else self.re_id)
        new_component.setAttribute("name", self.name if self.re_name == None else self.re_name)

        # Add params settings
        for param_key in self.translated_params_order:
            new_param = doc.createElement("param")
            new_param.setAttribute("name", param_key)
            new_param.setAttribute("value", self.translated_params[param_key])
            new_component.appendChild(new_param)

        # Add statistics
        for stat_key in self.translated_statistics_order:
            new_stat = doc.createElement("stat")
            new_stat.setAttribute("name", stat_key)
            new_stat.setAttribute("value", self.translated_statistics[stat_key])
            new_component.appendChild(new_stat)

        # Update child & re-order children for xml output for system
        if self.name == options.system_name:
            new_children = []
            filters = [options.cpu_name, "L1Directory", "l2", "tol2bus", "mc", "niu", "pcie", "flashc"]
            unfilters = [None, None, "Directory", None, None, None, None, None]
            unfilters2 = [None, None, "bus", None, None, None, None, None]
            filter_pair = zip(filters, unfilters, unfilters2)
            for filter, unfilter, unfilter2 in filter_pair:
                temp_new = []
                for child in self.children:
                    if filter in child.name:
                        if (unfilter == None or unfilter not in child.name) and (unfilter2 == None or unfilter2 not in child.name):
                            temp_new.append(child)
                new_children += sortComponentList(temp_new)

            self.children = new_children

        # Update child & re-order children for xml output for CPU
        if self.params.has_key('type') and (self.params['type'] == "DerivO3CPU" or self.params['type'] == "TimingSimpleCPU"):
            new_children = []
            filters = ["PBT", options.itb_name, "icache", options.dtb_name, "dcache", "BTB"]
            unfilters = [None, None, None, None, None, None]
            filter_pair = zip(filters, unfilters)
            for filter, unfilter in filter_pair:
                temp_new = []
                for child in self.children:
                    if filter in child.name:
                        temp_new.append(child)
                new_children += sortComponentList(temp_new)

            self.children = new_children

        for child in self.children:
            child.formXmlPower(new_component, doc, options)

    ## checkToFilter() is responsible for seeing the current component should
    ## be filtered from the power xml file
    def checkToFilter(self, options):
        ptype = self.params['type']
        for f in self.FILTER_TYPES:
            if ptype == f:
                self.power_xml_filter = True
                break

        if "TimingSimpleCPU" in self.params['type'] and (options.cpu_name not in self.name or "pim_system" in self.id):
            self.power_xml_filter = True

        if "replacement_policy" in self.id:
            self.power_xml_filter = True

        if "iocache" in self.name:
            self.power_xml_filter = True

    def checkToRenameReid(self, options):
        ptype = self.params['type']
        if options.cpu_name in self.name:
            self.re_name = self.name.replace(options.cpu_name, "core")
            self.re_id = self.id.replace(options.cpu_name, "core")

        if ptype == 'X86TLB':
            if self.name == options.itb_name:
                self.re_name = self.name.replace(options.itb_name, "itlb").replace(options.cpu_name, "core")
                self.re_id = self.id.replace(options.itb_name, "itlb").replace(options.cpu_name, "core")
            elif self.name == options.dtb_name:
                self.re_name = self.name.replace(options.dtb_name, "dtlb").replace(options.cpu_name, "core")
                self.re_id = self.id.replace(options.dtb_name, "dtlb").replace(options.cpu_name, "core")

        if ptype == "Cache" and ('icache' in self.name or 'dcache' in self.name):
            self.re_name = self.name.replace(options.l1_cache_cpu_name, "core")
            self.re_id = self.id.replace(options.l1_cache_cpu_name, "core")

##
## class Translator is used for finding and adding params and stats
## to the xml. Define a translator for each unique component in your system
## and make sure you add the assignment of the translator in setComponentType
##
class Translator:
    M5_PARAM = 0
    CONVERSION = 1
    DEFAULT_VALUE = 2
    M5_STAT = 3

    def __init__(self):
        self.power_params = {}
        self.power_params_order = []
        self.power_statistics = {}
        self.power_statistics_order = []
        None

    def addPowerParam(self, power_key, m5_key, default_value = "NaV"):
        if not self.power_params.has_key(power_key):
            self.power_params_order.append(power_key)
        self.power_params[power_key] = {Translator.M5_PARAM: m5_key,
            Translator.DEFAULT_VALUE: default_value}

    def addPowerStat(self, power_key, m5_key, default_value = "NaV"):
        if not self.power_statistics.has_key(power_key):
            self.power_statistics_order.append(power_key)
        self.power_statistics[power_key] = {Translator.M5_STAT: m5_key,
            Translator.DEFAULT_VALUE: default_value}

    ##
    ## translate_params (component) translates all params in component object
    ## from m5 parameters to the equivalent power model name
    ##
    def translate_params(self, component):
        for power_param_key in self.power_params_order:
            power_param = self.power_params[power_param_key]
            # Grab M5's version of the parameter needed and translate it to
            # power file name
            self.translate_param(component, power_param, power_param_key)

    ##
    ## translate_param(component, power_param) responsible for translating one
    ## M5 parameter to an m5 parameter and adding that parameter to the
    ## component translated_params variable
    ##
    def translate_param(self, component, power_param, key):
        # Find the translated value if it exists
        component.translated_params_order.append(key)
        try:
            component.translated_params[key] = \
                component.params[power_param[Translator.M5_PARAM]]
        except:
            # If it doesn't exist, use a default value
            component.translated_params[key] = \
                power_param[Translator.DEFAULT_VALUE]

    ##
    ## translate_statistics(component) translates all statistics in component
    ## object from m5 statistics to the equivalent power model statistics
    ##
    def translate_statistics(self, component):
        for power_stat_key in self.power_statistics_order:
            power_stat = self.power_statistics[power_stat_key]
            # Grab M5's version of the statistic needed and translate it to
            # power file stat
            self.translate_statistic(component, power_stat, power_stat_key)

    ##
    ## translate_statistc(component, power_param) responsible for translating
    ## one M5 statistic to a m5 statistic and adding that parameter to the
    ## component translated_statistics variable
    ##
    def translate_statistic(self, component, power_stat, key):
        # Find the translated value if it exists
        component.translated_statistics_order.append(key)
        try:
            component.translated_statistics[key] = component.statistics[power_stat[Translator.M5_STAT]]
        except:
            # If it doesn't exist, use a default value
            component.translated_statistics[key] = power_stat[Translator.DEFAULT_VALUE]

class System(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="number_of_cores", m5_key="number_of_cores", default_value="NaV")
        self.addPowerParam(power_key="number_of_L1Directories", m5_key="number_of_L2s", default_value="NaV")
        self.addPowerParam(power_key="number_of_L2Directories", m5_key="number_of_L2Directories", default_value="NaV") # shadow L4 with 0 latency back memory is our L2 directory
        self.addPowerParam(power_key="number_of_L2s", m5_key="number_of_L2s", default_value="NaV")
        self.addPowerParam(power_key="number_of_L3s", m5_key="number_of_L3s", default_value="NaV")
        self.addPowerParam(power_key="number_of_NoCs", m5_key="number_of_nocs", default_value="NaV")
        self.addPowerParam(power_key="homogeneous_cores", m5_key="homogeneous_cores", default_value="1") # TODO: set your value
        self.addPowerParam(power_key="homogeneous_L2s", m5_key="homogeneous_L2s", default_value="0") # TODO: set your value
        self.addPowerParam(power_key="homogeneous_L1Directories", m5_key="homogeneous_L1Directories", default_value="0") # TODO: set your value
        self.addPowerParam(power_key="homogeneous_L2Directories", m5_key="homogeneous_L2Directories", default_value="1") # TODO: set your value
        self.addPowerParam(power_key="homogeneous_L3s", m5_key="homogeneous_L3s", default_value="1") # TODO: set your value
        self.addPowerParam(power_key="homogeneous_ccs", m5_key="unknown", default_value="1") # TODO: set your value
        self.addPowerParam(power_key="homogeneous_NoCs", m5_key="homogeneous_nocs", default_value="0") # TODO: set your value
        self.addPowerParam(power_key="core_tech_node", m5_key="unknown", default_value="22") # TODO: set your value
        self.addPowerParam(power_key="target_core_clockrate", m5_key="unknown", default_value="2000") # TODO: set your value
        self.addPowerParam(power_key="temperature", m5_key="unknown", default_value="350") # TODO: set your value
        self.addPowerParam(power_key="number_cache_levels", m5_key="number_cache_levels", default_value="NaV")
        self.addPowerParam(power_key="interconnect_projection_type", m5_key="unknown", default_value="0") # TODO: set your value
        self.addPowerParam(power_key="device_type", m5_key="unknown", default_value="1") # TODO: set your value
        self.addPowerParam(power_key="longer_channel_device", m5_key="unknown", default_value="0") # TODO: set your value
        self.addPowerParam(power_key="power_gating", m5_key="unknown", default_value="0") # TODO: set your value
        self.addPowerParam(power_key="machine_bits", m5_key="unknown", default_value="64") # TODO: set your value
        self.addPowerParam(power_key="virtual_address_width", m5_key="unknown", default_value="64") # TODO: set your value
        self.addPowerParam(power_key="physical_address_width", m5_key="unknown", default_value="52") # TODO: set your value
        self.addPowerParam(power_key="virtual_memory_page_size", m5_key="unknown", default_value="4096") # TODO: set your value

        # statistics
        self.addPowerStat(power_key="total_cycles", m5_key="total_cycles", default_value="0")
        self.addPowerStat(power_key="idle_cycles", m5_key="unknown", default_value="0")
        self.addPowerStat(power_key="busy_cycles", m5_key="total_cycles", default_value="0")

class InOrderCore(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key = "clock_rate", m5_key = "clockrate", default_value = "NaV")
        self.addPowerParam(power_key = "vdd", m5_key = "unknown", default_value = "1")
        self.addPowerParam(power_key = "instruction_length", m5_key = "unknown", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "opcode_width", m5_key = "unknown", default_value = "7") # TODO: set your value
        self.addPowerParam(power_key = "x86", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "machine_type", m5_key = "unknown", default_value = "1") # 1 for inorder
        self.addPowerParam(power_key = "number_hardware_threads", m5_key = "numThreads", default_value = "1")
        self.addPowerParam(power_key = "fetch_width",  m5_key = "unknown", default_value = "2") # TODO: set your value
        self.addPowerParam(power_key = "number_instruction_fetch_ports", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "decode_width", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "issue_width", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "commit_width", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "fp_issue_width", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "prediction_width", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "pipelines_per_core", m5_key = "unknown", default_value = "1,1") # TODO: set your value
        self.addPowerParam(power_key = "pipeline_depth", m5_key = "unknown", default_value = "7,10") # TODO: set your value
        self.addPowerParam(power_key = "ALU_per_core", m5_key = "unknown", default_value = "2") # TODO: set your value
        self.addPowerParam(power_key = "MUL_per_core", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "FPU_per_core", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "instruction_buffer_size", m5_key = "unknown", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "decoded_stream_buffer_size", m5_key = "unknown", default_value = "16") # TODO: set your value
        self.addPowerParam(power_key = "instruction_window_scheme", m5_key = "unknown", default_value = "0") # TODO: set your value
        self.addPowerParam(power_key = "instruction_window_size", m5_key = "unknown", default_value = "16")
        self.addPowerParam(power_key = "fp_instruction_window_size", m5_key = "unknown", default_value = "16")
        self.addPowerParam(power_key = "ROB_size", m5_key = "unknown", default_value = "80")
        self.addPowerParam(power_key = "archi_Regs_IRF_size", m5_key = "unknown", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "archi_Regs_FRF_size", m5_key = "unknown", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "phy_Regs_IRF_size", m5_key = "unknown", default_value = "32")
        self.addPowerParam(power_key = "phy_Regs_FRF_size", m5_key = "unknown", default_value = "32")
        self.addPowerParam(power_key = "rename_scheme", m5_key = "unknown", default_value = "0")
        self.addPowerParam(power_key = "register_windows_size", m5_key = "unknown", default_value = "0")
        self.addPowerParam(power_key = "LSU_order", m5_key = "unknown", default_value = "inorder") # TODO: set your value
        self.addPowerParam(power_key = "store_buffer_size", m5_key = "unknown", default_value = "32")
        self.addPowerParam(power_key = "load_buffer_size", m5_key = "unknown", default_value = "0")
        self.addPowerParam(power_key = "memory_ports", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "RAS_size", m5_key="unknown", default_value="32")

        # statistics
        self.addPowerStat(power_key = "total_instructions", m5_key = "committedInsts", default_value = "0")
        self.addPowerStat(power_key = "int_instructions", m5_key = "num_int_insts", default_value = "0")
        self.addPowerStat(power_key = "fp_instructions", m5_key = "num_fp_insts", default_value = "0")
        self.addPowerStat(power_key = "branch_instructions", m5_key = "num_conditional_control_insts", default_value = "0")
        self.addPowerStat(power_key = "branch_mispredictions", m5_key = "unknown", default_value = "0") # TODO: set your value
        self.addPowerStat(power_key = "load_instructions", m5_key = "num_load_insts", default_value = "0")
        self.addPowerStat(power_key = "store_instructions", m5_key = "num_store_insts", default_value = "0")
        self.addPowerStat(power_key = "committed_instructions", m5_key = "committedInsts", default_value = "0")
        self.addPowerStat(power_key = "committed_int_instructions", m5_key = "num_int_insts", default_value = "0") 
        self.addPowerStat(power_key = "committed_fp_instructions", m5_key = "num_fp_insts", default_value = "0")
        self.addPowerStat(power_key = "pipeline_duty_cycle", m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerStat(power_key = "total_cycles", m5_key = "numCycles", default_value = "0")
        self.addPowerStat(power_key = "idle_cycles", m5_key = "num_idle_cycles", default_value = "0")
        self.addPowerStat(power_key = "busy_cycles", m5_key = "num_busy_cycles", default_value = "0")
        self.addPowerStat(power_key = "ROB_reads", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "ROB_writes", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "rename_reads", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "rename_writes", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "fp_rename_reads", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "fp_rename_writes", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "inst_window_reads", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "inst_window_writes", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "inst_window_wakeup_accesses", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "fp_inst_window_reads", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "fp_inst_window_writes", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "fp_inst_window_wakeup_access", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "int_regfile_reads", m5_key = "num_int_register_reads", default_value = "0")
        self.addPowerStat(power_key = "float_regfile_reads", m5_key = "num_fp_register_reads", default_value = "0")
        self.addPowerStat(power_key = "int_regfile_writes", m5_key = "num_int_register_writes", default_value = "0")
        self.addPowerStat(power_key = "float_regfile_writes", m5_key = "num_fp_register_writes", default_value = "0")
        self.addPowerStat(power_key = "function_calls", m5_key = "num_func_calls", default_value = "0")
        self.addPowerStat(power_key = "context_switches", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "ialu_accesses", m5_key = "num_int_alu_accesses", default_value = "0")
        self.addPowerStat(power_key = "fpu_accesses", m5_key = "num_fp_alu_accesses", default_value = "0")
        self.addPowerStat(power_key = "mul_accesses", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "cdb_alu_accesses", m5_key = "num_int_alu_accesses", default_value = "0")
        self.addPowerStat(power_key = "cdb_mul_accesses", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "cdb_fpu_accesses", m5_key = "num_fp_alu_accesses", default_value = "0")
        # Do not change below unless you know what you are doing!
        self.addPowerStat(power_key = "IFU_duty_cycle", m5_key = "unknown", default_value = "0.5")
        self.addPowerStat(power_key = "LSU_duty_cycle", m5_key = "unknown", default_value = "0.25")
        self.addPowerStat(power_key = "MemManU_I_duty_cycle", m5_key = "unknown", default_value = "0.5")
        self.addPowerStat(power_key = "MemManU_D_duty_cycle", m5_key = "unknown", default_value = "0.25")
        self.addPowerStat(power_key = "ALU_duty_cycle", m5_key = "unknown", default_value = "0.9")
        self.addPowerStat(power_key = "MUL_duty_cycle", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "FPU_duty_cycle", m5_key = "unknown", default_value = "0.6")
        self.addPowerStat(power_key = "ALU_cdb_duty_cycle", m5_key = "unknown", default_value = "0.9")
        self.addPowerStat(power_key = "MUL_cdb_duty_cycle", m5_key = "unknown", default_value = "0")
        self.addPowerStat(power_key = "FPU_cdb_duty_cycle", m5_key = "unknown", default_value = "0.6")

# TODO: checking
class OOOCore(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key = "clock_rate",
                           m5_key = "clockrate")
        self.addPowerParam(power_key = "opt_local",
                           m5_key = "unknown", default_value = '1')
        self.addPowerParam(power_key = "instruction_length",
                           m5_key = "unknown", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "opcode_width",
                           m5_key = "unknown", default_value = "7") # TODO: set your value
        self.addPowerParam(power_key = "x86",
                           m5_key = "unknown", default_value = "0") # TODO: set your value
        self.addPowerParam(power_key = "micro_opcode_width",
                           m5_key = "unknown", default_value = "8") # TODO: set your value
        self.addPowerParam(power_key = "machine_type",
                           m5_key = "unknown", default_value = "0") # TODO: set your value
        self.addPowerParam(power_key = "number_hardware_threads",
                           m5_key = "numThreads", default_value = "1")
        self.addPowerParam(power_key = "fetch_width",
                           m5_key = "fetchWidth", default_value = "4")
        self.addPowerParam(power_key = "number_instruction_fetch_ports",
                           m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "decode_width",
                           m5_key = "decodeWidth", default_value = "4")
        self.addPowerParam(power_key = "issue_width",
                           m5_key = "issueWidth", default_value = "4")
        self.addPowerParam(power_key = "peak_issue_width",
                           m5_key = "issueWidth", default_value = "6") # TODO: set your value
        self.addPowerParam(power_key = "commit_width",
                           m5_key = "commitWidth", default_value = "4")
        self.addPowerParam(power_key = "fp_issue_width",
                           m5_key = "fp_issue_width", default_value = "4") # TODO: set your value
        self.addPowerParam(power_key = "prediction_width",
                           m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "pipelines_per_core",
                           m5_key = "unknown", default_value = "1,1") # TODO: set your value
        self.addPowerParam(power_key = "pipeline_depth",
                           m5_key = "unknown", default_value = "7,7") # TODO: set your value
        self.addPowerParam(power_key = "ALU_per_core",
                           m5_key = "ALU_per_core", default_value = "4") # TODO: set your value
        self.addPowerParam(power_key = "MUL_per_core",
                           m5_key = "MUL_per_core", default_value = "2") # TODO: set your value
        self.addPowerParam(power_key = "FPU_per_core",
                           m5_key = "FPU_per_core", default_value = "2") # TODO: set your value
        self.addPowerParam(power_key = "instruction_buffer_size",
                           m5_key =" instruction_buffer_size", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "decoded_stream_buffer_size",
                           m5_key = "decoded_stream_buffer_size", default_value = "16") # TODO: set your value
        self.addPowerParam(power_key = "instruction_window_scheme",
                           m5_key = "unknown", default_value = "0") # TODO: set your value
        self.addPowerParam(power_key = "instruction_window_size",
                           m5_key = "numIQEntries", default_value = "20")
        self.addPowerParam(power_key = "fp_instruction_window_size",
                           m5_key = "numIQEntries", default_value = "15")
        self.addPowerParam(power_key = "ROB_size",
                           m5_key = "numROBEntries", default_value = "80")
        self.addPowerParam(power_key = "archi_Regs_IRF_size",
                           m5_key = "unknown", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "archi_Regs_FRF_size",
                           m5_key = "unknown", default_value = "32") # TODO: set your value
        self.addPowerParam(power_key = "phy_Regs_IRF_size",
                           m5_key = "numPhysIntRegs", default_value = "80")
        self.addPowerParam(power_key = "phy_Regs_FRF_size",
                           m5_key = "numPhysFloatRegs", default_value = "72")
        self.addPowerParam(power_key = "rename_scheme",
                           m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerParam(power_key = "register_windows_size",
                           m5_key = "unknown", default_value = "0") # TODO: set your value
        self.addPowerParam(power_key = "LSU_order",
                           m5_key = "unknown", default_value = "inorder") # TODO: set your value
        self.addPowerParam(power_key = "store_buffer_size",
                           m5_key = "SQEntries", default_value = "32")
        self.addPowerParam(power_key = "load_buffer_size",
                           m5_key = "LQEntries", default_value = "32")
        self.addPowerParam(power_key = "memory_ports",
                           m5_key = "memory_ports", default_value = "2") # TODO: set your value
        self.addPowerParam(power_key = "RAS_size",
                           m5_key = "RASSize", default_value = "32")

        # statistics
        self.addPowerStat(power_key = "total_instructions",
                          m5_key = "iq.iqInstsIssued", default_value = "0")
        self.addPowerStat(power_key = "int_instructions",
                          m5_key = "int_instructions", default_value = "NaV")
        self.addPowerStat(power_key = "fp_instructions",
                          m5_key = "fp_instructions", default_value = "NaV")
        self.addPowerStat(power_key = "branch_instructions",
                          m5_key = "BPredUnit.condPredicted", default_value = "NaV")
        self.addPowerStat(power_key = "branch_mispredictions",
                          m5_key = "BPredUnit.condIncorrect", default_value = "NaV")
        self.addPowerStat(power_key = "load_instructions",
                          m5_key = "load_instructions", default_value = "NaV")
        self.addPowerStat(power_key = "store_instructions",
                          m5_key = "store_instructions", default_value = "NaV")
        self.addPowerStat(power_key = "committed_instructions",
                          m5_key = "commit.count", default_value = "NaV")
        self.addPowerStat(power_key = "committed_int_instructions",
                          m5_key = "commit.int_insts", default_value = "NaV")
        self.addPowerStat(power_key = "committed_fp_instructions",
                          m5_key = "commit.fp_insts", default_value = "NaV")
        self.addPowerStat(power_key = "pipeline_duty_cycle",
                          m5_key = "unknown", default_value = "1") # TODO: set your value
        self.addPowerStat(power_key = "total_cycles",
                          m5_key = "numCycles", default_value = "NaV")
        self.addPowerStat(power_key = "idle_cycles",
                          m5_key = "idleCycles", default_value = "NaV")
        self.addPowerStat(power_key = "busy_cycles",
                          m5_key = "num_busy_cycles", default_value = "NaV")
        self.addPowerStat(power_key = "ROB_reads",
                          m5_key = "rob_reads", default_value = "34794891") # FIXME: rerun the experiments to include this statistic
        self.addPowerStat(power_key = "ROB_writes",
                          m5_key = "rob_writes", default_value = "34794891") # FIXME: rerun the experiments to include this statistic
        self.addPowerStat(power_key = "rename_reads",
                          m5_key = "rename.int_rename_lookups", default_value = "0")
        self.addPowerStat(power_key = "rename_writes",
                          m5_key = "unknown", default_value = "0") # TODO: FIXME
        self.addPowerStat(power_key = "fp_rename_reads",
                          m5_key = "rename.fp_rename_lookups", default_value = "0")
        self.addPowerStat(power_key = "fp_rename_writes",
                          m5_key = "unknown", default_value = "0") # TODO: FIXME
        self.addPowerStat(power_key = "inst_window_reads",
                          m5_key = "iq.int_inst_queue_reads", default_value = "NaV")
        self.addPowerStat(power_key = "inst_window_writes",
                          m5_key = "iq.int_inst_queue_writes", default_value = "NaV")
        self.addPowerStat(power_key = "inst_window_wakeup_accesses",
                          m5_key = "iq.int_inst_queue_wakeup_accesses", default_value = "NaV")
        self.addPowerStat(power_key = "fp_inst_window_reads",
                          m5_key = "iq.fp_inst_queue_reads", default_value = "0")
        self.addPowerStat(power_key = "fp_inst_window_writes",
                          m5_key = "iq.fp_inst_queue_writes", default_value = "NaV")
        self.addPowerStat(power_key = "fp_inst_window_wakeup_accesses",
                          m5_key = "iq.fp_inst_queue_wakeup_accesses", default_value = "NaV")
        self.addPowerStat(power_key = "int_regfile_reads",
                          m5_key = "int_regfile_reads", default_value = "0")
        self.addPowerStat(power_key = "float_regfile_reads",
                          m5_key = "fp_regfile_reads", default_value = "0")
        self.addPowerStat(power_key = "int_regfile_writes",
                          m5_key =" int_regfile_writes", default_value = "0")
        self.addPowerStat(power_key = "float_regfile_writes",
                          m5_key = "fp_regfile_writes", default_value = "0")
        self.addPowerStat(power_key = "function_calls",
                          m5_key = "commit.function_calls", default_value = "NaV")
        self.addPowerStat(power_key = "context_switches",
                          m5_key = "kern.swap_context", default_value = "0")
        self.addPowerStat(power_key = "ialu_accesses",
                          m5_key = "iq.int_alu_accesses", default_value = "NaV")
        self.addPowerStat(power_key = "fpu_accesses",
                          m5_key = "iq.fp_alu_accesses", default_value = "NaV")
        self.addPowerStat(power_key = "mul_accesses",
                          m5_key = "iq.FU_type_0::IntMult", default_value = "NaV")
        self.addPowerStat(power_key = "cdb_alu_accesses",
                          m5_key = "iq.int_alu_accesses", default_value = "NaV")
        self.addPowerStat(power_key = "cdb_mul_accesses",
                          m5_key = "iq.FU_type_0::IntMult", default_value = "NaV")
        self.addPowerStat(power_key = "cdb_fpu_accesses",
                          m5_key = "iq.fp_alu_accesses", default_value = "NaV")
        # Do not change below unless you know what you are doing!
        self.addPowerStat(power_key = "IFU_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "LSU_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "MemManU_I_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "MemManU_D_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "ALU_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "MUL_duty_cycle",
                          m5_key = "unknown", default_value = "0.3")
        self.addPowerStat(power_key = "FPU_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "ALU_cdb_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "MUL_cdb_duty_cycle",
                          m5_key = "unknown", default_value = "0.3")
        self.addPowerStat(power_key = "FPU_cdb_duty_cycle",
                          m5_key = "unknown", default_value = "1")
        self.addPowerStat(power_key = "number_of_BPT",
                          m5_key = "unknown", default_value = "2")

class Predictor(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="local_predictor_size", m5_key="unknown", default_value="10,3")
        self.addPowerParam(power_key="local_predictor_entries", m5_key="unkown", default_value="1024")
        self.addPowerParam(power_key="global_predictor_entries", m5_key="unknown", default_value="4096")
        self.addPowerParam(power_key="global_predictor_bits", m5_key="unknown", default_value="2")
        self.addPowerParam(power_key="chooser_predictor_entries", m5_key="unknown", default_value="4096")
        self.addPowerParam(power_key="chooser_predictor_bits", m5_key="unknown", default_value="2")

class BTB(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key = "BTB_config", m5_key = "unknown", default_value = "6144,4,2,1,1,3")

        # statistics
        self.addPowerStat(power_key = "read_accesses", m5_key = "lookup", default_value = "0")
        self.addPowerStat(power_key = "write_accesses", m5_key = "unknown", default_value = "0")

class X86TLB(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key = "number_entries",
                           m5_key = "size")

        # statistics
        self.addPowerStat(power_key = "total_accesses",
                          m5_key = "total_accesses", default_value = "0")
        self.addPowerStat(power_key = "total_misses",
                          m5_key = "total_misses", default_value = "0")
        self.addPowerStat(power_key = "conflicts",
                          m5_key = "unknown", default_value = "0")

class TLB(X86TLB):
    pass
class ITLB(TLB):
    pass
class DTLB(TLB):
    pass

class InstructionCache(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key = "icache_config",
                           m5_key = "icache_config")
        self.addPowerParam(power_key = "buffer_sizes",
                           m5_key = "buffer_sizes")

        # statistics
        self.addPowerStat(power_key = "read_accesses",
                          m5_key = "ReadReq_accesses::total", default_value = "0")
        self.addPowerStat(power_key="read_misses",
                          m5_key = "ReadReq_misses::total", default_value = "0")
        self.addPowerStat(power_key = "conflicts",
                          m5_key = "replacements", default_value = "0")

class DataCache(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key = "dcache_config",
                           m5_key = "dcache_config")
        self.addPowerParam(power_key = "buffer_sizes",
                           m5_key = "buffer_sizes")

        # statistics
        self.addPowerStat(power_key = "read_accesses",
                          m5_key = "ReadReq_accesses::total", default_value = "0")
        self.addPowerStat(power_key = "write_accesses",
                          m5_key = "WriteReq_accesses::total", default_value = "0")
        self.addPowerStat(power_key = "read_misses",
                          m5_key = "ReadReq_misses::total", default_value = "0")
        self.addPowerStat(power_key = "write_misses",
                          m5_key = "WriteReq_misses::total", default_value = "0")
        self.addPowerStat(power_key = "conflicts",
                          m5_key = "replacements", default_value = "0")

class SharedCacheL2(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key = "L2_config",
                           m5_key = "L2_config")
        self.addPowerParam(power_key = "buffer_sizes",
                           m5_key = "buffer_sizes")
        self.addPowerParam(power_key = "clockrate",
                           m5_key = "clockrate", default_value = "NaV")
        self.addPowerParam(power_key = "ports",
                           m5_key = "unknown", default_value = "1,1,1") # TODO: specify your value
        self.addPowerParam(power_key = "device_type",
                           m5_key = "unknown", default_value = "0") # TODO: specify your value

        # statistics
        self.addPowerStat(power_key = "read_accesses",
                          m5_key = "ReadReq_accesses::total", default_value = "0")
        self.addPowerStat(power_key = "write_accesses",
                          m5_key = "ReadExReq_accesses::total", default_value = "0")
        self.addPowerStat(power_key = "read_misses",
                          m5_key = "ReadReq_misses::total", default_value = "0")
        self.addPowerStat(power_key = "write_misses",
                          m5_key = "ReadExReq_misses::total", default_value = "0")
        self.addPowerStat(power_key = "conflicts",
                          m5_key = "replacements", default_value = "0")
        self.addPowerStat(power_key = "duty_cycle",
                          m5_key = "unknown", default_value = "1.0")

class L1Directory(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="Directory_type", m5_key="unknown", default_value="0") # TODO: specify your value
        self.addPowerParam(power_key="Dir_config", m5_key="Dir_config", default_value="NaV")
        self.addPowerParam(power_key="buffer_sizes", m5_key="unknown", default_value="8,8,8,8") # TODO: specify your value
        self.addPowerParam(power_key="clockrate", m5_key="clockrate", default_value="NaV")
        self.addPowerParam(power_key="ports", m5_key="unknown", default_value="1,1,1") # TODO: specify your value
        self.addPowerParam(power_key="device_type", m5_key="unknown", default_value="0") # TODO: specify your value

        # statistics
        self.addPowerStat(power_key="read_accesses", m5_key="read_accesses", default_value="NaV")
        self.addPowerStat(power_key="write_accesses", m5_key="write_accesses", default_value="NaV")
        self.addPowerStat(power_key="read_misses", m5_key="read_misses", default_value="0") # FIXME: Add this stat to M5. My model does not treat directory as a cache
        self.addPowerStat(power_key="write_misses", m5_key="write_misses", default_value="0") # FIXME: Add this stat to M5. My model does not treat directory as a cache
        self.addPowerStat(power_key="conflicts", m5_key="replacements", default_value="0") # FIXME: Add this stat to M5. My model does not treat directory as a cache

class L2Directory(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="Directory_type", m5_key="unknown", default_value="1") # TODO: specify your value
        self.addPowerParam(power_key="Dir_config", m5_key="Dir_config", default_value="NaV")
        self.addPowerParam(power_key="buffer_sizes", m5_key="unknown", default_value="8,8,8,8") # TODO: specify your value
        self.addPowerParam(power_key="clockrate", m5_key="clockrate", default_value="NaV")
        self.addPowerParam(power_key="ports", m5_key="unknown", default_value="1,1,1") # TODO: specify your value
        self.addPowerParam(power_key="device_type", m5_key="unknown", default_value="0") # TODO: specify your value

        # statistics
        self.addPowerStat(power_key="read_accesses", m5_key="read_accesses", default_value="NaV")
        self.addPowerStat(power_key="write_accesses", m5_key="write_accesses", default_value="NaV")
        self.addPowerStat(power_key="read_misses", m5_key="read_misses", default_value="0") # FIXME: Add this stat to M5. My model does not treat directory as a cache
        self.addPowerStat(power_key="write_misses", m5_key="write_misses", default_value="0") # FIXME: Add this stat to M5. My model does not treat directory as a cache
        self.addPowerStat(power_key="conflicts", m5_key="replacements", default_value="0") # FIXME: Add this stat to M5. My model does not treat directory as a cache

class Bus(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="clockrate", m5_key="clockrate", default_value="0")
        self.addPowerParam(power_key="type", m5_key="unknown", default_value="0") # 0 for BUS
        self.addPowerParam(power_key="horizontal_nodes", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="vertical_nodes", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="has_global_link", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="link_throughput", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="link_latency", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="input_ports", m5_key="input_ports", default_value="0")
        self.addPowerParam(power_key="output_ports", m5_key="output_ports", default_value="0")
        self.addPowerParam(power_key="virtual_channel_per_port", m5_key="unknown", default_value="2") # FIXME: what is this?
        self.addPowerParam(power_key="input_buffer_entries_per_vc", m5_key="unknown", default_value="128") # FIXME
        self.addPowerParam(power_key="flit_bits", m5_key="unknown", default_value="64") # FIXME: what is this?
        self.addPowerParam(power_key="chip_coverage", m5_key="unknown", default_value="1") # really should be a function of the number of nocs
        self.addPowerParam(power_key="link_routing_over_percentage", m5_key="unknown", default_value="0.5")

        # statistics
        self.addPowerStat(power_key="total_accesses", m5_key="pkt_count::total", default_value="0")
        self.addPowerStat(power_key="duty_cycle", m5_key="unknown", default_value="1")

class MC(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="type", m5_key="unknown", default_value="0") # TODO: set your value
        self.addPowerParam(power_key="mc_clock", m5_key="unknown", default_value="400") # TODO: set your value
        self.addPowerParam(power_key="peak_transfer_rate", m5_key="unknown", default_value="1600") # TODO: set your value
        self.addPowerParam(power_key="block_size", m5_key="unknown", default_value="64") # TODO: set your value
        self.addPowerParam(power_key="number_mcs", m5_key="unknown", default_value="2") # TODO: set this value
        self.addPowerParam(power_key="memory_channels_per_mc", m5_key="unknown", default_value="1") # TODO: set your value
        self.addPowerParam(power_key="number_ranks", m5_key="unknown", default_value="2") # TODO: set your value
        self.addPowerParam(power_key="req_window_size_per_channel", m5_key="unknown", default_value="32") # TODO: set your value
        self.addPowerParam(power_key="IO_buffer_size_per_channel", m5_key="unknown", default_value="32") # TODO: set your value
        self.addPowerParam(power_key="databus_width", m5_key="unknown", default_value="128") # TODO: set your value
        self.addPowerParam(power_key="addressbus_width", m5_key="unknown", default_value="51") # TODO: set your value
        self.addPowerParam(power_key="withPHY", m5_key="unknown", default_value="1") # TODO: set your value

        # statistcs
        self.addPowerStat(power_key="memory_accesses", m5_key="mem_accesses", default_value="0")
        self.addPowerStat(power_key="memory_reads", m5_key="mem_reads", default_value="0")
        self.addPowerStat(power_key="memory_writes", m5_key="mem_writes", default_value="0")

class NIU(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="type", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="clockrate", m5_key="unknown", default_value="350")
        self.addPowerParam(power_key="vdd", m5_key="unknown", default_value="0")
        self.addPowerParam(power_key="power_gating_vcc", m5_key="unknown", default_value="-1")
        self.addPowerParam(power_key="number_units", m5_key="unknown", default_value="0")

        # statistcs
        self.addPowerStat(power_key="duty_cycle", m5_key="unknown", default_value="1.0")
        self.addPowerStat(power_key="total_load_perc", m5_key="unknown", default_value="0.7")

class PCIe(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="type", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="withPHY", m5_key="unknown", default_value="0")
        self.addPowerParam(power_key="clockrate", m5_key="unknown", default_value="350")
        self.addPowerParam(power_key="vdd", m5_key="unknown", default_value="0")
        self.addPowerParam(power_key="power_gating_vcc", m5_key="unknown", default_value="-1")
        self.addPowerParam(power_key="number_units", m5_key="unknown", default_value="0")
        self.addPowerParam(power_key="num_channels", m5_key="unknown", default_value="8")

        # statistcs
        self.addPowerStat(power_key="duty_cycle", m5_key="unknown", default_value="1.0")
        self.addPowerStat(power_key="total_load_perc", m5_key="unknown", default_value="0.7")

class Flashc(Translator):
    def __init__(self):
        Translator.__init__(self)

        # params
        self.addPowerParam(power_key="number_flashcs", m5_key="unknown", default_value="0")
        self.addPowerParam(power_key="type", m5_key="unknown", default_value="1")
        self.addPowerParam(power_key="withPHY", m5_key="unknown", default_value="0")
        self.addPowerParam(power_key="peak_transfer_rate", m5_key="unknown", default_value="200")
        self.addPowerParam(power_key="vdd", m5_key="unknown", default_value="0")
        self.addPowerParam(power_key="power_gating_vcc", m5_key="unknown", default_value="-1")

        # statistcs
        self.addPowerStat(power_key="duty_cycle", m5_key="unknown", default_value="1.0")
        self.addPowerStat(power_key="total_load_perc", m5_key="unknown", default_value="0.7")


##
## setComponentType takes as input a component object, and assigns
## the translator field to the right type of Translator object. Translator
## objects are responsible for grabbing the right stats and naming them
## correctly
##
def setComponentType(component, options):
    for name in options.interconn_names.split('#'):
        if name in component.name:
            if component.params['type'] == "CoherentXBar":
                component.translator = Bus()
            return

    if options.cpu_name in component.name:
        if component.params['type'] == "TimingSimpleCPU":
            component.translator = InOrderCore()
        if component.params['type'] == "DerivO3CPU":
            component.translator = OOOCore()
    elif options.itb_name in component.name:
        component.translator = ITLB()
    elif options.dtb_name in component.name:
        component.translator = DTLB()
    elif "icache" in component.name:
        if component.params['type'] == "Cache":
            component.translator = InstructionCache()
    elif "dcache" in component.name:
        if component.params['type'] == "Cache":
            component.translator = DataCache()
    elif "Directory" in component.name:
        if "L1" in component.name:
            component.translator = L1Directory()
        elif "L2" in component.name:
            component.translator = L2Directory()
    elif "l2" in component.name:
        if component.params['type'] == "Cache":
            component.translator = SharedCacheL2()
    elif options.system_name == component.name:
        component.translator = System()
    elif "PBT" in component.name:
        component.translator = Predictor()
    elif "BTB" in component.name:
        component.translator = BTB()
    elif "mc" in component.name:
        component.translator = MC()
    elif "niu" in component.name:
        component.translator = NIU()
    elif "pcie" in component.name:
        component.translator = PCIe()
    elif "flashc" in component.name:
        component.translator = Flashc()
    else:
        return

# Assume that ticks are picoseconds and converting to MHz
def clkComponentToClkRate(clk_comp):
    return int(1 / (float(clk_comp.params['clock']) * 1e-6))

##
## Function - genId
## genId() will take a list of system components and concat them to make a
## specific component of stat identifier.
##
def genId(id_list):
    res=''
    for id in id_list:
        res += '%s.' % id
    res = res.rstrip('.')
    return res

def tryGrabComponentStat(component, stat, conversion = "int"):
    try:
        value = str(component.statistics[stat])
    except:
        value = "0"

    if conversion == "int":
        value = int(value)
    else:
        panic("unable to perform conversion")

    return value

##
## Function - generateCalcStats
## generateCalcStats() is a function used to:
## * Add statistics that are composed from several other statistics and params
##   that can be seen by the translator objects in the next phase
## * Rename newly generated components to meet the McPat specifications
## * Move children components to a new parent component to meet the right xml
##   form
##
## This code is the least generic and will likely needed to be changed by new
## users. If there is a bug, it probably in this function ... X_X
##
def generateCalcStats(cht, sht, options):
    fastest_clock = None

    num_cores = 0
    num_l1s = 0
    num_l2s = 0
    num_l3s = 0
    num_nocs = 0
    num_cache_levels = 0

    homogeneous_L1s = "0"
    homogeneous_L2s = "0"
    homogeneous_L3s = "0"
    homogeneous_nocs = "0"
    homogeneous_L1Directories = "0"
    homogeneous_L2Directories = "0"

    new_components_to_add = []

    for c_key in cht:
        component = cht[c_key]

        if "pim_system" in c_key:
            continue

        if not component.params.has_key('type'):
            continue

        ptype = component.params['type']

        if ptype == 'X86TLB':
            rdAccesses = tryGrabComponentStat(component, "rdAccesses")
            rdMisses = tryGrabComponentStat(component, "rdMisses")
            wrAccesses = tryGrabComponentStat(component, "wrAccesses")
            wrMisses = tryGrabComponentStat(component, "wrMisses")
            component.statistics["total_accesses"] = str(rdAccesses +
                                                         wrAccesses)
            component.statistics["total_misses"] = str(rdMisses + wrMisses)

        if ptype == "CoherentXBar":
            for name in options.interconn_names.split('#'):
                if name in component.name:
                    component.re_name = component.name.replace(name, "noc%d" %
                                                                     num_nocs)
                    component.re_id = component.id.replace(name, "NoC%d" %
                                                                 num_nocs)
                    num_nocs += 1
                    break

            clk_component = cht[component.params['clk_domain']]
            clock_rate = clkComponentToClkRate(clk_component)
            input_ports = len(component.params['slave'].split())
            output_ports = len(component.params['master'].split())
            component.params["clockrate"] = str(clock_rate)
            component.params["input_ports"] = str(input_ports)
            component.params["output_ports"] = str(output_ports)

            ports = component.params['slave'].split()
            ports.extend(component.params['master'].split())
            for port in ports:
                # Remove port name to find component this bus is attached to
                temp = port.split('.')
                comp_id = genId(temp[0 : len(temp) - 1])
                if not cht.has_key(comp_id):
                    panic("unable to find component %s" % comp_id)
                # Add bus width to component to make it easier for power model
                cht[comp_id].params[component.name + ".width"] = \
                    component.params['width']

        if (ptype == "TimingSimpleCPU" or ptype == "DerivO3CPU") and options.cpu_name in component.name and "pim_system" not in component.id:
            clk_component = cht[component.params['clk_domain']]
            clock_rate = clkComponentToClkRate(clk_component)
            component.params["clockrate"] = str(clock_rate)

            clock = int(clk_component.params['clock'])
            if fastest_clock == None or fastest_clock > clock:
                fastest_clock = clock

            num_cores += 1

            if ptype == "TimingSimpleCPU":
                # Add BTB unit
                child_id = component.id + ".BTB"
                new_params = {}
                new_params["BTB_config"] = "%s,4,2,1,1,3" % "8192" # FIXME: not enough
                new_comp = Component(child_id, new_params)
                new_comp.re_name = new_comp.name.replace(options.cpu_name, "core")
                new_comp.re_id = new_comp.id.replace(options.cpu_name, "core")
                new_comp.statistics["lookup"] = component.statistics["Branches"]
                new_components_to_add.append((child_id, new_comp))
                component.children.append(new_comp)

                # Add branch predictor child
                child_id = component.id + ".predictor"
                new_params = {}
                new_comp = Component(child_id, new_params, "PBT")
                new_comp.re_name = new_comp.name.replace(options.cpu_name, "core")
                new_comp.re_id = new_comp.id.replace(options.cpu_name, "core")
                new_components_to_add.append((child_id, new_comp))
                component.children.append(new_comp)
            else:
                # Add BTB unit
                child_id = component.id + ".BTB"
                new_params = {}
                new_params["BTB_config"] = "%s,4,2,1,1,3" % (component.params["BTBEntries"]) # FIXME: not enough
                new_comp = Component(child_id, new_params)
                new_comp.re_name = new_comp.name.replace(options.cpu_name, "core")
                new_comp.re_id = new_comp.id.replace(options.cpu_name, "core")
                new_comp.statistics["lookup"] = component.statistics["Branches"]
                new_comp.statistics["write_accesses"] = str(int(component.statistics["BPredUnit.lookups"]) - int(component.statistics["BPredUnit.BTBHits"]))
                new_components_to_add.append((child_id, new_comp))
                component.children.append(new_comp)

                # Add branch predictor child
                child_id = component.id + ".predictor"
                new_params = {}
                new_params["local_predictor_size"] = "10,3" # FIXME: Where to grab this information
                new_params["local_predictor_entries"] = component.params["localPredictorSize"]
                new_params["global_predictor_entries"] = component.params["globalPredictorSize"] # FIXME
                new_params["global_predictor_bits"] = "2" # FIXME
                new_params["chooser_predictor_entries"] = component.params["choicePredictorSize"] # FIXME
                new_params["chooser_predictor_bits"] = "2" #FIXME
                new_params["prediction_width"] = "1"
                new_comp = Component(child_id, new_params, "PBT")
                new_comp.re_name = new_comp.name.replace(options.cpu_name, "core")
                new_comp.re_id = new_comp.id.replace(options.cpu_name, "core")
                new_components_to_add.append((child_id, new_comp))
                component.children.append(new_comp)

                # Set params & stats
                issue_width = int(component.params["issueWidth"])
                component.params["ALU_per_core"] = str(int(math.ceil(issue_width)))
                component.params["fp_issue_width"] = str(int(math.ceil(2 / 3.0 * issue_width)))
                component.params["MUL_per_core"] = str(int(math.ceil(1 / 3.0 * issue_width)))
                component.params["FPU_per_core"] = str(int(math.ceil(2 / 3.0 * issue_width)))
                component.params["instruction_buffer_size"] = "16" # str(int(math.ceil(16/3.0*issue_width)))
                component.params["decoded_stream_buffer_size"] = str(int(math.ceil(8 / 3.0 * issue_width)))
                component.params["memory_ports"] = str(int(math.ceil(1 / 3.0 * issue_width)))

                component.statistics["fp_instructions"] = str(int(component.statistics["iq.FU_type_0::FloatAdd"]) + \
                                                              int(component.statistics["iq.FU_type_0::FloatCmp"]) + \
                                                              int(component.statistics["iq.FU_type_0::FloatCvt"]) + \
                                                              int(component.statistics["iq.FU_type_0::FloatMult"]) + \
                                                              int(component.statistics["iq.FU_type_0::FloatDiv"]) + \
                                                              int(component.statistics["iq.FU_type_0::FloatSqrt"]))
                component.statistics["int_instructions"] = str(int(component.statistics["iq.FU_type_0::No_OpClass"]) + \
                                                               int(component.statistics["iq.FU_type_0::IntAlu"]) + \
                                                               int(component.statistics["iq.FU_type_0::IntMult"]) + \
                                                               int(component.statistics["iq.FU_type_0::IntDiv"]) + \
                                                               int(component.statistics["iq.FU_type_0::IprAccess"]))
                try:
                    component.statistics["committed_int_instructions"] = str(int(float(component.statistics["int_instructions"]) \
                                                                / (float(component.statistics["int_instructions"])+float(component.statistics["fp_instructions"])) \
                                                                * int(component.statistics["commit:count"])))
                    component.statistics["committed_fp_instructions"] = str(int(float(component.statistics["fp_instructions"]) \
                                                                / (float(component.statistics["int_instructions"])+float(component.statistics["fp_instructions"])) \
                                                                * int(component.statistics["commit.count"])))
                except:
                    component.statistics["committed_int_instructions"] = "0"
                    component.statistics["committed_fp_instructions"] = "0"
                component.statistics["load_instructions"] = str(int(component.statistics["iq.FU_type_0::MemRead"]) + \
                                                                int(component.statistics["iq.FU_type_0::InstPrefetch"]))
                component.statistics["store_instructions"] = str(int(component.statistics["iq.FU_type_0::MemWrite"]))
                component.statistics["num_busy_cycles"] = str(int(component.statistics["numCycles"]) -
                                                          tryGrabComponentStat(component, "idleCycles", conversion = "int"))

        if ptype == "Cache":
            num_mshrs = int(component.params["mshrs"])
            num_write_buffers = int(component.params["write_buffers"])
            if num_mshrs < 4:
                num_mshrs = 4
            component.params["buffer_sizes"] = "%d,%d,%d,%d" % (num_mshrs, num_mshrs, num_mshrs, num_write_buffers)

            size = component.params["size"]
            tag_lat = component.params["tag_latency"]
            response_lat = component.params["response_latency"]

            tags_component = cht[component.params["tags"]]
            block_size = tags_component.params["block_size"]
            assoc = tags_component.params["assoc"]

            try:
                banked = component.params["banked"]
                num_banks = component.params["numBanks"]
            except:
                num_banks = "1"

            if "icache" in component.name:
                cache_config_type = "icache_config"
            elif "dcache" in component.name:
                cache_config_type = "dcache_config"
            elif "l2" in component.name:
                cache_config_type = "L2_config"

            component.params[cache_config_type] = "%s,%s,%s,%s,%s,%s,%s,%s" % (size, block_size, assoc, num_banks, response_lat, tag_lat, block_size, "1")

            if "l2" in component.name:
                # Set clockrate
                clk_component = cht[component.params['clk_domain']]
                clock_rate = clkComponentToClkRate(clk_component)
                component.params["clockrate"] = str(clock_rate)

                # Add L2 directory
                component.re_name = component.name.replace("l", "L")
                component.re_id = component.id.replace("l", "L")

                match = re.match(r".*(l[0-9])([0-9]*)", component.name)
                cache_qualifier = match.group(1).upper()
                new_cache_qualifier = cache_qualifier.replace("L2", "L1")
                cache_number = '0'

                component.re_name = component.re_name + cache_number
                component.re_id = component.re_id + cache_number

                child_id = "%s.%sDirectory%s" % (options.system_name, new_cache_qualifier, cache_number)
                core_component = "%s.%s0" % (options.system_name, options.cpu_name)
                if not cht.has_key(core_component):
                    core_component = "%s.%s00" % (options.system_name, options.cpu_name)
                    if not cht.has_key(core_component):
                        core_component ="%s.%s" % (options.system_name, options.cpu_name)

                new_params = {}
                new_params["clockrate"] = str(clock_rate)
                dir_size = str(int(float(size) / float(block_size)))
                dir_block_size = "16" # block_size of 64 causes problems for L1Directory so I hardcoded 16
                dir_number_banks = "1" # bank_size not equal to 1 causes problems for the L1DIrectory
                new_params["Dir_config"] = "%s,%s,%s,%s,%s,%s" % (dir_size, dir_block_size, assoc, dir_number_banks, response_lat, tag_lat)
                new_comp = Component(child_id, new_params)
                new_comp.statistics["read_accesses"] = str(int(component.statistics["ReadCleanReq_accesses::total"]) +
                                                           int(component.statistics["ReadReq_accesses::total"]) +
                                                           int(component.statistics["ReadSharedReq_accesses::total"]))
                new_comp.statistics["write_accesses"] = str(int(component.statistics["ReadExReq_accesses::total"]))
                new_comp.statistics["read_misses"] = str(int(component.statistics["ReadCleanReq_misses::total"]) +
                                                         int(component.statistics["ReadReq_misses::total"]) +
                                                         int(component.statistics["ReadSharedReq_misses::total"]))
                new_comp.statistics["write_misses"] = str(int(component.statistics["ReadExReq_misses::total"]))
                new_comp.statistics["replacements"] = str(int(component.statistics["replacements"]))

                new_components_to_add.append((child_id, new_comp))
                cht[options.system_name].children.append(new_comp)

        if ptype == "Cache" and ("dcache" in component.name or "icache" in component.name):
            if num_cache_levels < 1:
                num_cache_levels = 1
            num_l1s += 1
            if num_l1s == 1:
                homogeneous_L1s = "1"
            elif num_l1s > 1:
                homogeneous_L1s = "0"

        if ptype == "Cache" and "l2" in component.name:
            if num_cache_levels < 2:
                num_cache_levels = 2
            num_l2s += 1
            if num_l2s == 1:
                homogeneous_L1Directories = "1"
                homogeneous_L2s = "1"
            elif num_l2s > 1:
                homogeneous_L1Directories = "0"
                homogeneous_L2s = "0"

    # Set mc
    mc_id = "%s.mc" % options.system_name
    mc_comp = Component(mc_id, {})
    new_components_to_add.append((mc_id, mc_comp))
    cht[options.system_name].children.append(mc_comp)
    mc_comp.statistics["mem_reads"] = "0"
    mc_comp.statistics["mem_writes"] = "0"
    for c_key in cht:
        component = cht[c_key]
        if component.params['type'] == "DRAMCtrl" and "mem_ctrls" in component.name:
            if not component.statistics.has_key('num_reads::total'):
                component.statistics["num_reads::total"] = 0
            if not component.statistics.has_key('num_writes::total'):
                component.statistics["num_writes::total"] = 0
            mc_comp.statistics["mem_reads"] = str(int(mc_comp.statistics["mem_reads"]) + int(component.statistics["num_reads::total"]))
            mc_comp.statistics["mem_writes"] = str(int(mc_comp.statistics["mem_writes"]) + int(component.statistics["num_writes::total"]))
    mc_comp.statistics["mem_accesses"] = str(int(mc_comp.statistics["mem_reads"]) + int(mc_comp.statistics["mem_writes"]))

    # Set NIU
    niu_id = "%s.niu" % options.system_name
    niu_comp = Component(niu_id, {})
    new_components_to_add.append((niu_id, niu_comp))
    cht[options.system_name].children.append(niu_comp)

    # Set PCIe
    pcie_id = "%s.pcie" % options.system_name
    pcie_comp = Component(pcie_id, {})
    new_components_to_add.append((pcie_id, pcie_comp))
    cht[options.system_name].children.append(pcie_comp)

    # Set flashc
    flashc_id = "%s.flashc" % options.system_name
    flashc_comp = Component(flashc_id, {})
    new_components_to_add.append((flashc_id, flashc_comp))
    cht[options.system_name].children.append(flashc_comp)

    # Add new components
    for key_id, new_comp in new_components_to_add:
        cht[key_id] = new_comp

    # system
    cht[options.system_name].params["number_of_cores"] = str(num_cores)
    cht[options.system_name].params["number_of_L1Directories"] = str(num_l2s)
    cht[options.system_name].params["number_of_L2s"] = str(num_l2s)
    cht[options.system_name].params["number_of_L2Directories"] = str(num_l3s)
    cht[options.system_name].params["number_of_L3s"] = str(num_l3s)
    cht[options.system_name].params["number_of_nocs"] = str(num_nocs)
    cht[options.system_name].params["number_cache_levels"] = str(num_cache_levels)
    cht[options.system_name].params["homogeneous_L2s"] = homogeneous_L2s
    cht[options.system_name].params["homogeneous_L3s"] = homogeneous_L3s
    cht[options.system_name].params["homogeneous_L1Directories"] = homogeneous_L1Directories
    cht[options.system_name].params["homogeneous_L2Directories"] = homogeneous_L2Directories
    cht[options.system_name].params["homogeneous_nocs"] = homogeneous_nocs
    cht[options.system_name].statistics["total_cycles"] = str(int(sht["%s.sim_ticks" % options.system_name]) / int(fastest_clock))

##
## Function - createComponentTree
## createComponentTree() does the following:
## * Creates a tree of components by looking at the config.ini parameter
##   children for each component
## * Stats are added to each component as appropriate
## * Missing stats are generated
## * Component translator is set
## * The translator grabs all relevant stats and params for the component and
##   renames from M5 names to McPat names
##
def createComponentTree(cht, sht, options):
    # Create a component tree by looking at the children parameter
    for key in cht:
        component = cht[key]
        if component.params.has_key('children'):
            for child in component.params['children'].split():
                if key == "root":
                    child_id = child
                    if child_id == "pim_system":
                        continue
                else:
                    child_id = "%s.%s" % (component.id, child)

                if not cht.has_key(child_id):
                    panic("child id %s does not exist!" % child_id)

                component.children.append(cht[child_id])

    # Add all statistics to right component
    for key in sht:
        stat_val = sht[key]
        temp = key.split('.')
        num_fields = len(temp)
        prefix_id = None

        # Find the longest prefix that matches a component id
        for x in xrange(num_fields, 0, -1):
            prefix_id = genId(temp[0:x])
            if cht.has_key(prefix_id):
                break

        # Add the statistic to the right component
        stat_id = genId(temp[x:num_fields])
        if len(stat_id) < 1:
            panic("parsed invalid stat %s" % key)

        # For all those stats that don't have a component, add it to root
        # component
        if not cht.has_key(prefix_id):
            prefix_id = "root"
            stat_id = genId(temp)

        component = cht[prefix_id]
        component.statistics[stat_id] = stat_val

    # Filter out unwanted component info in power.xml
    for key in cht:
        cur_component = cht[key]
        cur_component.checkToFilter(options)
        cur_component.checkToRenameReid(options)

    # Generate calculated statistics
    generateCalcStats(cht, sht, options)

    # Set component types
    for id in cht:
        if "pim_system" not in id:
            component = cht[id]
            setComponentType(component, options)
            if (component.translator != Component.UNKNOWN):
                component.translator.translate_params(component)
                component.translator.translate_statistics(component)

##
## Function - genComponentXml
## genComponentXml() is responsible for generating summary.xml the intermediate
## form for power.xml
##
def genComponentXml(root_component, out_path, options):
    import xml.dom.minidom
    doc = xml.dom.minidom.Document()

    root_component.formXml(doc, doc)

    print("Writing %s..." % out_path)
    f = open(out_path, 'w')
    f.write(doc.toprettyxml())
    f.close()

##
## Function - genPowerXml
## genPowerXml() is responsible for generating power.xml, the interface for
## McPat
##
def genPowerXml(root_component, out_path, options):
    import xml.dom.minidom
    doc = xml.dom.minidom.Document()

    root_component.formXmlPower(doc, doc, options)

    print("Writing %s..." % out_path)
    f = open(out_path, 'w')
    f.write(doc.toprettyxml())
    f.close()

##
## Function - parseSystemConfig
## parseSystemConfig() is repsonsible for creating a component dictionary,
## a statisitic dictionary, and then using this two structures to build a an
## internal tree of component objects that contain fields with their parameters
## and statistics.
## @stats_filepath string to the stats filepath
## @config_filepath string to the config.ini filepath
## @summary_filepath path to put the summary.xml file that is the intermediate
##                   of the power.xml file
## @power_filepath path to put the power.xml file
## @options
##
def parseSystemConfig(stats_filepath, config_filepath, summary_filepath,
                      power_filepath, options):
    # cht dictionary that contains all component keys and their associated objects
    cht = {}
    # sht dictionary that contains all stat keys and their associated stat objects
    sht = {}

    # Parse the configuration file & add all the components to the dictionary
    curr_component = None # current component
    params = {} # params set for the current config
    cf = open(config_filepath, 'r')
    for line in cf:
        # Look for a new component
        if '[' in line and ']' in line and '=' not in line:
            curr_component = line.rstrip().rstrip(']').lstrip('[')
            if cht.has_key(curr_component):
                panic("component %s occurs twice!" % curr_component)
        else:
            # Find params for current component
            if curr_component:
                temp = line.split('=', 1)
                # Assume that a newline or line without an = is the beginning of
                # the next component
                if len(temp) <= 1:
                    cht[curr_component] = Component(curr_component, params)
                    curr_component = None
                    params = {}
                # Grab the param
                elif len(temp) == 2:
                    params[temp[0]] = temp[1].rstrip()
                else:
                    panic("illegal parameter (%s) in component %s" % (line,
                          curr_component))
    cf.close()

    # Parse the stats file & add all the statistics to the dictionary
    sf = open(stats_filepath, 'r')
    for line in sf:
        match = re.match(("(%s[\w\.:]*)\s+([\w\.]+)\s+" % options.system_name),
                         line)
        if match:
            sht[match.group(1)] = match.group(2)
            continue

        match = re.match(r"^(?!pim_system)([\w\.:]*)\s+([\w\.]+)\s+", line)
        if match:
            sht[options.system_name + "." + match.group(1)] = match.group(2)
            continue
    sf.close()

    # Put all the components into a tree
    createComponentTree(cht, sht, options)

    # Generate the intermediate xml summary.xml
    genComponentXml(cht['root'], summary_filepath, options)

    # Generate the McPat power.xml
    genPowerXml(cht['root'], power_filepath, options)

##
## Funtion - run
## run() is repsonsible for creating paths to all important files, and calling
## parseSystemConfig that handles the power.xml creation.
##
def run(options):
    stats_filepath = options.stats_filename
    config_filepath = options.config_filename

    if os.path.isfile(stats_filepath) == False:
        panic("stats file %s does not exist!" % stats_filepath)

    if os.path.isfile(config_filepath) == False:
        panic("config file %s does not exist!" % config_filepath)

    STATS_FILE_BASENAME = os.path.basename(stats_filepath)
    STATS_FILE_DIR = os.path.dirname(stats_filepath)
    summary_filepath = os.path.join(STATS_FILE_DIR, STATS_FILE_BASENAME + "_" +
                                                    options.summary_file_suffix)
    power_filepath = os.path.join(STATS_FILE_DIR, STATS_FILE_BASENAME + "_" +
                                                  options.power_file_suffix)

    print("Processing stats file %s with config file %s ..." %
          (stats_filepath, config_filepath))
    parseSystemConfig(stats_filepath, config_filepath, summary_filepath,
                      power_filepath, options)

def main(options):
    run(options)

if __name__ == '__main__':
    try:
        parser = optparse.OptionParser(formatter =
                                           optparse.TitledHelpFormatter(),
                                       usage = globals()['__doc__'],
                                       version = 'Beta')

        parser.add_option('--system_name',
                          action = 'store',
                          default = 'system',
                          help = """the name the system we are consider for
                                    stats""")
        parser.add_option('--cpu_name',
                          action = 'store',
                          default = 'cpu',
                          help = "the string used cpu comparisons")
        parser.add_option('--l1_cache_cpu_name',
                          action = 'store',
                          default = 'cpu',
                          help = """the name of the cpu to which the l1 dcache
                                    and icache were first attached""")
        parser.add_option('--itb_name',
                          action = 'store',
                          default = 'itb',
                          help = """The name associated with M5's itb""")
        parser.add_option('--dtb_name',
                          action = 'store',
                          default = 'dtb',
                          help = """The name associated with M5's dtb""")
        parser.add_option('-I', '--interconn_names',
                          action = 'store',
                          default = 'tol2bus',
                          help = "The name of the interconnects to consider")

        parser.add_option('-s', '--stats_filename',
                          action = 'store',
                          default = 'stats.txt',
                          help = "the name of the stats file to use")
        parser.add_option('-c', '--config_filename',
                          action = 'store',
                          default = 'config.ini',
                          help = "the name of the config file to use")
        parser.add_option('--summary_file_suffix',
                          action = 'store',
                          default = 'summary.xml',
                          help = "the suffix of the summary output file name")
        parser.add_option('--power_file_suffix',
                          action = 'store',
                          default = 'power.xml',
                          help = "the suffix of the power output file name")

        (options, args) = parser.parse_args()

        main(options)

    # Ctrl-C
    except KeyboardInterrupt, e:
        raise e
    # sys.exit()
    except SystemExit, e:
        raise e
    except Exception, e:
        print("Unexpected exception error: %s" % str(e))
        traceback.print_exc()
        os._exit(1)

# vim:set sr et ts=4 sw=4 ft=python : // See Vim, :help 'modeline'
