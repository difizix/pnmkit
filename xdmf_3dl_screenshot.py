#!/usr/bin/env python3
import argparse
import os
import sys

import numpy as np
import vtk
from vtk.util import numpy_support


def make_parser():
    parser = argparse.ArgumentParser(description="VTK XDMF Screenshot Generator")
    parser.add_argument("xmf_file", help="Input XMF file path")
    parser.add_argument("var_name", help="Variable name to visualize (e.g. radius)")

    # Optional arguments corresponding to defaults
    parser.add_argument("--xRad", type=float, default=0.5, help="Radius multiplier factor for the lines tube filter")
    parser.add_argument("--zoom", type=float, default=1.05, help="Camera zoom factor")
    parser.add_argument("--doll", type=float, default=1.1, help="Camera dolly factor")
    parser.add_argument("--azim", type=float, default=91.0, help="Camera azimuth angle in degrees")
    parser.add_argument("--roll", type=float, default=-91.0, help="Camera roll angle in degrees")
    parser.add_argument("--pich", type=float, default=0.0, help="Camera pitch angle in degrees")
    parser.add_argument("--elev", type=float, default=0.0, help="Camera elevation angle in degrees")
    parser.add_argument("--yaw", type=float, default=1.0, help="Camera yaw angle in degrees")
    parser.add_argument("--resX", type=int, default=1440, help="Horizontal resolution of the output image")
    parser.add_argument("--resY", type=int, default=1440, help="Vertical resolution of the output image")
    parser.add_argument("--hueb", type=float, default=0.7, help="Start hue value for color lookup table")
    parser.add_argument("--hued", type=float, default=0.0, help="End hue value for color lookup table")
    parser.add_argument("--satb", type=float, default=0.7, help="Start saturation value for color lookup table")
    parser.add_argument("--satd", type=float, default=1.0, help="End saturation value for color lookup table")
    parser.add_argument("--valb", type=float, default=1.0, help="Start value (brightness) for color lookup table")
    parser.add_argument("--vald", type=float, default=0.9, help="End value (brightness) for color lookup table")
    parser.add_argument("--rngb", type=float, default=1.0, help="Lower value limit for color map scale")
    parser.add_argument("--rngd", type=float, default=0.9, help="Upper value limit for color map scale")
    parser.add_argument("--trsh", type=float, default=-1e32, help="Upper threshold value for filtering cells by radius")
    parser.add_argument("--axOn", type=str, default="F", help="Enable showing axes on viewport ('T' or 'F')")
    parser.add_argument("--brOn", type=str, default="F", help="Enable showing color scalar bar ('T' or 'F')")
    parser.add_argument("--logC", type=str, default="F", help="Use logarithmic scaling for color lookup table ('T' or 'F')")
    parser.add_argument("--intr", type=str, default="F", help="Interpolate scalars before mapping ('T' or 'F')")
    parser.add_argument("--outg", type=str, default="", help="Output filename suffix")

    return parser


