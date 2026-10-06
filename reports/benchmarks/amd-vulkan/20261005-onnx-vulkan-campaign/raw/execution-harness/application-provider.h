// Native integration and observations; the upstream application owns inference.
#pragma once
#include "dawn/dawn_proc_table.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <dlfcn.h>
#include <fstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>

inline const char* campaign_env(const char* name) {
    const char* value = std::getenv(name);
    if (!value || !*value) throw std::runtime_error(std::string("Missing campaign input: ") + name);
    return value;
}

class CampaignProvider {
    Ort::Env& env;
    const DawnProcTable* table = nullptr;
    WGPUInstance instance = nullptr;
    WGPUDevice device = nullptr;
    void (*release)(const DawnProcTable*, WGPUInstance, WGPUDevice) = nullptr;
    bool registered = false;
    uint64_t (*call_count)(size_t) = nullptr;
    size_t (*proc_count)() = nullptr;
    // Proc libraries intentionally share the consumer's process lifetime.
    static void* load(const char* name) {
        void* handle = dlopen(campaign_env(name), RTLD_NOW | RTLD_LOCAL);
        if (!handle) throw std::runtime_error(dlerror());
        return handle;
    }
    template<class T> static T symbol(void* library, const char* name) {
        void* address = dlsym(library, name);
        if (!address) throw std::runtime_error(std::string("Missing native symbol: ") + name);
        return reinterpret_cast<T>(address);
    }
    void close() {
        if (registered) { env.UnregisterExecutionProviderLibrary("campaign"); registered = false; }
        if (release) { release(table, instance, device); device = nullptr; instance = nullptr; }
    }
public:
    CampaignProvider(Ort::Env& owner, Ort::SessionOptions& options) : env(owner) {
        try {
            std::string arm = campaign_env("CAMPAIGN_ARM");
            if (arm != "doe" && arm != "dawn") throw std::runtime_error("Unknown arm");
            auto library = load("CAMPAIGN_BRIDGE");
            auto initialize = symbol<const DawnProcTable* (*)(const char*)>(library,
                arm == "doe" ? "doeDawnBridgeInitialize" : "doeDawnBridgeInitializeControl");
            call_count = symbol<decltype(call_count)>(library, "doeDawnBridgeCallCount");
            proc_count = symbol<decltype(proc_count)>(library, "doeDawnBridgeProcCount");
            table = initialize(campaign_env("CAMPAIGN_NATIVE"));
            if (!table) throw std::runtime_error("Proc-table initialization failed");
            auto context = load("CAMPAIGN_CONTEXT");
            struct Identity { uint32_t backend, vendor, device, type; } identity{};
            release = symbol<decltype(release)>(context, "doeExternalContextRelease");
            auto create = symbol<int (*)(const DawnProcTable*, WGPUInstance*, WGPUDevice*, Identity*)>(context, "doeExternalContextCreate");
            if (create(table, &instance, &device, &identity)) throw std::runtime_error("Physical AMD Vulkan context rejected");
            std::cout << "CampaignContext " << identity.backend << " " << identity.vendor << " "
                      << identity.device << " " << identity.type << "\n";
            env.RegisterExecutionProviderLibrary("campaign", campaign_env("CAMPAIGN_PROVIDER"));
            registered = true;
            std::vector<Ort::ConstEpDevice> selected;
            for (auto candidate : env.GetEpDevices()) {
                if (std::string(candidate.EpName()) == "WebGpuExecutionProvider" &&
                    candidate.Device().VendorId() == 0x1002) selected.push_back(candidate);
            }
            if (selected.size() != 1) throw std::runtime_error("Expected one AMD WebGPU EP device");
            Ort::KeyValuePairs settings({
                {"dawnProcTable", std::to_string(reinterpret_cast<uintptr_t>(table))},
                {"webgpuInstance", std::to_string(reinterpret_cast<uintptr_t>(instance))},
                {"webgpuDevice", std::to_string(reinterpret_cast<uintptr_t>(device))},
                {"deviceId", "0"}, {"dawnBackendType", "Vulkan"}, {"validationMode", "full"}});
            options.AddConfigEntry("session.disable_cpu_ep_fallback", "1");
            options.AppendExecutionProvider_V2(env, selected, settings);
            if (std::string(campaign_env("CAMPAIGN_MODE")) == "qualification")
                options.EnableProfiling(campaign_env("CAMPAIGN_PROFILE"));
        } catch (...) { close(); throw; }
    }
    ~CampaignProvider() {
        try { close(); }
        catch (const std::exception& error) { std::cerr << "CampaignCleanupFailure " << error.what() << "\n"; }
        if (call_count) for (size_t index = 0; index < proc_count(); ++index)
            if (call_count(index)) std::cout << "CampaignCallCount " << index << " " << call_count(index) << "\n";
    }
};

inline std::vector<Ort::Value> campaign_run(Ort::Session& session, const char* const* names,
    const Ort::Value* input, size_t count, const char* const* outputs, size_t output_count) {
    const int warmup = std::stoi(campaign_env("CAMPAIGN_WARMUP"));
    const int runs = std::stoi(campaign_env("CAMPAIGN_RUNS"));
    const bool timing = std::string(campaign_env("CAMPAIGN_MODE")) == "timing";
    const float atol = std::stof(campaign_env("CAMPAIGN_ATOL"));
    const float rtol = std::stof(campaign_env("CAMPAIGN_RTOL"));
    std::ifstream reference(campaign_env("CAMPAIGN_REFERENCE"), std::ios::binary);
    if (!reference) throw std::runtime_error("Reference absent");
    std::vector<float> expected(1000);
    reference.read(reinterpret_cast<char*>(expected.data()), expected.size() * sizeof(float));
    if (!reference || reference.peek() != EOF) throw std::runtime_error("Reference shape changed");
    std::vector<Ort::Value> result;
    std::ofstream observations(campaign_env("CAMPAIGN_OBSERVATIONS"));
    if (!observations || warmup < 0 || runs < 1) throw std::runtime_error("Invalid observation contract");
    for (int iteration = -warmup; iteration < runs; ++iteration) {
        auto start = std::chrono::steady_clock::now();
        auto cpu_start = std::clock();
        result = session.Run(Ort::RunOptions{nullptr}, names, input, count, outputs, output_count);
        auto cpu_end = std::clock();
        auto end = std::chrono::steady_clock::now();
        if (result.size() != 1 || result[0].GetTensorTypeAndShapeInfo().GetElementCount() != expected.size())
            throw std::runtime_error("Application output shape changed");
        auto values = result[0].GetTensorData<float>();
        for (size_t i = 0; i < expected.size(); ++i)
            if (!std::isfinite(values[i]) || std::abs(values[i] - expected[i]) > atol + rtol * std::abs(expected[i]))
                throw std::runtime_error("Independent oracle mismatch at class " + std::to_string(i));
        if (std::max_element(values, values + expected.size()) - values !=
            std::max_element(expected.begin(), expected.end()) - expected.begin())
            throw std::runtime_error("Application winning class changed");
        if (iteration >= 0 && timing) observations << iteration << " "
            << std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count() << " "
            << (double(cpu_end - cpu_start) * 1e9 / CLOCKS_PER_SEC) << "\n";
    }
    struct rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage)) throw std::runtime_error("RSS observation failed");
    std::cout << "CampaignPeakRss " << uint64_t(usage.ru_maxrss) * 1024 << "\n";
    if (!timing) {
        Ort::AllocatorWithDefaultOptions allocator;
        auto path = session.EndProfilingAllocated(allocator);
        std::cout << "CampaignProfile " << path.get() << "\n";
    }
    return result;
}
