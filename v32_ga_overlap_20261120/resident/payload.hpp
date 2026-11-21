#pragma once

#include <cstdint>
#include <cstring>
#include <memory>
#include <vector>

namespace ga_resident {
// Wire headers can place a uint64_t at a four-byte offset or across two
// authenticated parts. A view owns its bytes until the last BO copy finishes.
struct Payload {
    using Bytes = std::vector<char>;
    struct Span {
        std::shared_ptr<const Bytes> owner;
        size_t offset, size;
        const char* data() const { return owner->data() + offset; }
    };
    std::vector<Span> spans;
    size_t size = 0;

    void clear() { spans.clear(); size = 0; }

    void copy_to(void* target, size_t bytes) const {
        ga::check(size == bytes, "verified span length differs from BO size");
        auto* out = static_cast<char*>(target);
        for (const auto& span : spans) {
            std::memcpy(out,span.data(),span.size);
            out += span.size;
        }
    }

    void validate(const ga::Tile& tile) const {
        ga::check(size == tile.input_words()*sizeof(uint64_t), "wire payload shape");
        size_t part = 0, at = 0;
        for (unsigned k=0; k<tile.k; ++k) for (uint64_t q : tile.q) {
            size_t left = size_t(tile.n)*2;
            while (left) {
                const auto& span = spans.at(part);
                const size_t whole = std::min(left,(span.size-at)/8);
                if (whole) {
                    uint64_t maximum = 0;
                    for (size_t j=0; j<whole; ++j) {
                        uint64_t word;
                        std::memcpy(&word,span.data()+at+8*j,8);
                        maximum = std::max(maximum,word);
                    }
                    ga::check(maximum < q, "noncanonical input residue");
                    left -= whole;
                    at += 8*whole;
                } else {
                    uint64_t word = 0;
                    size_t filled = 0;
                    while (filled < 8) {
                        const auto& segment = spans.at(part);
                        const size_t n = std::min(8-filled,segment.size-at);
                        std::memcpy(reinterpret_cast<char*>(&word)+filled,segment.data()+at,n);
                        filled += n;
                        at += n;
                        if (at == segment.size) { ++part; at = 0; }
                    }
                    ga::check(word < q, "noncanonical split input residue");
                    --left;
                    continue;
                }
                if (at == span.size) { ++part; at = 0; }
            }
        }
        ga::check(part == spans.size() && at == 0, "unconsumed payload bytes");
    }
};
}
