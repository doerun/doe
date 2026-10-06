#include "dawn/native/DawnNative.h"
extern "C" __attribute__((visibility("default"))) const DawnProcTable* doeDawnControlGetProcs() {
    return &dawn::native::GetProcs();
}
