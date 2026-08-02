#!/usr/bin/env python

import argparse
import json
import sys
from pathlib import Path


def make_parser():
    parser = argparse.ArgumentParser(description="Create an animation of var_name in an OpenFOAM case, in .png format")
    parser.add_argument("--case", type=str, default="case", help="OpenFOAM case's `run_dir`ectory")
    parser.add_argument("--fields", type=str, nargs="+", default=None, help="field name to visualize")
    parser.add_argument("--out_dir", type=str, default=None, help="animation output directory, defaults to f'anim_{field}'")
    parser.add_argument("--interactive", action="store_true", help=" VTK's interactive window, use only when running locally")
    parser.add_argument("-i", "--time-index", type=int, default=-1, help="index into the case's write times (default -1 = last; negative counts from the end)")  # dest="time_index"
    parser.add_argument("--camera-json", type=str, default="{}", help="camera configuration")  # dest="camera_json"
    parser.add_argument("--slice-json", type=str, default="{}", help="slice location and orientation")  # dest="slice_json"
    return parser


def main():
    """Create a animation of var_name in an openfoam case, in .png format

    Arguments:
        args:
              same as sys.argv[1:]
    """

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
    renWin.SetAlphaBitPlanes(1)  # Enable usage of alpha channel
    renderer.SetBackground(cg.ImageBackground.red, cg.ImageBackground.green, cg.ImageBackground.blue)
    renderer.SetBackgroundAlpha(cg.ImageBackground.alpha)

    if not args.interactive:
        renWin.SetOffScreenRendering(1)
    renWin.AddRenderer(renderer)

    ofCase = fvk.FoamReader(args.case)
    if not -len(ofCase.times) <= args.time_index < len(ofCase.times):
        parser.error(f"--time-index {args.time_index} out of range, times: {ofCase.times}")
    t = ofCase.times[args.time_index]
    ofCase.set_time(t)

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

    outPath = Path("figs" if not args.out_dir else args.out_dir)
    outPath.mkdir(exist_ok=True)

    fields = args.fields
    if not fields:
        fields = sorted([ii.name for ii in Path(f"{args.case}/{t:g}").glob("*") if ii.is_file()])
        fvk.debug(fields)
        if not fields:
            msg = f"No fields at time {args.case}/{t:g}/"
            raise RuntimeError(msg)

    for field in fields:
        if "phi" in field.lower():
            print(f"{field} skipped, visualizing surfaceFields is not supported")
            continue

        err = fvk.update_pipeline(t, bndryMapr, sliceMapr, scalarBar, ofCase, field, cg, sgs)

        if err:
            print(f"Skipping {field} at time {t}, missing data")
            continue

        outName = f"{outPath}/{field}_{t:g}.png"
        print(f"Writing {outName}")
        fvk.save_screenshot(renWin, outName)

    # not used, interactive visualization
    if args.interactive:
        fvk.interactive_view(renWin)


if __name__ == "__main__":  # local run for testing
    main()
