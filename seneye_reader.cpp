#include <iostream>
#include <iomanip>
#include <vector>
#include <cstring>
#include <unistd.h>
#include <cstdint>
#include "hidapi.h"
#include "json/json.h"

// Seneye Device Identifiers
#define SENEYE_VENDOR_ID 0x2507
#define SENEYE_PRODUCT_ID 0x2204

// Data structures replicated from the original Seneye driver
#pragma pack(push, 1)
struct SUDDATA {
    unsigned int T;
    unsigned int pH;
    unsigned int Nh3;
    struct {
        unsigned int InWater:1;
        unsigned int SlideNotFitted:1;
        unsigned int SlideExpired:1;
    } Bits;
};
struct SUDREADING { SUDDATA Reading; };
struct SUDLIGHTMETERDATA { unsigned int Par; unsigned int Lux; unsigned int PUR; unsigned int Kelvin; };
struct SUDLIGHTMETER { bool IsKelvin; SUDLIGHTMETERDATA Data; };
#pragma pack(pop)

int main() {
    Json::Value output_json;
    const char* device_path = "/dev/hidraw0"; // Default path, may change to hidraw1, etc.

    if (hid_init()) {
        output_json["error"] = "Failed to initialize HIDAPI";
        std::cout << output_json << std::endl;
        return 1;
    }

    // Try to open hidraw0, if that fails, try hidraw1
    hid_device* handle = hid_open_path(device_path);
    if (!handle) {
        device_path = "/dev/hidraw1";
        handle = hid_open_path(device_path);
    }

    if (!handle) {
        hid_exit();
        output_json["error"] = "Could not open Seneye device on hidraw0 or hidraw1.";
        std::cout << output_json << std::endl;
        return 1;
    }

    unsigned char buf[65];

    // 1. Send HELLO and READING commands
    memset(buf, 0x00, sizeof(buf));
    strcpy((char*)buf + 1, "HELLOSUD");
    hid_write(handle, buf, sizeof(buf));
    usleep(200000);

    memset(buf, 0x00, sizeof(buf));
    strcpy((char*)buf + 1, "READING");
    hid_write(handle, buf, sizeof(buf));
    usleep(200000);

    // 2. Read responses to find data packets
    SUDREADING water_reading;
    SUDLIGHTMETER light_reading;
    bool water_ok = false;
    bool light_ok = false;

    for (int i=0; i < 5 && (!water_ok || !light_ok); ++i) {
        int res = hid_read_timeout(handle, buf, sizeof(buf), 1000);
        if (res > 0) {
            if (buf[0] == 0x00 && buf[1] == 0x01) { // Water reading
                memcpy(&water_reading, &buf[2], sizeof(SUDREADING));
                water_ok = true;
            }
            if (buf[0] == 0x00 && buf[1] == 0x02) { // Light reading
                memcpy(&light_reading, &buf[2], sizeof(SUDLIGHTMETER));
                light_ok = true;
            }
        }
    }

    // 3. Send BYE command
    memset(buf, 0x00, sizeof(buf));
    strcpy((char*)buf + 1, "BYESUD");
    hid_write(handle, buf, sizeof(buf));

    hid_close(handle);
    hid_exit();

    // 4. Populate JSON with correctly parsed data
    if (water_ok) {
        output_json["Temp"] = (float)water_reading.Reading.T / 1000.0f;
        output_json["pH"] = (float)water_reading.Reading.pH / 100.0f;
        output_json["NH3"] = (float)water_reading.Reading.Nh3 / 1000.0f;
        output_json["InWater"] = (bool)water_reading.Reading.Bits.InWater;
        output_json["SlideFitted"] = !(bool)water_reading.Reading.Bits.SlideNotFitted;
        output_json["SlideExpired"] = (bool)water_reading.Reading.Bits.SlideExpired;
    }

    if (light_ok) {
        output_json["PAR"] = light_reading.Data.Par;
        output_json["Lux"] = light_reading.Data.Lux;
        output_json["PUR"] = light_reading.Data.PUR;
        output_json["Kelvin"] = light_reading.Data.Kelvin / 1000;
    }

    if (!water_ok && !light_ok) {
        output_json["error"] = "Failed to get a valid reading from device";
    }

    std::cout << output_json << std::endl;

    return 0;
}