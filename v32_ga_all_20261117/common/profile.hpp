#pragma once

#include <cstdlib>
#include <stdexcept>
#include <string_view>

namespace ga_opt {
inline bool fast_profile() {
    const char* value = std::getenv("V32_GA_OPT_PROFILE");
    if (value == nullptr || std::string_view(value) == "baseline") return false;
    if (std::string_view(value) == "fast") return true;
    throw std::invalid_argument("V32_GA_OPT_PROFILE must be baseline or fast");
}
}
