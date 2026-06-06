cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

#-----------------------------------------------------------------------------
# Scripted Loadable Module: BiopsyToolOpenIGT
#
# This minimal CMakeLists.txt is sufficient for a Python-only
# Scripted Loadable Module. It declares the module to Slicer's
# build system so that, when bundled as part of a larger extension,
# the .py file is found and registered.
#
# For development you do NOT need to run CMake -- just add this
# folder to "Additional module paths" via Slicer's settings dialog
# and the module will appear under Modules -> IGT -> BiopsyTool
# OpenIGT Bridge after a restart.
#-----------------------------------------------------------------------------

set(MODULE_NAME BiopsyToolOpenIGT)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
)

set(MODULE_PYTHON_RESOURCES
)

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )
