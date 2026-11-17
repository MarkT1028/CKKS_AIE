#include "../../v32_ga0_full_20261114/ga0.hpp"
#include "../ga0/ntt.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <limits>
#include <random>

int main(int argc, char** argv) {
    using namespace ga0;
    if (argc != 3) throw std::runtime_error("expected basis.txt and a compact plaintext input");
    std::ifstream basis(argv[1]), data(argv[2], std::ios::binary);
    std::vector<int64_t> real(Ring), test(Ring);
    data.read(reinterpret_cast<char*>(real.data()), real.size() * sizeof(int64_t));
    if (!data) throw std::runtime_error("truncated plaintext input");
    std::vector<uint64_t> baseline(Ring), candidate(Ring);
    std::mt19937_64 random(0x764280);
    using Clock = std::chrono::steady_clock;
    Clock::duration baseline_time{}, fast_time{};
    for (unsigned i = 0; i < Towers; ++i) {
        uint64_t q, root;
        if (!(basis >> q >> root)) throw std::runtime_error("missing basis");
        Transform old(q, root);
        LazyTransform<Ring> fast(q, root);
        for (unsigned input = 0; input < 2; ++input) {
            if (input == 0) {
                test = real;
            } else {
                for (auto& x : test) x = int64_t(random() >> 1) - (int64_t(1) << 62);
                test[0] = std::numeric_limits<int64_t>::min();
                test[1] = std::numeric_limits<int64_t>::max();
                test[2] = -int64_t(q);
                test[3] = int64_t(q);
                test[4] = 0;
            }
            const auto start = Clock::now();
            old.forward(test.data(), baseline.data());
            const auto middle = Clock::now();
            fast.forward(test.data(), candidate.data());
            const auto end = Clock::now();
            baseline_time += middle - start;
            fast_time += end - middle;
            if (baseline != candidate) throw std::runtime_error("NTT mismatch at tower " + std::to_string(i));
        }
    }
    std::cout << "PASS_GA0_EXACT_NTT towers=" << Towers << " vectors=" << Towers * 2
              << " baseline_x86_seconds=" << std::chrono::duration<double>(baseline_time).count()
              << " lazy_x86_seconds=" << std::chrono::duration<double>(fast_time).count() << '\n';
}
