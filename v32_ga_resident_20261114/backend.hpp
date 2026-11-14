#pragma once

namespace ga_resident {
namespace {
class Backend {
    struct InputBuffer {
        xrt::bo bo;
        uint64_t* mapped;

        InputBuffer(const xrt::device& device, unsigned group)
            : bo(device, size_t(ga::tile_n) * ga::tile_l * ga::terms * 16,
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

        OutputBuffer(const xrt::device& device, Kernels& kernels, unsigned lane)
            : output(device, size_t(ga::tile_n / 2) * ga::tile_l * 3 * 8,
                     xrt::bo::flags::cacheable, kernels.reducer.group_id(1)),
              params(device, ga::tile_l * 32, xrt::bo::flags::cacheable,
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
    std::vector<uint64_t> merged;
    std::vector<uint64_t> parameters;
    boexp::Clock::time_point deadline;
    const finishsha::Engine& hash;
    const Source& source;
    const bool direct;
    const Window* window = nullptr;
    std::mutex prepare_mutex;

public:
    std::vector<std::string> digests;

    Backend(const xrt::device& device, const xrt::uuid& uuid, unsigned groups,
            const finishsha::Engine& hash, const Source& source, bool direct)
        : hash(hash), source(source), direct(direct) {
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
        for (unsigned i = 0; i < groups; ++i) weights.emplace_back(device, a);
        baby = std::make_unique<InputBuffer>(device, b);
        if (!direct) merged.resize(size_t(ga::tile_n) * ga::tile_l * 3);
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
            frame.timed("baby_copy_sync", -1, epoch, [&] {
                baby->upload(source.baby, t.input_words());
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
                out.reader.set_arg(5, t.k);
                out.reducer.set_arg(3, t.n / 2);
                out.reducer.set_arg(4, t.l);
                out.reducer.set_arg(5, t.k);
                out.params.write(parameters.data(), parameters.size() * 8, 0);
                out.params.sync(XCL_BO_SYNC_BO_TO_DEVICE, parameters.size() * 8, 0);
                std::fill_n(out.mapped, t.output_words() / 2, UINT64_MAX);
                out.output.sync(XCL_BO_SYNC_BO_TO_DEVICE, t.output_words() * 4, 0);
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
        const size_t half = size_t(t.n / 2) * 3;
        for (unsigned lane = 0; lane < 2; ++lane) {
            frame.timed("output_sync", lane, epoch, [&] {
                out[lane]->output.sync(XCL_BO_SYNC_BO_FROM_DEVICE, t.output_words() * 4, 0);
            });
        }
        // The offline manifest hashes only raw little-endian output words.
        // The expected digest covers both halves of every RNS tower.
        auto visit = [&](auto add) {
            for (unsigned tower = 0; tower < t.l; ++tower) {
                for (const auto& lane : out) add(lane->mapped + tower * half, half * 8);
            }
        };
        if (!direct) {
            frame.timed("merge_copy", -1, epoch, [&] {
                auto* target = merged.data();
                visit([&](const uint64_t* data, size_t bytes) {
                    std::memcpy(target, data, bytes);
                    target += bytes / sizeof(uint64_t);
                });
            });
        }
        frame.timed("output_sha256", -1, epoch, [&] {
            digests.at(i) = direct ? hash.segments(nullptr, 0, visit)
                                   : hash.hex(nullptr, 0, merged.data(), t.output_words() * 8);
            check(digests.at(i) == source.output_hashes.at(t.id - 1),
                  ("sealed output SHA256 mismatch at tile " + std::to_string(t.id)).c_str());
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
