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

inline bool read_ahead_allowed() {
    const char* value = std::getenv("V32_GA_DISABLE_READ_AHEAD");
    if (value == nullptr || std::string_view(value) == "0") return true;
    if (std::string_view(value) == "1") return false;
    throw std::invalid_argument("V32_GA_DISABLE_READ_AHEAD must be 0 or 1");
}
}
