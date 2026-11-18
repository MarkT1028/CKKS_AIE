#include "ct_mac.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace ctmac;
extern "C" int ga_chain(const input_t*, const input_t*, word_t*, const param_t*,
                         unsigned, unsigned, unsigned, unsigned);

namespace {
using Wide = unsigned __int128;

void pack(const std::vector<uint64_t>& words, std::vector<input_t>& beats) {
    for (size_t i = 0; i < words.size(); ++i) {
        beats[i/8].range(64*(i%8) + 63, 64*(i%8)) = words[i];
    }
}

void check_case(bool plaintext, unsigned n, unsigned l, unsigned k, unsigned lane) {
    const uint64_t moduli[] = {(1ULL << 44) + 1, (1ULL << 51) - 129, (1ULL << 60) - 1};
    const uint64_t canary = 0xdeadc0de0bad7a11ULL;
    param_t params[MAX_L]{};
    for (unsigned t = 0; t < MAX_L; ++t) {
        const auto q = moduli[t % 3];
        params[t] = q;
        params[t].range(191, 64) = ap_uint<128>((ap_uint<129>(1) << 128) / q);
    }
    uint64_t state = 0x20261117;
    auto random = [&] (uint64_t q) {
        state = state*6364136223846793005ULL + 1442695040888963407ULL;
        return (state >> 3) % q;
    };
    const unsigned input_components = plaintext ? 1 : 2;
    const unsigned output_components = plaintext ? 2 : 3;
    const size_t count = 2*n*l*k;
    std::vector<uint64_t> a(2*count), b(input_components*count);
    for (size_t i = 0; i < count; ++i) {
        const auto q = moduli[(i/(2*n) % l) % 3];
        a[2*i] = i%4 == 0 ? q - 1 : i%4 == 1 ? 0 : random(q);
        a[2*i + 1] = i%4 == 0 ? 0 : i%4 == 1 ? q - 1 : random(q);
        b[input_components*i] = i%4 < 2 ? q - 1 : random(q);
        if (!plaintext) b[2*i + 1] = i%4 < 2 ? 0 : random(q);
    }
    std::vector<input_t> a_beats(131072), b_beats(131072);
    std::vector<word_t> output(32770);
    pack(a, a_beats);
    pack(b, b_beats);
    std::fill(output.begin(), output.end(), canary);
    if (ga_chain(a_beats.data(), b_beats.data(), output.data() + 1, params,
                 n, l, k | (plaintext ? plaintext_mode : 0), lane) != OK)
        throw std::runtime_error("GA chain returned an error");
    if (output[0] != canary || output[output_components*n*l + 1] != canary)
        throw std::runtime_error("GA chain wrote outside its output");
    for (unsigned t = 0; t < l; ++t) for (unsigned j = 0; j < n; ++j) {
        Wide sum[3] = {};
        for (unsigned p = 0; p < k; ++p) {
            const size_t i = (size_t(p)*l + t)*2*n + lane*n + j;
            sum[0] += Wide(a[2*i])*b[input_components*i];
            sum[1] += Wide(a[2*i + 1])*b[input_components*i];
            if (!plaintext) {
                sum[1] += Wide(a[2*i])*b[2*i + 1];
                sum[2] += Wide(a[2*i + 1])*b[2*i + 1];
            }
        }
        for (unsigned c = 0; c < output_components; ++c) {
            if (output[1 + output_components*(t*n + j) + c] != uint64_t(sum[c] % moduli[t % 3]))
                throw std::runtime_error("GA chain differs from the four-product reference");
        }
    }
    std::cout << "PASS_GA_CHAIN plaintext=" << plaintext << " N=" << n << " L=" << l
              << " K=" << k << " lane=" << lane << '\n';
}
}

int main() {
    try {
        for (unsigned lane = 0; lane < 2; ++lane) {
            check_case(false, 64, 3, 1, lane);
            check_case(true, 128, 16, 16, lane);
            check_case(false, 128, 16, 16, lane);
            check_case(true, 4096, 1, 2, lane);
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
