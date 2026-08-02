from __future__ import annotations

import subprocess
import sys
import traceback
from dataclasses import InitVar, astuple, dataclass, field

# pylint: disable=import-error
from pathlib import Path

import vtk


def debug(*args, **kwargs):
    summary = traceback.StackSummary.extract(traceback.walk_stack(None))
    line = summary.format()[1].split("\n")[1]
    print(f'"""{line}""":', *args, **kwargs)
    print(end="", flush=True)


@dataclass
class Float3:
    x: float
    y: float
    z: float

    def __eq__(self, p):
        if isinstance(p, Float3):
            return abs(self.x - p.x) + abs(self.y - p.y) + abs(self.z - p.z) < 3.0e-12
        return False

def _mag(p):
    return (p.x**2 + p.y**2 + p.z**2) ** 0.5


@dataclass
class Range:
    lower: float
    upper: float


@dataclass
class Window:
    width: int
    height: int


@dataclass
class RGBAColor:
    red: float
    green: float
    blue: float
    alpha: float

    def __eq__(self, c):
        if isinstance(c, RGBAColor):
            return abs(self.red - c.red) + abs(self.green - c.green) + abs(self.blue - c.blue) + abs(self.alpha - c.alpha) < 4.0e-3
        return False


def _as(cls, val):
    """Convert a (json) dict to the dataclass `cls`, pass through otherwise"""
    return cls(**val) if isinstance(val, dict) else val


def _clamp01(rng: Range) -> Range:
    return Range(max(0.0, min(rng.lower, 1.0)), max(0.0, min(rng.upper, 1.0)))


@dataclass
class CameraConfig:
    """Camera/colour settings, from --camera-json; missing keys take the defaults below.
    It is easy to get camera config wrong, so __post_init__ does some bound checking too,
    unless AcceptOutOfBounds. `n_slices` (init-only) tunes transparency for slice views.
    """

    # Note: Names get sorted alphabetically in web UI
    AcceptOutOfBounds: bool = False
    # Position: Float3
    # FocalPoint: Float3
    # ViewUp: Float3
    # UseDepthPeeling: int
    # OcclusionRatio: float
    # MaximumNumberOfPeels: int
    # Elevation: float
    # Azimuth: float
    ViewRoll: float = 0.0
    ViewPitch: float = 0.0
    ViewYaw: float = 0.0
    Zoom: float = 1.0
    ColorbarSaturationForScalars: Range = field(default_factory=lambda: Range(0.5, 0.6))  # white==0
    ColorbarSaturationForVectors: Range = field(default_factory=lambda: Range(0.1, 1.0))  # white==0,  (0,1) -> grey-scale@U=0
    ColorbarBrightness: Range = field(default_factory=lambda: Range(1.0, 1.0))  # white/coloured==1.0, black==0
    ColorbarHue: Range = field(default_factory=lambda: Range(0.667, 0.0))  # blue==0.667, red==0.0==1.0
    ColorBySliceRange: bool = False
    ColorInterpolateFields: bool = False
    ImageBackground: RGBAColor = field(default_factory=lambda: RGBAColor(1.0, 1.0, 1.0, 0.0))  # white, transparent
    ImageResolution: Window = field(default_factory=lambda: Window(1440, 1080))
    TransparencyOfBoundary: float = 0.0
    TransparencyOfSlices: float = 0.0

    SlicesWrapFactor: float = 0.0
    SlicesWrapVector: str = ""
    SliceEdgeVisibility: bool = False

    n_slices: InitVar[int] = 0

    def __post_init__(self, n_slices: int):
        self.ColorbarSaturationForScalars = _as(Range, self.ColorbarSaturationForScalars)
        self.ColorbarSaturationForVectors = _as(Range, self.ColorbarSaturationForVectors)
        self.ColorbarBrightness = _as(Range, self.ColorbarBrightness)
        self.ColorbarHue = _as(Range, self.ColorbarHue)
        self.ImageBackground = _as(RGBAColor, self.ImageBackground)
        self.ImageResolution = _as(Window, self.ImageResolution)

        if self.AcceptOutOfBounds:
            return

        if self.Zoom < 1e-3:
            self.Zoom = 1.0
        self.Zoom = max(0.1, min(self.Zoom, 10.0))
        if self.ImageResolution.width == 0 or self.ImageResolution.height == 0:
            self.ImageResolution = Window(1440, 1080)

        self.ColorbarSaturationForScalars = _clamp01(self.ColorbarSaturationForScalars)
        self.ColorbarSaturationForVectors = _clamp01(self.ColorbarSaturationForVectors)
        self.ColorbarBrightness = _clamp01(self.ColorbarBrightness)
        self.ColorbarHue = _clamp01(self.ColorbarHue)

        if n_slices > 0 and self.TransparencyOfSlices == 0.0 and self.TransparencyOfBoundary == 0.0:
            self.TransparencyOfBoundary = 0.8

        # disable workaround config if not visualizing slices
        if n_slices == 0 or self.TransparencyOfSlices > 0.99:
            self.ColorInterpolateFields = True  # disable (hard-code) configuration for 3D boundary


