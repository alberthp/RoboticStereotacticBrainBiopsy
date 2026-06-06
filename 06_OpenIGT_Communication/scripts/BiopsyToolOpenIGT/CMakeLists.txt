cmake_minimum_required(VERSION 3.20.6...3.22.6 FATAL_ERROR)

project(BiopsyToolOpenIGT)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/BiopsyToolOpenIGT")
set(EXTENSION_CONTRIBUTORS "Albert Hernansanz (Universitat Pompeu Fabra)")
set(EXTENSION_DESCRIPTION "Real-time OpenIGTLink bridge between Slicer and Unity for the robotic stereotactic brain biopsy educational project. Receives the BiopsyTool pose (TRANSFORM) and collision state (STRING) from Unity, and visualises both in real time. Recolours the VirtualFixture model when the tool collides with it.")
set(EXTENSION_ICONURL "https://www.example.com/Slicer/Extensions/BiopsyToolOpenIGT.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/BiopsyToolOpenIGT/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(BiopsyToolOpenIGT)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
