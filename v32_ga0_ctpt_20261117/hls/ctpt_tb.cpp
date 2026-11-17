#include "ct_mac.hpp"
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace ctmac;
extern "C" int ctpt_chain(const input_t*, const input_t*, word_t*, const param_t*,
                          unsigned, unsigned, unsigned, unsigned);

int main() {
    try {
        const uint64_t moduli[] = {(1ULL << 44) + 1, (1ULL << 51) - 129, (1ULL << 60) - 1};
        const uint64_t canary = 0xdeadc0de0bad7a11ULL;
        param_t params[MAX_L]{};
        for (unsigned t = 0; t < MAX_L; ++t) {
            const auto q = moduli[t % 3];
            params[t] = q;
            params[t].range(191, 64) = ap_uint<128>((ap_uint<129>(1) << 128) / q);
        }
        uint64_t state = 0x20261117;
        std::vector<input_t> weights(16384), plain(8192);
        std::vector<word_t> outputs(8194);
        for (unsigned sample = 0; sample < 6; ++sample) {
            const unsigned n = sample < 2 ? 64 : sample < 4 ? 128 : 4096;
            const unsigned l = sample < 2 ? 3 : sample < 4 ? 16 : 1;
            const unsigned k = sample < 2 ? 1 : sample < 4 ? 16 : 2;
            const unsigned lane = sample % 2;
            const unsigned count = 2 * n * l * k;
            std::vector<uint64_t> a(count * 2), b(count);
            for (unsigned i = 0; i < count; ++i) {
                const auto q = moduli[(i / (2 * n) % l) % 3];
                state = state * 6364136223846793005ULL + 1442695040888963407ULL;
                b[i] = i % 5 == 0 ? q - 1 : i % 7 == 0 ? 0 : state % q;
                for (unsigned c = 0; c < 2; ++c) {
                    state = state * 6364136223846793005ULL + 1442695040888963407ULL;
                    a[2 * i + c] = i % 5 == 0 ? q - 1 : state % q;
                }
            }
            for (unsigned i = 0; i < count; ++i) {
                plain[i / 8].range(64 * (i % 8) + 63, 64 * (i % 8)) = b[i];
            }
            for (unsigned i = 0; i < 2 * count; ++i) {
                weights[i / 8].range(64 * (i % 8) + 63, 64 * (i % 8)) = a[i];
            }
            for (auto& word : outputs) word = canary;
            if (ctpt_chain(weights.data(), plain.data(), outputs.data() + 1, params, n, l, k, lane))
                throw std::runtime_error("CTPT chain status");
            if (outputs[0] != canary || outputs[2 * n * l + 1] != canary)
                throw std::runtime_error("CTPT output guard overwritten");
            for (unsigned t = 0; t < l; ++t) for (unsigned j = 0; j < n; ++j) {
                for (unsigned c = 0; c < 2; ++c) {
                    unsigned __int128 sum = 0;
                    for (unsigned p = 0; p < k; ++p) {
                        const size_t index = (size_t(p) * l + t) * 2 * n + lane * n + j;
                        sum += static_cast<unsigned __int128>(a[2 * index + c]) * b[index];
                    }
                    if (outputs[1 + 2 * (t * n + j) + c] != uint64_t(sum % moduli[t % 3]))
                        throw std::runtime_error("CTPT result differs from exact reference");
                }
            }
            std::cout << "PASS_CTPT N=" << n << " L=" << l << " K=" << k << " lane=" << lane << '\n';
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
