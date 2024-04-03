#ifndef __SIM_SE_MODE_SYSTEM_HH__
#define __SIM_SE_MODE_SYSTEM_HH__

#include <string>

class BaseCPU;
class System;
class ThreadContext;

namespace SEModeSystem {

extern std::string SEModeSystemName;

/**
 * Return true if the object belongs to the specific SE mode system, and vice
 * versa. In addition, when the SE mode system name is not set, it returns
 * false
 */
bool belongSEsys(const System *const _system);
bool belongSEsys(const BaseCPU *const _cpu);
bool belongSEsys(ThreadContext *const _tc);

}; //namespace SEModeSystem

#endif // __SIM_SE_MODE_SYSTEM_HH__
