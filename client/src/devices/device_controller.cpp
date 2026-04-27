#include "devices/device_controller.h"

namespace telegram_like::client::devices {

std::string DeviceController::describe() const {
    return "device controller ready for active device inspection, trust and revoke flows";
}

}  // namespace telegram_like::client::devices
