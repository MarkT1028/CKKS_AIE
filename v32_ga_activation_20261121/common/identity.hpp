#pragma once
#include "../../v32_ga3_splitbo_20261109/variants/v32_native_pl_2_pipe/host/variant_config.hpp"
#undef PERF_BOOT_UUID
#undef PERF_VARIANT_ID
#ifndef V32_GA_BUILD_UUID
#error "Select a sealed boot UUID when building the native runner."
#endif
#define PERF_BOOT_UUID V32_GA_BUILD_UUID
#define PERF_VARIANT_ID V32_GA_BUILD_VARIANT