@dataclass
class SliceInfo:
    # Note: Names get sorted alphabetically in web UI
    Normal: Float3 = field(default_factory=lambda: Float3(0.0, 0.0, 1.0))
    Shift: float = 0.0

    def __post_init__(self):
        self.Normal = _as(Float3, self.Normal)
        if _mag(self.Normal) < 0.01:
            self.Normal.z = 1.0


def to_json(rec: any):
    if "to_json" in vars(rec):
        return rec.to_json()
    dic = {}
    for atr in vars(rec):
        getattr(rec, atr)
        dic[atr] = getattr(rec, atr)
    return dic


def run_pyx(command: str, cwd=".") -> None:
    """Run a process and merge stderr into stout
    Arguments:
        command: shell command to run
        cwd: working directory
    Raises:
        subprocess.CalledProcessError
    """
    # cmd = f"xvfb-run -a {sys.executable} {command}"
    cmd = f"xvfb-run -a /usr/bin/python3 {command}"
    print("Running", cmd)
    ret = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in ret.stdout.decode("utf-8").split("\n"):
        print(line)
    print("\n")
    if ret.returncode:
        print(f"'{cmd}' FAILED with return code {ret.returncode}", flush=True)
        sys.exit(ret.returncode)


class FoamReader:
    """Holder for OpenFOAM reader and data for visualization
    Attributes:
        times     OF write times, array of floats
        reader    A vtk.vtkOpenFOAMReader
        polyData  combined reader data (patches and internals)
    """

    def __init__(self, case_dir: str):
        """Read the openfoam case from  the`casePath` folder

        Raises
        ValueError
            If the path is not valid.
        """

        # Check that paths are valid
        if not Path(case_dir).is_dir():
            msg = "Provided path to foam case is invalid!"
            raise ValueError(msg)

        # Case reader
        self.reader = vtk.vtkOpenFOAMReader()
        self.reader.CreateCellToPointOn()
        self.reader.SetFileName(str(case_dir) + "/for_vtk.foam")
        self.reader.Update()

        # combine for rendering all
        self.polyData = vtk.vtkCompositeDataGeometryFilter()
        self.polyData.SetInputConnection(self.reader.GetOutputPort())

        # cache times
        self.times = vtk.util.numpy_support.vtk_to_numpy(self.reader.GetTimeValues())

    def set_time(self, time=None, dataPipeline=None):
        """set Simulation/visualization `time` and update the pipeline"""
        info = self.reader.GetExecutive().GetOutputInformation(0)
        if time is None:
            time = self.times[-1]
        info.Set(vtk.vtkStreamingDemandDrivenPipeline.UPDATE_TIME_STEP(), time)
        # Also update polyData, the rest will be updated automatically by VTK, or shall be passed as dataPipeline
        info = self.polyData.GetExecutive().GetOutputInformation(0)
        info.Set(vtk.vtkStreamingDemandDrivenPipeline.UPDATE_TIME_STEP(), time)

        if dataPipeline:
            dataPipeline.GetExecutive().GetOutputInformation(0).Set(vtk.vtkStreamingDemandDrivenPipeline.UPDATE_TIME_STEP(), time)
            dataPipeline.Update()

    def getTime(self) -> float:
        return self.reader.GetTimeValue()


def save_screenshot(renWin: vtk.vtkRenderWindow, filename: str):
    winToImage = vtk.vtkWindowToImageFilter()
    winToImage.SetInputBufferTypeToRGBA()
    winToImage.SetInput(renWin)
    winToImage.Update()

    writer = vtk.vtkPNGWriter()
    if not filename.endswith(".png"):
        filename = filename + ".png"
    writer.SetFileName(filename)
    writer.SetInputConnection(winToImage.GetOutputPort())
    writer.Write()


