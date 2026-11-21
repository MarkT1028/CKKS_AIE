#pragma once
#include <common/finish_overlap.hpp>

namespace boexp {
// Only the controller launches kernels. Its previous output is already
// complete while the worker prepares the third, disjoint bank.
template<class Backend>
Replay run_three_bank(Backend& backend, unsigned count, Worker& worker, bool save) {
    ensure(count != 0, "empty three-bank replay");
    Replay replay;
    replay.frames.resize(count);
    const auto epoch = Clock::now();
    auto prepare = [&](unsigned index) {
        auto& frame = replay.frames[index];
        frame.chunk = index;
        frame.bank = index % 3;
        backend.prepare(index, frame.bank, frame, epoch);
    };
    auto finish = [&](unsigned index) {
        auto& frame = replay.frames[index];
        backend.finish(index, frame.bank, frame, epoch);
        if (save) frame.timed("output_save", -1, epoch, [&] { backend.save(index, frame.bank); });
    };
    try {
        prepare(0);
        for (unsigned i = 0; i < count; ++i) {
            if (i) worker.wait();
            auto& frame = replay.frames[i];
            const auto start = Clock::now();
            backend.start(i, frame.bank);
            if (i + 1 < count) worker.submit([&, next = i + 1] { prepare(next); });
            if (i) finish(i - 1);
            backend.wait(i, frame.bank);
            ensure(frame.count < frame.spans.size(), "execute trace capacity");
            frame.spans[frame.count++] = {"execute", -1, elapsed(epoch,start), elapsed(epoch,Clock::now())};
            backend.complete(i, frame.bank, frame, epoch);
        }
        finish(count - 1);
        replay.wall_ms = elapsed(epoch, Clock::now());
        return replay;
    } catch (...) {
        worker.close(); // Drain host BO accesses before aborting or unwinding its owners.
        backend.cancel();
        throw;
    }
}
}
