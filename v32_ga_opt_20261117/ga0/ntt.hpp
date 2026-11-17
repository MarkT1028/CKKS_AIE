#pragma once

#include <cstdint>
#include <stdexcept>
#include <vector>

namespace ga0 {
// Harvey's forward butterfly keeps values in [0, 4q) between stages.
// Canonicalize once at the end to preserve the existing OpenFHE order and ABI.
template<unsigned Size>
class LazyTransform {
    static_assert(Size > 1 && (Size & (Size - 1)) == 0);
    using Wide = unsigned __int128;
    struct Twiddle { uint64_t value, quotient; };
    uint64_t q;
    std::vector<Twiddle> table;

public:
    LazyTransform(uint64_t modulus, uint64_t root) : q(modulus), table(Size) {
        if (q < 3 || q >= (1ULL << 62) || (q & 1) == 0 || root <= 1 || root >= q)
            throw std::invalid_argument("invalid lazy NTT basis");
        uint64_t power = 1;
        unsigned reverse = 0;
        for (unsigned j = 0; j < Size; ++j) {
            table[reverse] = {power, uint64_t((Wide(power) << 64) / q)};
            power = uint64_t(Wide(power) * root % q);
            unsigned bit = Size / 2;
            while (bit && (reverse & bit)) {
                reverse ^= bit;
                bit >>= 1;
            }
            reverse ^= bit;
        }
    }

    void forward(const int64_t* values, uint64_t* out) const {
        const int64_t signed_q = int64_t(q);
        for (unsigned j = 0; j < Size; ++j) {
            int64_t x = values[j];
            if (x < -signed_q || x >= signed_q) x %= signed_q;
            out[j] = uint64_t(x < 0 ? x + signed_q : x);
        }
        const uint64_t twice = 2 * q;
        for (unsigned m = 1, stride = Size / 2; m < Size; m *= 2, stride /= 2) {
            for (unsigned i = 0; i < m; ++i) {
                const auto twiddle = table[m + i];
                auto* first = out + 2 * i * stride;
                auto* second = first + stride;
                for (unsigned j = 0; j < stride; ++j) {
                    const uint64_t a = first[j] >= twice ? first[j] - twice : first[j];
                    const uint64_t b = second[j];
                    const uint64_t estimate = uint64_t((Wide(b) * twiddle.quotient) >> 64);
                    // Unsigned wrap retains the exact difference, which is below 2q.
                    const uint64_t product = b * twiddle.value - estimate * q;
                    first[j] = a + product;
                    second[j] = a + twice - product;
                }
            }
        }
        for (unsigned j = 0; j < Size; ++j) {
            const uint64_t x = out[j] >= twice ? out[j] - twice : out[j];
            out[j] = x >= q ? x - q : x;
        }
    }
};
}