def adjust_camera(renderer: vtk.vtkRenderer, cg: CameraConfig):

    renderer.GetActiveCamera().SetPosition(0.0, 0.0, -1.0)
    renderer.GetActiveCamera().SetFocalPoint(0.0, 0.0, 0.0)
    renderer.GetActiveCamera().SetViewUp(0.0, 1.0, 0.0)
    renderer.ResetCamera()

    # Camera movements around camera position: Roll, Elevation, Azimuth
    # Camera movements around focal point: Roll, Pitch and Yaw
    #   y        #  around y: Azimuth / Yaw
    #   |        #
    #   ,---> x  #  around x: Elevation / Pitch
    # z'         #  around z: Roll

    renderer.GetActiveCamera().Roll(cg.ViewRoll)  # in the window
    renderer.GetActiveCamera().Pitch(cg.ViewPitch)  #   vertical cammera rotation, cancelled by OrthogonalizeViewUp
    renderer.GetActiveCamera().Yaw(cg.ViewYaw)
    renderer.ResetCamera()
    renderer.GetActiveCamera().Zoom(cg.Zoom)


def apply_filters(ofCase: FoamReader, scg: list[SliceInfo], cg: CameraConfig | None):

    # from vtkmodules.vtkRenderingCore import vtkDataSetMapper
    domain: vtk.vtkPolyData = ofCase.reader.GetOutput().GetBlock(0)

    # Get the extent of the data: imin,imax, jmin,jmax, kmin,kmax
    xt = domain.GetBounds()
    ct = domain.GetCenter()
    debug(domain.GetCenter())
    debug(domain.GetBounds())

    scalarRange = domain.GetScalarRange()
    debug(scalarRange)

    appendF = vtk.vtkAppendPolyData()  # see https://examples.vtk.org/site/Python/VisualizationAlgorithms/VelocityProfile/
    for sg in scg:  # loop over slices
        print("slice info:", sg)

        s = sg.Shift / _mag(sg.Normal)
        x, y, z = astuple(sg.Normal)
        x *= s
        y *= s
        z *= s
        Dx, Dy, Dz = xt[1] - xt[0], xt[3] - xt[2], xt[5] - xt[4]
        Ox, Oy, Oz = s * Dx + ct[0], s * Dy + ct[1], s * Dz + ct[2]
        print("slice Origin:", Ox, Oy, Oz)

        assert Dx > 0
        debug(x, y, z)
        assert x > -0.6 and x < 0.6 and y > -0.6 and y < 0.6 and z > -0.6 and z < 0.6, "Wrong slice Shift, shall be between -0.5 and 0.5"
        plane = vtk.vtkPlane()
        plane.SetOrigin(Ox, Oy, Oz)
        plane.SetNormal(*astuple(sg.Normal))

        # create clipper
        # clipper = vtk.vtkTableBasedClipDataSet()
        # clipper.SetClipFunction(plane)
        # clipper.SetInputData(pl3dOutput)
        # clipper.SetValue(0.0)
        # clipper.GenerateClippedOutputOn()
        # clipper.GenerateClipScalarsOn()
        # # clipper.InsideOutOn()
        # clipper.Update()

        clipper = vtk.vtkCompositeCutter()  # vtkCutter?
        clipper.SetCutFunction(plane)
        clipper.GenerateCutScalarsOn()
        clipper.GenerateTrianglesOn()
        clipper.SetInputData(domain)
        clipper.Update()

        appendF.AddInputData(clipper.GetOutput())
    all = appendF

    if cg and cg.SlicesWrapVector and cg.SlicesWrapFactor > 0.0:  # Warp
        warp = vtk.vtkWarpVector()
        warp.SetInputData(appendF.GetOutput())
        warp.SetScaleFactor(cg.SlicesWrapFactor)
        # https://stackoverflow.com/a/29946307
        warp.SetInputArrayToProcess(1, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, cg.SlicesWrapVector)
        appendF.Update()
        warp.Update()
        debug(warp.GetOutput())

        all = vtk.vtkPolyDataNormals()
        all.SetInputData(warp.GetPolyDataOutput())
        # all = warp

    all.Update()

    return all.GetOutput()


