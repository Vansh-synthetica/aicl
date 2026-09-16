// =============================================================================
//  aicl_test.cpp — Simple smoke test for AICL C++ adapter
// =============================================================================

#include <aicl/aicl_adapter.hpp>
#include <aicl/aicl_model.hpp>
#include <aicl/aicl_value.hpp>

#include <iostream>
#include <cassert>

using namespace aicl;

#define CHECK(cond) do { \
    if (!(cond)) { \
        std::cerr << "FAIL: " << #cond << " at line " << __LINE__ << "\n"; \
        return 1; \
    } \
} while(0)

int main() {
    std::cout << "AICL C++ adapter smoke test\n";

    // Test 1: Create adapter
    AICLModelAdapter adapter;
    CHECK(true); // constructor didn't throw

    // Test 2: Install backend
    adapter.install_backend(BackendKind::Dummy, "", 2048);
    std::cout << "PASS: install_backend\n";

    // Test 3: Register model
    auto model = load_model(BackendKind::Dummy, "", {});
    CHECK(model != nullptr);
    model->info().id = "test-model";
    u16 cap = adapter.register_model(std::move(model));
    CHECK(cap != 0);
    std::cout << "PASS: register_model (cap=" << cap << ")\n";

    // Test 4: Non-streaming call
    ModelRequest req;
    req.target = cap;
    req.inputs["prompt"] = Value::from_string("test");
    ModelResponse resp;
    adapter.handle_call(req, resp);
    CHECK(resp.error_code == 0);
    CHECK(resp.outputs.count("text") > 0);
    std::cout << "PASS: handle_call\n";

    // Test 5: Streaming call
    int chunk_count = 0;
    bool got_end = false;
    adapter.handle_stream(req, [&](const ModelResponse& chunk) -> bool {
        if (chunk.flags.has(AiclFlags::STREAM_END)) {
            got_end = true;
            return false;
        }
        chunk_count++;
        return true;
    });
    CHECK(got_end);
    std::cout << "PASS: handle_stream (" << chunk_count << " chunks)\n";

    // Test 6: Capability query
    auto caps = adapter.advertised_capabilities();
    CHECK(!caps.empty());
    std::cout << "PASS: capabilities (" << caps.size() << ")\n";

    // Test 7: Resource usage
    ResourceUsage usage = adapter.report();
    std::cout << "PASS: report (last_inference=" << usage.last_inference_ms << "ms)\n";

    // Test 8: Buffer registry (zero-copy)
    auto buf = std::make_shared<std::vector<u8>>(std::vector<u8>{1, 2, 3, 4});
    u64 buf_id = adapter.context().buffers().register_buffer(buf);
    CHECK(buf_id != 0);
    const u8* data = adapter.context().buffers().data(buf_id, 0, 4);
    CHECK(data != nullptr);
    CHECK(data[0] == 1);
    std::cout << "PASS: buffer registry\n";

    // Test 9: Shutdown
    adapter.shutdown();
    std::cout << "PASS: shutdown\n";

    std::cout << "\nAll tests passed!\n";
    return 0;
}