"""Exercise native Vulkan adapter selection shared by multiple devices."""

from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path


def bind(library: ctypes.CDLL, name: str, argument_count: int) -> ctypes._CFuncPtr:
    function = getattr(library, name)
    function.argtypes = [ctypes.c_void_p] * argument_count
    function.restype = ctypes.c_void_p if name.endswith(("CreateInstance", "CreateAdapter", "CreateDevice", "GetAdapter")) else None
    return function


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path, help="Built libwebgpu_doe.so")
    args = parser.parse_args()
    library = ctypes.CDLL(str(args.library.resolve()))
    create_instance = bind(library, "doeNativeCreateInstance", 1)
    create_adapter = bind(library, "doeNativeInstanceCreateAdapter", 2)
    create_device = bind(library, "doeNativeAdapterCreateDevice", 2)
    device_adapter = bind(library, "doeNativeDeviceGetAdapter", 1)
    release_instance = bind(library, "doeNativeInstanceRelease", 1)
    release_adapter = bind(library, "doeNativeAdapterRelease", 1)
    release_device = bind(library, "doeNativeDeviceRelease", 1)

    instance = create_instance(None)
    assert instance, "native instance creation failed"
    adapter = create_adapter(instance, None)
    assert adapter, "native Vulkan adapter selection failed"
    release_instance(instance)

    first = create_device(adapter, None)
    second = create_device(adapter, None)
    assert first and second and first != second, "two Vulkan devices were not created"
    first_adapter = device_adapter(first)
    second_adapter = device_adapter(second)
    assert first_adapter == adapter and second_adapter == adapter, "device adapter identity changed"
    release_adapter(first_adapter)
    release_adapter(second_adapter)

    release_adapter(adapter)
    release_device(first)
    third = create_device(device_adapter(second), None)
    assert third and third != second, "selection did not survive releasing the first device"
    release_device(second)
    release_device(third)
    # The device adapter query above owns one reference.
    release_adapter(adapter)
    print(json.dumps({"devices": 3, "adapter_identity_preserved": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
