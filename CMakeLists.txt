# Require CMake 3.15+ (matching scikit-build-core)
cmake_minimum_required(VERSION 3.15...4.0)

# Disable C++20 module dependency scanning
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Project setup
if(NOT DEFINED SKBUILD_PROJECT_NAME)
  set(SKBUILD_PROJECT_NAME "pnmkit")
endif()
if(NOT DEFINED SKBUILD_PROJECT_VERSION)
  set(SKBUILD_PROJECT_VERSION "0.0.0")
endif()

project(
  ${SKBUILD_PROJECT_NAME}
  VERSION ${SKBUILD_PROJECT_VERSION}
  LANGUAGES CXX)

# Find Python early
find_package(
  Python
  COMPONENTS Interpreter Development.Module
  REQUIRED)

find_package(ZLIB REQUIRED)
find_package(MPI REQUIRED)

# --- Dependencies ---
include(FetchContent)
set(FETCH_LIST "")

# pybind11
find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
  FetchContent_Declare(
    pybind11
    URL https://github.com/pybind/pybind11/archive/refs/tags/v3.0.1.tar.gz)
  list(APPEND FETCH_LIST pybind11)
endif()

# OpenMP
if(APPLE)
  if(NOT DEFINED OpenMP_ROOT AND DEFINED ENV{OpenMP_ROOT})
    set(OpenMP_ROOT $ENV{OpenMP_ROOT})
  endif()
  find_package(OpenMP QUIET)
  if(NOT OpenMP_FOUND)
    set(OpenMP_CXX_FLAGS "-Xpreprocessor -fopenmp")
    find_library(
      OMP_LIB
      NAMES omp
      PATHS "${OpenMP_ROOT}/lib" "/opt/homebrew/opt/libomp/lib"
            "/usr/local/opt/libomp/lib")
    if(OMP_LIB)
      set(OpenMP_FOUND TRUE)
      add_library(OpenMP::OpenMP_CXX UNKNOWN IMPORTED)
      set_target_properties(
        OpenMP::OpenMP_CXX
        PROPERTIES IMPORTED_LOCATION "${OMP_LIB}"
                   INTERFACE_COMPILE_OPTIONS "${OpenMP_CXX_FLAGS}"
                   INTERFACE_LINK_LIBRARIES "${OMP_LIB}")
    endif()
  endif()
endif()
if(NOT OpenMP_FOUND)
  find_package(OpenMP REQUIRED)
endif()

# image3kit (local submodule)
set(image3kit_SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/image3kit)
add_subdirectory(image3kit)

# hypre
set(HYPRE_ENABLE_MPI
    ON
    CACHE BOOL "Build HYPRE with MPI" FORCE)
set(HYPRE_ENABLE_OPENMP
    OFF
    CACHE BOOL "Build HYPRE with OpenMP" FORCE)
FetchContent_Declare(
  hypre
  GIT_REPOSITORY https://github.com/hypre-space/hypre.git
  GIT_TAG 7e403d172640473c07e8391f6a9fb69cd824d48a
  SOURCE_SUBDIR src)
list(APPEND FETCH_LIST hypre)

# Make requested dependencies available
if(FETCH_LIST)
  set(CMAKE_WARN_DEPRECATED
      OFF
      CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(${FETCH_LIST})
  set(CMAKE_WARN_DEPRECATED
      ON
      CACHE BOOL "" FORCE)
endif()

# --- Main Target ---
# --- Source Lists ---
set(COMMON_SOURCES "snm/Xdmf/Xdmf.cpp")

set(PNMKIT_SOURCES "src/main.cpp" "snm/Xdmf/mapDarcy.cpp"
                   "snm/Xdmf/mapImages.cpp" "snm/utils/Input_utils.cpp")

set(SKELOR_SOURCES
    "snm/skelor/MultiNet.cpp"
    "snm/skelor/MultiNet2.cpp"
    "snm/skelor/nextract.cpp"
    "snm/skelor/MedSurf.cpp"
    "snm/skelor/MedSurf2.cpp"
    "snm/skelor/writers_vtk.cpp"
    "snm/skelor/writers_vxl.cpp"
    "snm/skelor/crsMsh.cpp"
    "snm/skelor/voxelImage_inst.cpp"
    "${image3kit_SOURCE_DIR}/src/_voxlib/voxelImage.cpp"
    "${image3kit_SOURCE_DIR}/src/_voxlib/VxlStrips.cpp")

set(SCALOR_SOURCES
    "snm/Xdmf/FlowData.cpp"
    "snm/Xdmf/msflow.cpp"
    "snm/Xdmf/dblWeibCrl.cpp"
    "snm/scalor/flowSim.cpp"
    "snm/scalor/Element.cpp"
    "snm/scalor/FlowMdlIO.cpp"
    "snm/scalor/FlowModel.cpp"
    "snm/scalor/LSolver.cpp"
    "snm/scalor/eCorner.cpp"
    "snm/scalor/elPore.cpp"
    "snm/scalor/elPoreInv.cpp"
    "snm/scalor/elPoreVK.cpp"
    "snm/scalor/elPorous.cpp"
    "snm/scalor/xtra/NetEdit.cpp"
    "snm/scalor/xtra/netStats.cpp"
    "snm/scalor/xtra/vtuWriter.cpp")

# --- Common Config ---
set(PNMKIT_DEFINITIONS
    BildMSM
    BildPNM
    MNFLOW
    SVG
    _extraCompile_
    ZLIB
    OpenMP
    VERSION_INFO=${PROJECT_VERSION})

set(PNMKIT_INCLUDES
    snm/Xdmf
    snm/skelor
    snm/scalor
    snm/scalor/xtra
    ${image3kit_SOURCE_DIR}/src/_include
    ${image3kit_SOURCE_DIR}/src/_voxlib
    ${image3kit_SOURCE_DIR}/src/_vxlToSurf
    ${image3kit_SOURCE_DIR}/src/_vxlToFoam
    ${image3kit_SOURCE_DIR}/pkgs/svplot
    ${image3kit_SOURCE_DIR}/pkgs/stb
    ${image3kit_SOURCE_DIR}/pkgs/zlib)

# --- Python Target ---
python_add_library(
  pnmkit_core
  MODULE
  ${PNMKIT_SOURCES}
  ${COMMON_SOURCES}
  ${SKELOR_SOURCES}
  ${SCALOR_SOURCES}
  WITH_SOABI)
set_target_properties(pnmkit_core PROPERTIES OUTPUT_NAME _pnmkit)
target_include_directories(pnmkit_core PRIVATE ${PNMKIT_INCLUDES})
target_compile_definitions(pnmkit_core PRIVATE ${PNMKIT_DEFINITIONS})
target_link_libraries(
  pnmkit_core
  PRIVATE pybind11::headers
          image3kit_headers
          Python::Module
          OpenMP::OpenMP_CXX
          HYPRE::HYPRE
          ZLIB::ZLIB
          MPI::MPI_CXX)

if(MSVC)
  target_compile_options(pnmkit_core PRIVATE /openmp:llvm /diagnostics:caret
                                             /bigobj)
  target_compile_definitions(pnmkit_core PRIVATE NOMINMAX)
else()
  target_compile_options(pnmkit_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

# --- Standalone Executables ---
add_executable(scalor snm/scalor/main.cpp ${COMMON_SOURCES} ${SCALOR_SOURCES})
target_include_directories(scalor PRIVATE ${PNMKIT_INCLUDES})
target_compile_definitions(scalor PRIVATE ${PNMKIT_DEFINITIONS} MAIN)
target_link_libraries(scalor PRIVATE image3kit_headers OpenMP::OpenMP_CXX
                                     HYPRE::HYPRE ZLIB::ZLIB MPI::MPI_CXX)

add_executable(skelor snm/skelor/main.cpp ${COMMON_SOURCES} ${SKELOR_SOURCES})
target_include_directories(skelor PRIVATE ${PNMKIT_INCLUDES})
target_compile_definitions(skelor PRIVATE ${PNMKIT_DEFINITIONS} MAIN)
target_link_libraries(skelor PRIVATE image3kit_headers OpenMP::OpenMP_CXX
                                     ZLIB::ZLIB)

set_property(TARGET pnmkit_core scalor skelor PROPERTY CXX_STANDARD 23)

if(SKBUILD AND DEFINED SKBUILD_SCRIPTS_DIR)
  set(CMAKE_INSTALL_BINDIR "${SKBUILD_SCRIPTS_DIR}")
endif()

# Installation logic
if(NOT SKBUILD AND CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
  set(CMAKE_INSTALL_PREFIX
      "inst"
      CACHE PATH "..." FORCE)
endif()

add_subdirectory(xpm)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
install(TARGETS scalor skelor xpm RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")

install(TARGETS pnmkit_core DESTINATION pnmkit)
install(DIRECTORY src/pnmkit/ DESTINATION pnmkit)
