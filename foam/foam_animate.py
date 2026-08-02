#!/usr/bin/env python

import argparse
import sys
from pathlib import Path


def make_parser():
    parser = argparse.ArgumentParser(description="Create a animation of var_name in an openfoam case, in .png format")
    parser.add_argument("--case", type=str, default="case", help="OpenFOAM case's `run_dir`ectory")
    parser.add_argument("--fields", type=str, nargs="+", default=["p"], help="field name to visualize")
    parser.add_argument("--out_dir", type=str, default=None, help="animation output directory, defaults to f'anim_{field}'")
    parser.add_argument("--interactive", action="store_true", help=" VTK's interactive window, use only when running locally")
    parser.add_argument(
        "-b",
        "--begin-time",
        type=float,
        default=-sys.float_info.max,  # target="begin_time"
        help="first time step to visualize",
    )
    parser.add_argument(
        "-e",
        "--end-time",
        type=float,
        default=sys.float_info.max,  # target="end_time"
        help="last time step to visualize",
    )
    parser.add_argument(
        "--camera-json",
        type=str,
        default="{}",  # target="camera_json"
        help="camera configuration",
    )
    parser.add_argument(
        "--slice-json",
        type=str,
        default="{}",  # target="slice_json"
        help="slice location and orientation",
    )
    return parser


def main():
    """Create a animation of var_name in an openfoam case, in .png format

    Arguments:
        args:
              same as sys.argv[1:]
    """
    import json

    import vtk

    try:
        import utils_foamvtk as fvk
    except ImportError:
        from . import utils_foamvtk as fvk
    parser = make_parser()
    args = parser.parse_args(sys.argv[1:])

    fvk.debug(args)

    sgs = [fvk.SliceInfo(**sg) for sg in json.loads(args.slice_json)]
    fvk.debug(sgs)

    cg = fvk.CameraConfig(**json.loads(args.camera_json), n_slices=len(sgs))
    fvk.debug(cg)

    renderer = vtk.vtkRenderer()
    renWin = vtk.vtkRenderWindow()
    renWin.SetAlphaBitPlanes(1)  # Enable alpha channel
    renderer.SetBackground(cg.ImageBackground.red, cg.ImageBackground.green, cg.ImageBackground.blue)
    renderer.SetBackgroundAlpha(cg.ImageBackground.alpha)

    if not args.interactive:
        renWin.SetOffScreenRendering(1)
    renWin.AddRenderer(renderer)

    ofCase = fvk.FoamReader(args.case)
    ofCase.set_time(time=None)

    # Add (Ghost of) original geometry
    bndryMapr = vtk.vtkPolyDataMapper()
    bndryMapr.SetInputConnection(ofCase.boundaryData.GetOutputPort())  # affect camera
    bndryMapr.SetUseLookupTableScalarRange(1)
    gostActor = vtk.vtkActor()
    gostActor.SetMapper(bndryMapr)
    gostActor.GetProperty().SetOpacity(1.0 - cg.TransparencyOfBoundary)
    renderer.AddActor(gostActor)

    # mapper, from ofCase combined filtered data to screen!
    sliceMapr = vtk.vtkPolyDataMapper()
    # sliceMapr.SetInputConnection(ofCase.polyData.GetOutputPort())
    sliceMapr.InterpolateScalarsBeforeMappingOn()
    sliceMapr.SetUseLookupTableScalarRange(1)  # to build the lookup table (lut)

    if cg.ColorInterpolateFields:
        bndryMapr.SetScalarModeToUsePointFieldData()
        sliceMapr.SetScalarModeToUsePointFieldData()
    else:
        bndryMapr.SetScalarModeToUseCellFieldData()
        sliceMapr.SetScalarModeToUseCellFieldData()

    actor = vtk.vtkActor()
    actor.SetMapper(sliceMapr)
    actor.GetProperty().SetOpacity(1.0 - cg.TransparencyOfSlices)
    renderer.AddActor(actor)

    if cg.SliceEdgeVisibility:
        actor.GetProperty().SetRepresentationToSurface()
        actor.GetProperty().EdgeVisibilityOn()
        actor.GetProperty().SetEdgeColor(0, 0, 0)

    # Visualize a color bar
    scalarBar = vtk.vtkScalarBarActor()
    renderer.AddActor2D(scalarBar)

    sliceMapr.SetInputData(fvk.apply_filters(ofCase, sgs, None))  # to adjust camera
    fvk.adjust_camera(renderer, cg)

    renWin.SetSize(*fvk.astuple(cg.ImageResolution))
    renWin.SetMultiSamples(0)
    renWin.SetAlphaBitPlanes(1)

    print(f"### Time loop: [0,{len(ofCase.times)})")
    for t in ofCase.times:
        if args.begin_time > t or t > args.end_time:
            continue
        for field in args.fields:
            err = fvk.update_pipeline(t, bndryMapr, sliceMapr, scalarBar, ofCase, field, cg, sgs)

            if err:
                print(f"Skipping {field} at time {t}, missing data")
                continue

            outPath = Path(f"anim_{field}" if not args.out_dir else args.out_dir)
            outPath.mkdir(exist_ok=True)
            outName = f"{outPath}/{field}_{t}.png"
            print(f"Writing {outName}")
            fvk.save_screenshot(renWin, outName)

    # not used, interactive visualization
    if args.interactive:
        fvk.interactive_view(renWin)


if __name__ == "__main__":  # local run for testing
    main()
