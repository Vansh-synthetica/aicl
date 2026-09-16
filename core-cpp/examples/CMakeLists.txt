# Examples CMakeLists.txt
cmake_minimum_required(VERSION 3.20)

# End-to-end demo: AICL instruction -> C++ adapter -> Dummy model -> response
add_executable(aicl_demo
    aicl_demo.cpp
)
target_link_libraries(aicl_demo PRIVATE aicl_core aicl_model_c)
target_include_directories(aicl_demo PRIVATE
    ${CMAKE_SOURCE_DIR}/include
)

# Simple test program
add_executable(aicl_test
    aicl_test.cpp
)
target_link_libraries(aicl_test PRIVATE aicl_core aicl_model_c)
target_include_directories(aicl_test PRIVATE
    ${CMAKE_SOURCE_DIR}/include
# Shared memory transport demo (Process A <-> shared memory <-> Process B)
add_executable(aicl_shm_demo
    aicl_shm_demo.cpp
)
target_link_libraries(aicl_shm_demo PRIVATE aicl_core aicl_model_c)
target_include_directories(aicl_shm_demo PRIVATE
    ${CMAKE_SOURCE_DIR}/include
)
)