#include "sim/se_mode_system.hh"

#include <cassert>

#include "cpu/base.hh"
#include "cpu/thread_context.hh"
#include "sim/system.hh"

namespace SEModeSystem {

bool
belongSEsys(const System *const _system)
{
    assert(_system);

    if (_system->name() == SEModeSystemName)
        return true;

    return false;
}

bool
belongSEsys(const BaseCPU *const _cpu)
{
    assert(_cpu);

    return belongSEsys(_cpu->system);
}

bool
belongSEsys(ThreadContext *const _tc)
{
    assert(_tc);

    return belongSEsys(_tc->getSystemPtr());
}

}; //namespace SEModeSystem

