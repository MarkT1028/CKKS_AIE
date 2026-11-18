#pragma once

#if defined(__aarch64__)
#include <arm_neon.h>
#endif

namespace ga_resident {
namespace {
class Backend {
    struct InputBuffer {
        xrt::bo bo;
        uint64_t* mapped;

        InputBuffer(const xrt::device& device, unsigned group, unsigned components)
            : bo(device, size_t(ga0::N) * ga0::L * ga0::K * components * sizeof(uint64_t),
                 xrt::bo::flags::cacheable, group),
              mapped(bo.map<uint64_t*>()) {
            check(mapped, "map input BO");
        }

        void upload(const std::vector<uint64_t>& data, size_t expected) {
            check(data.size() == expected, "unexpected host input size");
            const size_t bytes = data.size() * sizeof(uint64_t);
            std::memcpy(mapped, data.data(), bytes);
            bo.sync(XCL_BO_SYNC_BO_TO_DEVICE, bytes, 0);
        }
    };

    struct OutputBuffer {
        xrt::bo output, params;
        xrt::run reader, reducer;
        uint64_t* mapped;
        std::vector<uint64_t> cached_parameters;

        OutputBuffer(const xrt::device& device, Kernels& kernels, unsigned lane)
            : output(device, size_t(ga0::N / 2) * ga0::L * 2 * 8,
                     xrt::bo::flags::cacheable, kernels.reducer.group_id(1)),
              params(device, ga0::L * 32, xrt::bo::flags::cacheable,
                     kernels.reducer.group_id(2)),
              reader(kernels.reader), reducer(kernels.reducer), mapped(output.map<uint64_t*>()) {
            check(mapped, "map output BO");
            reducer.set_arg(1, output);
            reducer.set_arg(2, params);
            reader.set_arg(6, lane);
        }
    };

    using Bank = std::array<std::unique_ptr<OutputBuffer>, 2>;
    std::array<std::unique_ptr<Kernels>, 2> kernels;
    std::array<Bank, 2> banks;
    std::vector<InputBuffer> weights;
    std::unique_ptr<InputBuffer> baby;
    std::vector<uint64_t> parameters;
    boexp::Clock::time_point deadline;
    const finishsha::Engine& hash;
    const Source& source;
    std::function<void(uint64_t*, size_t)> baby_writer;
    const Window* window = nullptr;
    std::mutex prepare_mutex;

public:
    std::vector<std::string> digests;

    Backend(const xrt::device& device, const xrt::uuid& uuid, unsigned groups,
            const finishsha::Engine& hash, const Source& source, bool)
        : hash(hash), source(source) {
        for (unsigned lane = 0; lane < 2; ++lane) {
            kernels[lane] = std::make_unique<Kernels>(device, uuid, lane);
            for (auto& bank : banks) {
                bank[lane] = std::make_unique<OutputBuffer>(device, *kernels[lane], lane);
            }
        }
        const auto a = kernels[0]->reader.group_id(0), b = kernels[0]->reader.group_id(1);
        check(a == kernels[1]->reader.group_id(0) && b == kernels[1]->reader.group_id(1),
              "lane memory groups differ");
        weights.reserve(groups);
        for (unsigned i = 0; i < groups; ++i) weights.emplace_back(device, a, 2);
        baby = std::make_unique<InputBuffer>(device, b, 1);
    }

    void set_baby_writer(std::function<void(uint64_t*, size_t)> writer) {
        baby_writer = std::move(writer);
    }

    void configure(const Window& selected) {
        window = &selected;
        const auto& t = window->tiles.front();
        InputCase shape;
        shape.n = t.n / 2;
        shape.l = t.l;
        shape.k = t.k;
        for (auto q : t.q) {
            const auto mu = ~static_cast<unsigned __int128>(0) / q;
            shape.parameters.push_back({q, uint64_t(mu), uint64_t(mu >> 64)});
        }
        parameters = pack_parameters(shape);
        digests.assign(window->tiles.size(), {});
    }