def get_field_info(dataSet: vtk.vtkDataSet, field: str, component: int = -1):
    """ "Scrupulous way of getting a variable range, to help avoid clutter"""
    for data in [dataSet.GetCellData(), dataSet.GetPointData()]:
        if data:
            vals = data.GetVectors(field)
            if vals and vals.GetName() == field and vals.GetNumberOfComponents() == 3:
                return {"type": "vector", "range": vals.GetRange(component)}
            vals = data.GetScalars(field)
            if vals and vals.GetName() == field:
                return {"type": "scalar", "range": vals.GetRange()}
    return None


def set_colorbar_get_info(scalarBar: vtk.vtkScalarBarActor, input: vtk.vtkPolyData, lut: vtk.vtkLookupTable, field: str, cg: CameraConfig, component: int = -1):
    # see https://www.compilatrix.com/docs/vtk-lookup-tables

    # Share the lookup table between the mapper and the scalarbar
    # See https://examples.vtk.org/site/Python/Rendering/Rainbow/

    fieldInfo = get_field_info(input, field, component)  # hoping block 0 is internalCells !
    debug(field, fieldInfo)

    if fieldInfo is not None:
        lut.SetRange(*fieldInfo["range"])

    lut.SetValueRange(*astuple(cg.ColorbarBrightness))  # 0.0 -> black
    lut.SetHueRange(*astuple(cg.ColorbarHue))  # blue==0.667, red==0.0==1.0
    if fieldInfo and fieldInfo["type"] == "vector" and component == -1:  # vector magnitudes cannot be negative, use a different color scheme!
        lut.SetSaturationRange(*astuple(cg.ColorbarSaturationForVectors))  # (0.0, 1.0) #  Partial grey-scale (white==0)
    else:
        lut.SetSaturationRange(*astuple(cg.ColorbarSaturationForScalars))  # (0.5, 0.6) # white==0
    lut.Build()

    scalarBar.SetLookupTable(lut)
    scalarBar.SetTitle(field.ljust(10))  # ljust adjusts font size !
    scalarBar.GetTitleTextProperty().SetColor(0.0, 0.0, 0.0)
    scalarBar.GetLabelTextProperty().SetColor(0.0, 0.0, 0.0)

    scalarBar.SetNumberOfLabels(5)
    coord = scalarBar.GetPositionCoordinate()
    coord.SetCoordinateSystemToNormalizedViewport()
    coord.SetValue(0.9, 0.25)
    scalarBar.SetWidth(0.09)
    scalarBar.SetHeight(0.5)

    return fieldInfo


def update_pipeline(
    time: float,
    bndryMapr: vtk.vtkPolyDataMapper,
    sliceMapr: vtk.vtkPolyDataMapper,
    scalarBar: vtk.vtkScalarBarActor,
    ofCase: FoamReader,
    field: str,
    cg: CameraConfig,
    sgs: list[SliceInfo],
) -> bool:
    """Update the pipeline: boundary, slices and color bar
    return True if update is successful
    """

    bndryMapr.SetInputConnection(ofCase.polyData.GetOutputPort())  # affect camera
    sliceMapr.SelectColorArray(field)
    bndryMapr.SelectColorArray(field)

    ofCase.set_time(time)  # just updates the pipeline
    filtData = apply_filters(ofCase, sgs, cg)

    sliceMapr.SetInputData(filtData)

    bndryMapr.SetInputConnection(ofCase.polyData.GetOutputPort())  # affect camera

    lutInput: vtk.vtkPolyData = (
        sliceMapr.GetInput() if cg.ColorBySliceRange else bndryMapr.GetInputDataObject(0, 0)
    )  # or ofCase.reader.GetInputDataObject(0,0).GetBlock(0)

    lut: vtk.vtkLookupTable = sliceMapr.GetLookupTable()
    fieldInfo = set_colorbar_get_info(scalarBar, lutInput, lut, field, cg)
    # bndryMapr.SetInputConnection(ofCase.polyData.GetOutputPort()) # affect camera
    bndryMapr.SetLookupTable(lut)

    return fieldInfo is None


def interactive_view(renWin: vtk.vtkRenderWindow):
    """Open an interactive Window, to help adjust the camera"""
    iren = vtk.vtkRenderWindowInteractor()
    iren.SetRenderWindow(renWin)

    style = vtk.vtkInteractorStyleTrackballCamera()
    iren.SetInteractorStyle(style)

    iren.Initialize()
    iren.Start()
