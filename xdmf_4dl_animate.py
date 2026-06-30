#!/usr/bin/env python3

import argparse
import os
import sys

import imageio
import vtk


def make_parser():
    parser = argparse.ArgumentParser(description="VTK XDMF Animation Generator")
    parser.add_argument("xmf_file", help="Input XMF file path")
    parser.add_argument("var_name", help="Variable name to visualize (e.g. radius)")

    # Optional arguments corresponding to defaults
    parser.add_argument("--xRad", type=float, default=0.5, help="Radius multiplier factor for the lines tube filter")
    parser.add_argument("--zoom", type=float, default=1.1, help="Camera zoom factor")
    parser.add_argument("--doll", type=float, default=1.1, help="Camera dolly factor")
    parser.add_argument("--azim", type=float, default=92.0, help="Camera azimuth angle in degrees")
    parser.add_argument("--roll", type=float, default=-92.0, help="Camera roll angle in degrees")
    parser.add_argument("--pich", type=float, default=0.0, help="Camera pitch angle in degrees")
    parser.add_argument("--elev", type=float, default=0.0, help="Camera elevation angle in degrees")
    parser.add_argument("--yaw", type=float, default=1.0, help="Camera yaw angle in degrees")
    parser.add_argument("--resX", type=int, default=1200, help="Horizontal resolution of the output frame")
    parser.add_argument("--resY", type=int, default=1200, help="Vertical resolution of the output frame")
    parser.add_argument("--hueb", type=float, default=0.55, help="Start hue value for color lookup table")
    parser.add_argument("--hued", type=float, default=0.0, help="End hue value for color lookup table")
    parser.add_argument("--satb", type=float, default=1.0, help="Start saturation value for color lookup table")
    parser.add_argument("--satd", type=float, default=1.0, help="End saturation value for color lookup table")
    parser.add_argument("--valb", type=float, default=1.0, help="Start value (brightness) for color lookup table")
    parser.add_argument("--vald", type=float, default=0.7, help="End value (brightness) for color lookup table")
    parser.add_argument("--alfb", type=float, default=0.2, help="Start alpha (opacity) value for color lookup table")
    parser.add_argument("--alfd", type=float, default=1.0, help="End alpha (opacity) value for color lookup table")
    parser.add_argument("--rngb", type=float, default=1.0, help="Lower value limit for color map scale")
    parser.add_argument("--rngd", type=float, default=0.9, help="Upper value limit for color map scale")
    parser.add_argument("--axOn", type=str, default="F", help="Enable showing axes on viewport ('T' or 'F')")
    parser.add_argument("--brOn", type=str, default="F", help="Enable showing color scalar bar ('T' or 'F')")
    parser.add_argument("--logC", type=str, default="F", help="Use logarithmic scaling for color lookup table ('T' or 'F')")
    parser.add_argument("--intr", type=str, default="F", help="Interpolate scalars before mapping ('T' or 'F')")
    parser.add_argument("--GasO", type=str, default="X", help="Phase color/opacity presets ('G' for Gas, 'O' for Oil, 'X' for None)")

    return parser


def main():
    parser = make_parser()
    args = parser.parse_args()

    xmf_file = args.xmf_file
    var_name = args.var_name

    if not os.path.exists(xmf_file):
        print(f"Error: File '{xmf_file}' does not exist")
        sys.exit(1)

    print(f"Running vtkXdmfAnimate on '{xmf_file}', var: '{var_name}', args: {args}")

    baseName = os.path.splitext(xmf_file)[0]
    out_dir = f"{baseName}_{var_name}_pngs"
    os.makedirs(out_dir, exist_ok=True)
    print(f"outputDir: {out_dir}")

    reader = vtk.vtkXdmfReader()
    reader.SetFileName(xmf_file)
    if not reader.CanReadFile(xmf_file):
        print(f"Error: VTK cannot read '{xmf_file}'")
        sys.exit(1)

    reader.UpdateInformation()

    out_info = reader.GetOutputInformation(0)
    time_key = vtk.vtkStreamingDemandDrivenPipeline.TIME_STEPS()
    if not out_info.Has(time_key):
        print("Error: No time steps found in XDMF file.")
        sys.exit(1)

    time_step_len = out_info.Length(time_key)
    timStps = [out_info.Get(time_key, i) for i in range(time_step_len)]
    print(f"{time_step_len} time steps found.")

    renWin = vtk.vtkRenderWindow()
    renWin.OffScreenRenderingOn()

    png_files = []

    for it in range(time_step_len):
        t_val = timStps[it]
        print(f"timStps_{it}: {t_val}  {{")
        reader.UpdateTimeStep(t_val)
        reader.UpdateInformation()
        reader.Update()

        rOutput = reader.GetOutputDataObject(0)
        ug = vtk.vtkUnstructuredGrid.SafeDownCast(rOutput)
        if not ug:
            mb = vtk.vtkMultiBlockDataSet.SafeDownCast(rOutput)
            if mb:
                ug = mb.GetBlock(0)

        if not ug:
            print("Error: Output could not be cast to unstructured grid.")
            continue

        # Invert z
        transform = vtk.vtkTransform()
        transform.Scale(1.0, 1.0, -1.0)
        transformModel = vtk.vtkTransformFilter()
        transformModel.SetTransform(transform)
        transformModel.SetInputData(ug)

        geometryFilter = vtk.vtkGeometryFilter()
        geometryFilter.SetInputConnection(transformModel.GetOutputPort())
        geometryFilter.Update()

        polyData = geometryFilter.GetOutput()

        polyData.GetPointData().SetActiveScalars("radius")
        scalars_r = polyData.GetPointData().GetScalars("radius")
        if scalars_r:
            r_range = scalars_r.GetRange()
            print(f" R_range: {r_range[0]} {r_range[1]}")
        else:
            print(" R_range: not found")

        # Create a tube (cylinder) around the line
        tubeFilter = vtk.vtkTubeFilter()
        tubeFilter.SetInputData(polyData)
        tubeFilter.SetRadius(0.00005)
        # Set vary radius to absolute scalar
        tubeFilter.SetVaryRadiusToVaryRadiusByAbsoluteScalar()
        tubeFilter.SetNumberOfSides(10)
        tubeFilter.SetRadiusFactor(args.xRad)
        tubeFilter.Update()

        tubePolyData = tubeFilter.GetOutput()
        tubePolyData.GetPointData().SetActiveScalars(var_name)

        scalars_v = polyData.GetPointData().GetScalars(var_name)
        val_range = list(scalars_v.GetRange()) if scalars_v else [0.0, 1.0]
        print(f" {var_name}_range: {val_range[0]} {val_range[1]}")

        if var_name.startswith("f"):  # ffaz
            val_range[0] = max(val_range[0], 0.0)

        # Mappers
        tubeMapper = vtk.vtkPolyDataMapper()
        tubeMapper.SetInputData(tubePolyData)
        tubeMapper.Update()

        linesMapper = vtk.vtkDataSetMapper()
        linesMapper.SetInputData(polyData)
        linesMapper.SetScalarModeToUsePointData()
        linesMapper.Update()

        # Lookup table
        if val_range[1] < val_range[0] + 1e-12:
            val_range[1] = val_range[0] + 1.0

        hueLut = vtk.vtkLookupTable()
        hueLut.SetHueRange(args.hueb, args.hued)
        hueLut.SetSaturationRange(args.satb, args.satd)
        hueLut.SetValueRange(args.valb, args.vald)
        hueLut.SetAlphaRange(args.alfb, args.alfd)

        if args.GasO == "G":
            hueLut.SetHueRange(0.55, 0.1)
            hueLut.SetValueRange(1.0, 1.0)
            hueLut.SetAlphaRange(0.5, 0.3)
            hueLut.SetSaturationRange(0.8, 0.8)
        elif args.GasO == "O":
            hueLut.SetHueRange(0.55, 0.00)
            hueLut.SetSaturationRange(0.8, 1.0)
            hueLut.SetValueRange(1.0, 0.8)
            hueLut.SetAlphaRange(0.4, 0.999)

        hueLut.SetRange(val_range[0], val_range[1])
        hueLut.Build()

        hueLut3 = vtk.vtkLookupTable()
        hueLut3.DeepCopy(hueLut)
        hueLut3.SetRange(val_range[0], val_range[1])
        hueLut3.Build()

        tubeMapper.SelectColorArray(var_name)
        tubeMapper.SetScalarRange(val_range[0], val_range[1])
        tubeMapper.SetScalarModeToUsePointData()
        tubeMapper.SetLookupTable(hueLut)

        # Renderer
        renderer = vtk.vtkRenderer()
        renWin.AddRenderer(renderer)
        renWin.SetAlphaBitPlanes(1)

        tubeActor = vtk.vtkActor()
        tubeActor.GetProperty().SetSpecular(0.999)
        tubeActor.GetProperty().SetSpecularPower(99)
        tubeActor.SetMapper(tubeMapper)
        renderer.AddActor(tubeActor)

        renderer.SetBackground(1.0, 1.0, 1.0)  # White
        renderer.SetUseDepthPeeling(1)
        renderer.SetOcclusionRatio(0.1)
        renderer.SetMaximumNumberOfPeels(50)

        # Camera
        camera = renderer.GetActiveCamera()
        camera.SetRoll(args.roll)
        camera.Pitch(args.pich)
        camera.Yaw(args.yaw)
        renderer.ResetCamera()
        camera.Elevation(args.elev)
        camera.Azimuth(args.azim)
        camera.Zoom(args.zoom)
        camera.Dolly(args.doll)

        renWin.SetSize(int(args.resX), int(args.resY))
        renWin.SetMultiSamples(0)
        renWin.Render()

        # Screenshot frame
        win2img = vtk.vtkWindowToImageFilter()
        win2img.SetInput(renWin)
        win2img.SetInputBufferTypeToRGBA()
        win2img.ReadFrontBufferOff()
        win2img.Update()

        # format filename e.g. 0000.png, 0001.png
        # C++: dir+"/"+_s(10000+timStps[it]).substr(1)+".png"
        padded_num = f"{int(10000 + t_val)}"[1:]
        out_png = os.path.join(out_dir, f"{padded_num}.png")
        print(f" writing: {out_png}")

        writer = vtk.vtkPNGWriter()
        writer.SetFileName(out_png)
        writer.SetInputConnection(win2img.GetOutputPort())
        writer.Write()

        png_files.append(out_png)

        renWin.RemoveRenderer(renderer)
        print("  }")

    # Compile images to video using imageio
    video_out_mp4 = f"{baseName}_{var_name}.mp4"
    video_out_avi = f"{baseName}_{var_name}.avi"
    print(f"Compiling frames to video: {video_out_mp4}")

    # Read generated pngs
    frames = []
    for png in sorted(png_files):
        try:
            frames.append(imageio.v3.imread(png))
        except Exception as e:
            print(f"Failed to read {png}: {e}")

    if frames:
        # Write MP4
        try:
            imageio.v3.imwrite(video_out_mp4, frames, fps=5)
            print(f"wrote {video_out_mp4}")
        except Exception as e:
            print(f"Failed to write MP4: {e}")

        # Write AVI (optional, matching original script)
        try:
            imageio.v3.imwrite(video_out_avi, frames, fps=5)
            print(f"wrote {video_out_avi}")
        except Exception as e:
            print(f"Failed to write AVI: {e}")

    print(f"type:\npngsToVideo {out_dir} {out_dir} 5  # to convert to mp4")


if __name__ == "__main__":
    main()
