/** @file
 * Declaration of a test device.
 */

#ifndef __DEV_TESTDEV_HH__
#define __DEV_TESTDEV_HH__

#include "dev/io_device.hh"
#include "mem/packet.hh"
#include "params/TestDevice.hh"

/**
 * TestDevice
 * ...
 */
class TestDevice : public BasicPioDevice
{
  protected:
    uint8_t retData;

  public:
    typedef TestDeviceParams Params;
    const Params*
    params() const
    {
        return dynamic_cast<const Params*>(_params);
    }

    TestDevice(Params *p);

    virtual Tick read(PacketPtr pkt);
    virtual Tick write(PacketPtr pkt);
};

#endif // __DEV_TESTDEV_HH__
