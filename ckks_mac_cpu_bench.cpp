// Same-board, single-thread integer MAC baseline. Not an OpenFHE benchmark.
#define CKKSMAC_PARSER_ONLY
#define main ckks_parser_main
#include "ckks_mac_timed_xrt.cpp"
#undef main
#include <algorithm>

int main(int argc, char** argv) {
    try {
        require(argc == 3, "Usage: ckks_mac_cpu_bench INPUT_BIN EXPECTED_BIN");
        const auto input = read_input(argv[1]);
        print_inspection(input);
        const size_t prefix = 64 + input.parameters.size() * 24;
        require(fs::file_size(argv[2]) == prefix + input.output_words() * 8,
                "expected output length mismatch");
        std::ifstream golden_stream(argv[2], std::ios::binary);
        std::array<char, 8> magic{};
        golden_stream.read(magic.data(), magic.size());
        require(std::string(magic.data(), magic.size()) == "CKKSMAC1", "expected output magic mismatch");
        const std::array<uint32_t, 10> header{1, 2, input.n, input.l, input.k, 3, 1, 64, 0, 0};
        for (auto value : header) require(read_le(golden_stream, 4) == value, "expected output header mismatch");
        require(read_le(golden_stream, 8) == input.output_words(), "expected output word count mismatch");
        require(read_le(golden_stream, 8) == 0, "expected output reserved field mismatch");
        for (const auto& parameter : input.parameters) {
            require(read_le(golden_stream, 8) == parameter.q, "expected modulus mismatch");
            require(read_le(golden_stream, 8) == parameter.mu_lo, "expected reciprocal mismatch");
            require(read_le(golden_stream, 8) == parameter.mu_hi, "expected reciprocal mismatch");
        }
        std::vector<uint64_t> golden(static_cast<size_t>(input.output_words()));
        for (auto& value : golden) value = read_le(golden_stream, 8);
        std::vector<uint64_t> output(static_cast<size_t>(input.output_words()));
        std::array<double, 3> samples{};
        for (unsigned repetition = 0; repetition < 4; ++repetition) {
            const auto begin = std::chrono::steady_clock::now();
            for (uint32_t tower = 0; tower < input.l; ++tower) {
                const uint64_t q = input.parameters[tower].q;
                for (uint32_t j = 0; j < input.n; ++j) {
                    U128 s0 = 0, s1 = 0, s2 = 0;
                    for (uint32_t pair = 0; pair < input.k; ++pair) {
                        const size_t base = ((size_t(pair) * input.l + tower) * input.n + j) * 4;
                        const auto a0 = input.words[base];
                        const auto a1 = input.words[base + 1];
                        const auto b0 = input.words[base + 2];
                        const auto b1 = input.words[base + 3];
                        s0 += U128(a0) * b0;
                        s1 += U128(a0) * b1 + U128(a1) * b0;
                        s2 += U128(a1) * b1;
                    }
                    // q < 2^60, K <= 16: the largest sum is < 2^125.
                    const size_t base = (size_t(tower) * input.n + j) * 3;
                    output[base] = static_cast<uint64_t>(s0 % q);
                    output[base + 1] = static_cast<uint64_t>(s1 % q);
                    output[base + 2] = static_cast<uint64_t>(s2 % q);
                }
            }
            const auto end = std::chrono::steady_clock::now();
            for (size_t i = 0; i < output.size(); ++i)
                require(output[i] == golden[i],
                        "CPU mismatch at word " + std::to_string(i));
            const double elapsed = std::chrono::duration<double, std::milli>(end - begin).count();
            if (repetition) samples[repetition - 1] = elapsed;
            std::cout << std::fixed << std::setprecision(6)
                      << "CPU repetition=" << repetition << " compute_ms=" << elapsed
                      << " verified_words=" << output.size() << "\n";
        }
        std::sort(samples.begin(), samples.end());
        std::cout << "CPU_MEDIAN compute_ms=" << samples[1] << "\nPASS CPU reference\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << "\n";
        return 1;
    }
}
