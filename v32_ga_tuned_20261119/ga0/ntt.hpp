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

    struct Pair { uint64_t left, right; };

    uint64_t input_residue(int64_t x) const {
        const int64_t modulus = int64_t(q);
        if (x < -modulus || x >= modulus) x %= modulus;
        return uint64_t(x < 0 ? x + modulus : x);
    }

    static Pair butterfly(uint64_t a, uint64_t b, Twiddle w, uint64_t modulus, uint64_t twice) {
        if (a >= twice) a -= twice;
        const uint64_t low_quotient = uint64_t((Wide(b)*w.quotient) >> 64);
        // The exact nonnegative difference is below 2q.
        const uint64_t right = b*w.value - low_quotient*modulus;
        return {a+right, a+twice-right};
    }

    static uint64_t canonical(uint64_t value, uint64_t modulus, uint64_t twice) {
        if (value >= twice) value -= twice;
        return value >= modulus ? value - modulus : value;
    }

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

    void forward(const int64_t* values, uint64_t* out, bool fuse) const {
        fuse = fuse && Size>=8;
        const uint64_t twice = 2 * q;
        if (fuse) {
            const auto w = table[1];
            for (unsigned j=0;j<Size/2;++j) {
                const auto p=butterfly(input_residue(values[j]),input_residue(values[j+Size/2]),w,q,twice);
                out[j]=p.left;
                out[j+Size/2]=p.right;
            }
        } else {
            for (unsigned j=0;j<Size;++j) out[j]=input_residue(values[j]);
        }
        const unsigned start = fuse ? 2 : 1;
        const unsigned end = fuse ? Size/4 : Size;
        for (unsigned m = start, stride = Size/(2*start); m < end; m *= 2, stride /= 2) {
            for (unsigned i = 0; i < m; ++i) {
                const auto twiddle = table[m + i];
                auto* first = out + 2 * i * stride;
                auto* second = first + stride;
                for (unsigned j = 0; j < stride; ++j) {
                    const auto p=butterfly(first[j],second[j],twiddle,q,twice);
                    first[j]=p.left;
                    second[j]=p.right;
                }
            }
        }
        if (fuse) {
            // Keep the stride-2 and stride-1 stages and final canonicalization
            // in registers for each four-coefficient subtransform.
            for (unsigned i=0;i<Size/4;++i) {
                auto* a=out+4*i;
                const auto w=table[Size/4+i];
                const auto x=butterfly(a[0],a[2],w,q,twice);
                const auto y=butterfly(a[1],a[3],w,q,twice);
                const auto p=butterfly(x.left,y.left,table[Size/2+2*i],q,twice);
                const auto r=butterfly(x.right,y.right,table[Size/2+2*i+1],q,twice);
                a[0]=canonical(p.left,q,twice);
                a[1]=canonical(p.right,q,twice);
                a[2]=canonical(r.left,q,twice);
                a[3]=canonical(r.right,q,twice);
            }
        } else {
            for (unsigned j=0;j<Size;++j) out[j]=canonical(out[j],q,twice);
        }
    }
};
}