    void prepare(unsigned i, unsigned bank, boexp::Frame& frame, boexp::Clock::time_point epoch) {
        const std::lock_guard<std::mutex> guard(prepare_mutex);
        const auto& t = window->tiles.at(i);
        // Only the first group of a window writes the shared baby. Each weight
        // slot is written before its first use and then read-only for the block.
        if (!(t.flags & ga::reuse_baby)) {
            check(bool(baby_writer), "missing compact plaintext packing callback");
            const auto words = t.input_words() / 2;
            frame.timed("baby_pack", -1, epoch, [&] {
                baby_writer(baby->mapped, words);
            });
            frame.timed("baby_copy_sync", -1, epoch, [&] {
                baby->bo.sync(XCL_BO_SYNC_BO_TO_DEVICE, words * sizeof(uint64_t), 0);
            });
        }
        if (!(t.flags & ga::reuse_weight)) {
            frame.timed("weight_copy_sync", -1, epoch, [&] {
                weights.at(t.slot).upload(source.weights.at(t.slot), t.input_words());
            });
        }
        for (unsigned lane = 0; lane < 2; ++lane) {
            auto& out = *banks.at(bank).at(lane);
            frame.timed("prepare_lane", lane, epoch, [&] {
                out.reader.set_arg(0, weights.at(t.slot).bo);
                out.reader.set_arg(1, baby->bo);
                out.reader.set_arg(3, t.n / 2);
                out.reader.set_arg(4, t.l);
                out.reader.set_arg(5, unsigned(t.k | 0x10000U));
                out.reducer.set_arg(3, t.n / 2);
                out.reducer.set_arg(4, t.l);
                out.reducer.set_arg(5, unsigned(t.k | 0x10000U));
                if (out.cached_parameters != parameters) {
                    out.params.write(parameters.data(), parameters.size() * 8, 0);
                    out.params.sync(XCL_BO_SYNC_BO_TO_DEVICE, parameters.size() * 8, 0);
                    out.cached_parameters = parameters;
                }
                std::fill_n(out.mapped, size_t(t.n) * t.l, UINT64_MAX);
                out.output.sync(XCL_BO_SYNC_BO_TO_DEVICE, size_t(t.n) * t.l * sizeof(uint64_t), 0);
            });
        }
    }

    void start(unsigned, unsigned bank) {
        deadline = boexp::Clock::now() + std::chrono::seconds(120);
        for (auto& out : banks.at(bank)) out->reducer.start();
        for (auto& out : banks.at(bank)) out->reader.start();
    }

    void wait(unsigned, unsigned bank) {
        for (auto& out : banks.at(bank)) wait_for_run("reader", out->reader, deadline);
        for (auto& out : banks.at(bank)) wait_for_run("reducer", out->reducer, deadline);
    }

    void complete(unsigned, unsigned, boexp::Frame& frame, boexp::Clock::time_point epoch) {
        frame.timed("status", -1, epoch, [&] {
            for (const auto& k : kernels) {
                check(k->reader.read_register(0x10) == 0 && k->reducer.read_register(0x10) == 0,
                      "PL kernel status");
            }
        });
    }

    void finish(unsigned i, unsigned bank, boexp::Frame& frame, boexp::Clock::time_point epoch) {
        const auto& t = window->tiles.at(i);
        const auto& out = banks.at(bank);
        const size_t half = t.n / 2;
        const size_t lane_bytes = half * t.l * 2 * sizeof(uint64_t);
        for (unsigned lane = 0; lane < 2; ++lane) {
            frame.timed("output_sync", lane, epoch, [&] {
                out[lane]->output.sync(XCL_BO_SYNC_BO_FROM_DEVICE, lane_bytes, 0);
            });
        }
        frame.timed("output_sha256", -1, epoch, [&] {
            // Rebuild each canonical triple in a small staging buffer. The third
            // coefficient is zero for each plaintext product, including K sums.
            constexpr size_t batch = 256;
            std::array<uint64_t, batch * 3> canonical;
            auto visit = [&](auto add) {
                for (unsigned tower = 0; tower < t.l; ++tower) {
                    for (const auto& output : out) {
                        const auto* in = output->mapped + tower * half * 2;
                        for (size_t first = 0; first < half; first += batch) {
                            const size_t count = std::min(batch, half - first);
                            size_t j = 0;
#if defined(__aarch64__)
                            const uint64x2_t zero = vdupq_n_u64(0);
                            for (; j + 1 < count; j += 2) {
                                const uint64x2x2_t pair = vld2q_u64(in + 2 * (first + j));
                                vst3q_u64(canonical.data() + 3 * j, {pair.val[0], pair.val[1], zero});
                            }
#endif
                            for (; j < count; ++j) {
                                canonical[3 * j] = in[2 * (first + j)];
                                canonical[3 * j + 1] = in[2 * (first + j) + 1];
                                canonical[3 * j + 2] = 0;
                            }
                            add(canonical.data(), count * 3 * sizeof(uint64_t));
                        }
                    }
                }
            };
            digests.at(i) = hash.segments(nullptr, 0, visit);
            check(digests.at(i) == source.output_hashes.at(t.id - 1),
                  ("sealed CTPT SHA256 mismatch at tile " + std::to_string(t.id)).c_str());
        });
    }

    void save(unsigned, unsigned) {}

    void cancel() noexcept {
        const std::lock_guard<std::mutex> guard(prepare_mutex);
        for (auto& bank : banks) {
            for (auto& out : bank) {
                try { out->reader.abort(); } catch (...) {}
                try { out->reducer.abort(); } catch (...) {}
            }
        }
    }
};
}
}