def main():
    parser = make_parser()
    args = parser.parse_args()

    xmf_file = args.xmf_file
    var_name = args.var_name

    if not os.path.exists(xmf_file):
        print(f"Error: File '{xmf_file}' does not exist")
        sys.exit(1)

    print(f"Running vtkXdmfScreenshot on '{xmf_file}', var: '{var_name}', args: {args}")

    reader = vtk.vtkXdmfReader()
    reader.SetFileName(xmf_file)
    if not reader.CanReadFile(xmf_file):
        print(f"Error: VTK cannot read '{xmf_file}'")
        sys.exit(1)

    reader.UpdateInformation()
    reader.UpdateTimeStep(1.0)
    reader.Update()

    rOutput = reader.GetOutputDataObject(0)
    ug = vtk.vtkUnstructuredGrid.SafeDownCast(rOutput)
    if not ug:
        mb = vtk.vtkMultiBlockDataSet.SafeDownCast(rOutput)
        if mb:
            ug = mb.GetBlock(0)

    if not ug:
        print("Error: Output could not be cast to unstructured grid.")
        sys.exit(1)

    if xmf_file.endswith("_pn.xmf"):
        # Create an explicit index array for points (nodes)
        num_points = ug.GetNumberOfPoints()
        np_indices = np.arange(num_points, dtype=np.int32)
        index_array = numpy_support.numpy_to_vtk(num_array=np_indices, deep=True, array_type=vtk.VTK_INT)
        index_array.SetName("index")
        ug.GetPointData().AddArray(index_array)

        # Trim inlet/outlet (side) boundary nodes
        trimedBSides = vtk.vtkThreshold()
        trimedBSides.SetInputData(ug)
        trimedBSides.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_UPPER)
        trimedBSides.SetUpperThreshold(6)
        trimedBSides.SetAllScalars(True)
        trimedBSides.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, "index")
        trimedBSides.Update()
    else:
        trimedBSides = ug

    # Thresholding cells by radius
    selectCells = vtk.vtkThreshold()
    selectCells.SetInputData(trimedBSides.GetOutput())
    selectCells.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_UPPER)
    selectCells.SetUpperThreshold(args.trsh)
    selectCells.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, "radius")
    selectCells.Update()

    geometryFilter = vtk.vtkGeometryFilter()
    geometryFilter.SetInputData(selectCells.GetOutput())
    geometryFilter.Update()

    polyData = geometryFilter.GetOutput()
    bounds = polyData.GetBounds()
    print(f" Bounding Box: X:[{bounds[0]:.3f}, {bounds[1]:.3f}] Y:[{bounds[2]:.3f}, {bounds[3]:.3f}] Z:[{bounds[4]:.3f}, {bounds[5]:.3f}]")

    scalars_r = polyData.GetPointData().GetScalars("radius")
    if scalars_r:
        print(f" R_range: {scalars_r.GetRange()[0]} {scalars_r.GetRange()[1]}")

        # vtkTubeFilter with VaryRadiusByAbsoluteScalar uses active scalars.
        # Scale the radius array by args.xRad for the tube thickness.
        scaled_radius = vtk.vtkFloatArray()
        scaled_radius.SetName("tube_radius")
        for i in range(scalars_r.GetNumberOfTuples()):
            scaled_radius.InsertNextValue(scalars_r.GetValue(i) * args.xRad)
        polyData.GetPointData().AddArray(scaled_radius)
        polyData.GetPointData().SetActiveScalars("tube_radius")

    # Create tube filter
    tubeFilter = vtk.vtkTubeFilter()
    tubeFilter.SetInputData(polyData)
    tubeFilter.SetRadius(0.00005)
    tubeFilter.SetNumberOfSides(10)
    tubeFilter.SetVaryRadiusToVaryRadiusByAbsoluteScalar()
    tubeFilter.Update()

    tubePolyData = tubeFilter.GetOutput()
    tubePolyData.GetPointData().SetActiveScalars(var_name)

    scalars_v = polyData.GetPointData().GetScalars(var_name)
    val_range = list(scalars_v.GetRange()) if scalars_v else [0.0, 1.0]

    if args.rngb < args.rngd:
        val_range[0] = args.rngb
        val_range[1] = args.rngd

    print(f" {val_range[0]} <range of {var_name}> {val_range[1]}")

    # Lookup table setup
    hueLut = vtk.vtkLookupTable()
    hueLut.SetHueRange(args.hueb, args.hued)
    hueLut.SetSaturationRange(args.satb, args.satd)
    hueLut.SetValueRange(args.valb, args.vald)
    if args.logC == "T":
        val_range[0] = max(1e-4 * val_range[1], val_range[0])
        hueLut.SetScaleToLog10()
    hueLut.SetRange(val_range[0], val_range[1])
    hueLut.Build()

    hueLut3 = vtk.vtkLookupTable()
    hueLut3.DeepCopy(hueLut)
    if args.logC == "T":
        hueLut3.SetScaleToLog10()
    hueLut3.SetRange(val_range[0], val_range[1])
    hueLut3.Build()

    # Mappers
    linesMapper = vtk.vtkDataSetMapper()
    linesMapper.SetInputData(polyData)
    linesMapper.SetScalarModeToUsePointData()
    linesMapper.SelectColorArray(var_name)
    linesMapper.SetScalarRange(val_range[0], val_range[1])
    linesMapper.SetInterpolateScalarsBeforeMapping(args.intr == "T")
    linesMapper.SetLookupTable(hueLut3)

    tubeMapper = vtk.vtkPolyDataMapper()
    tubeMapper.SetInputData(tubePolyData)
    tubeMapper.SetScalarModeToUsePointData()
    tubeMapper.SelectColorArray(var_name)
    tubeMapper.SetScalarRange(val_range[0], val_range[1])
    tubeMapper.SetInterpolateScalarsBeforeMapping(args.intr == "T")
    tubeMapper.SetLookupTable(hueLut)

    # Actors
    tubeActor = vtk.vtkActor()
    tubeActor.SetMapper(tubeMapper)

    # Scalar Bar
    scalarBar = vtk.vtkScalarBarActor()
    scalarBar.SetNumberOfLabels(4)
    scalarBar.SetLookupTable(hueLut)
    scalarBar.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
    scalarBar.SetTitle(var_name)
    scalarBar.SetTextPositionToSucceedScalarBar()
    scalarBar.SetOrientationToHorizontal()
    scalarBar.GetPositionCoordinate().SetValue(0.3, 0.935)
    scalarBar.SetWidth(0.4)
    scalarBar.SetHeight(0.06)
    scalarBar.SetTextPad(2)
    scalarBar.GetTitleTextProperty().SetColor(0.4, 0.4, 0.4)
    scalarBar.GetTitleTextProperty().SetFontSize(int((16 * min(args.resX, args.resY)) / 720))
    scalarBar.GetLabelTextProperty().SetColor(0.4, 0.4, 0.4)
    scalarBar.GetLabelTextProperty().SetFontSize(int((14 * min(args.resX, args.resY)) / 720))
    scalarBar.SetUnconstrainedFontSize(True)

    # Renderer setup
    renderer = vtk.vtkRenderer()
    renderer.AddActor(tubeActor)
    renderer.AddActor2D(scalarBar)

    # Cube axes actor
    if args.axOn in ("t", "T"):
        cubeAxesActor = vtk.vtkCubeAxesActor()
        cubeAxesActor.SetBounds(tubeMapper.GetBounds())
        cubeAxesActor.SetCamera(renderer.GetActiveCamera())
        cubeAxesActor.SetScreenSize(18)
        cubeAxesActor.SetXTitle("X")
        cubeAxesActor.SetXUnits("m")
        cubeAxesActor.SetYTitle("Y")
        cubeAxesActor.SetYUnits("m")
        cubeAxesActor.SetZTitle("Z")
        cubeAxesActor.SetZUnits("m")
        cubeAxesActor.SetTickLocationToOutside()

        for i in range(3):
            cubeAxesActor.GetTitleTextProperty(i).SetColor(0.2, 0.2, 0.2)
            cubeAxesActor.GetLabelTextProperty(i).SetColor(0.2, 0.2, 0.2)
        cubeAxesActor.GetXAxesLinesProperty().SetColor(0.2, 0.2, 0.2)
        cubeAxesActor.GetYAxesLinesProperty().SetColor(0.2, 0.2, 0.2)
        cubeAxesActor.GetZAxesLinesProperty().SetColor(0.2, 0.2, 0.2)

        cubeAxesActor.GetXAxesLinesProperty().SetLineWidth(2)
        cubeAxesActor.GetYAxesLinesProperty().SetLineWidth(2)
        cubeAxesActor.GetZAxesLinesProperty().SetLineWidth(2)
        cubeAxesActor.SetLabelScaling(True, 6, 6, 6)

        cubeAxesActor.SetGridLineLocation(cubeAxesActor.VTK_GRID_LINES_FURTHEST if hasattr(cubeAxesActor, "VTK_GRID_LINES_FURTHEST") else 0)
        cubeAxesActor.XAxisMinorTickVisibilityOff()
        cubeAxesActor.YAxisMinorTickVisibilityOff()
        cubeAxesActor.ZAxisMinorTickVisibilityOff()
        cubeAxesActor.SetFlyModeToOuterEdges()
        renderer.AddActor(cubeAxesActor)

    renderer.SetBackground(1.0, 1.0, 1.0)  # White

    # Render Window
    renWin = vtk.vtkRenderWindow()
    renWin.OffScreenRenderingOn()
    renWin.AddRenderer(renderer)
    renWin.SetAlphaBitPlanes(1)

    camera = renderer.GetActiveCamera()
    camera.SetRoll(args.roll)
    camera.Azimuth(args.azim)
    camera.Pitch(args.pich)
    camera.Elevation(args.elev)
    renderer.ResetCamera()
    camera.Yaw(args.yaw)
    camera.Zoom(args.zoom)
    camera.Dolly(args.doll)

    renderer.ResetCameraClippingRange()

    renWin.SetSize(int(args.resX), int(args.resY))
    renWin.Render()

    # Image conversion
    win2img = vtk.vtkWindowToImageFilter()
    win2img.SetInput(renWin)
    win2img.SetInputBufferTypeToRGBA()
    win2img.ReadFrontBufferOff()
    win2img.Update()

    fnam = os.path.splitext(xmf_file)[0]
    out_png = f"{fnam}_{var_name}{args.outg}.png"

    writer = vtk.vtkPNGWriter()
    writer.SetFileName(out_png)
    writer.SetInputConnection(win2img.GetOutputPort())
    writer.Write()
    print(f"wrote {out_png}")


if __name__ == "__main__":
    main()
