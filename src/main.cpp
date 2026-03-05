#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <pybind11/pytypes.h>
#include <vector>
#include <string>
#include <cstring>
#include <utility>
#include <memory>

#include <globals.h>
#include "InputFile.h"
#include "Xdmf.h"
#include "msflow.h"
#include "voxelImage.h"
#include "bind_common.hpp"

using VxlPy::pyCastInput;

int mextract(const voxelImage& VImage, const InputFile& inp, bool verbose);
bool DictCompare(std::string dic1Nam, std::string dic2Nam, int sever = 1, std::string ignor = "");

namespace py = pybind11;

int mextract_wrapped(py::object image, py::dict inp_obj, bool verbose) {
    // image can be Path, str or voxelImage
    InputFile inp = pyCastInput(inp_obj);
    inp.initIO();
    try {
        const voxelImage& VImage = image.cast<const voxelImage&>();
        return mextract(VImage, inp, verbose);
    } catch (const py::cast_error&) {
        // Automatically convert pathlib.Path or other str-convertible objects
        std::string img_path = py::str(image).cast<std::string>();
        voxelImage VImage(img_path, readOpt::procAndConvert);
        return mextract(VImage, inp, verbose);
    }
}

Xdml runXcanStages(py::dict inp_obj)  {
    InputFile inp_cpy = pyCastInput(inp_obj);
    inp_cpy.initIO();
    Xdml xdmfl("");
    std::string ntf = inp_cpy.getOr("networkFile", std::string("_.msm"));
    if(hasExt(ntf,".msm") || hasExt(ntf,"_ms.xmf") || ntf.substr(0,12)=="synthetizeNet_") {
        #ifdef BildMSM
        auto ret =  runWettabilityScanStages(inp_cpy, snflowQD);
        if(ret) return ::std::move(*ret);
        #endif //BildMSM
        alert(".msm network format is not available in this version.",-1);
    }
    else {
        #ifdef BildPNM
        // return   runWettabilityScanStages(inp_cpy, cnflowQD);
        #endif //BildPNM
        alert("cnflow is not available here, please contact us if you need it...",-1);
    }
    return xdmfl;
}

PYBIND11_MODULE(_pnmkit, m, py::mod_gil_not_used(), py::multiple_interpreters::per_interpreter_gil()) {
    m.doc() = R"pbdoc(
        pnmkit network extraction and simulation
        ---------------------------------------

        .. currentmodule:: pnmkit

        .. autosummary::
           :toctree: _generate

           Input, shared with image3kit
           mextract
           snflow
    )pbdoc";

    // Reuse InputFile from image3kit
    auto sirun = py::module_::import("image3kit._core.sirun");
    m.attr("Input") = sirun.attr("Input");

    m.def("mextract", &mextract_wrapped, "Extract network from voxelImage or filename",
          py::arg("image"), py::arg("config")=py::dict(), py::arg("verbose") = false);

    m.def("snflow", [](py::dict inp) { return runXcanStages(inp); }, "Run network model stages", py::arg("inp"));


    m.def("DictCompare", &DictCompare, "Compare two input files",
          py::arg("dic1Nam"), py::arg("dic2Nam"), py::arg("sever") = 1, py::arg("ignor") = "");

    py::class_<stepData>(m, "stepData")

        .def_property_readonly("nodeData_", [](const stepData& self) {
            py::object self_obj = py::cast(&self);
            py::dict d;
            for (const auto& [k, v] : self.nodeData_) {
                pybind11::ssize_t n = static_cast<pybind11::ssize_t>(v.size());
                std::vector<pybind11::ssize_t> shape = {n};
                std::vector<pybind11::ssize_t> strides = {static_cast<pybind11::ssize_t>(sizeof(float))};
                d[k.c_str()] = py::array_t<float>(shape, strides, v.data(), self_obj);
            }
            return d;
        })
        .def_property_readonly("nodeDataI_", [](const stepData& self) {
            py::object self_obj = py::cast(&self);
            py::dict d;
            for (const auto& [k, v] : self.nodeDataI_) {
                pybind11::ssize_t n = static_cast<pybind11::ssize_t>(v.size());
                std::vector<pybind11::ssize_t> shape = {n};
                std::vector<pybind11::ssize_t> strides = {static_cast<pybind11::ssize_t>(sizeof(int))};
                d[k.c_str()] = py::array_t<int>(shape, strides, v.data(), self_obj);
            }
            return d;
        })
        .def_property_readonly("nodeData3_", [](const stepData& self) {
            py::object self_obj = py::cast(&self);
            py::dict d;
            for (const auto& [k, v] : self.nodeData3_) {
                pybind11::ssize_t n = static_cast<pybind11::ssize_t>(v.size());
                std::vector<pybind11::ssize_t> shape = {n, 3};
                std::vector<pybind11::ssize_t> strides = {static_cast<pybind11::ssize_t>(sizeof(v[0])), static_cast<pybind11::ssize_t>(sizeof(float))};
                const float* p = n > 0 ? &v[0].x : nullptr;
                d[k.c_str()] = py::array_t<float>(shape, strides, p, self_obj);
            }
            return d;
        })
        .def_property_readonly("elemData_", [](const stepData& self) {
            py::object self_obj = py::cast(&self);
            py::dict d;
            for (const auto& [k, v] : self.elemData_) {
                pybind11::ssize_t n = static_cast<pybind11::ssize_t>(v.size());
                std::vector<pybind11::ssize_t> shape = {n};
                std::vector<pybind11::ssize_t> strides = {static_cast<pybind11::ssize_t>(sizeof(float))};
                d[k.c_str()] = py::array_t<float>(shape, strides, v.data(), self_obj);
            }
            return d;
        })
        .def_property_readonly("elemDataI_", [](const stepData& self) {
            py::object self_obj = py::cast(&self);
            py::dict d;
            for (const auto& [k, v] : self.elemDataI_) {
                pybind11::ssize_t n = static_cast<pybind11::ssize_t>(v.size());
                std::vector<pybind11::ssize_t> shape = {n};
                std::vector<pybind11::ssize_t> strides = {static_cast<pybind11::ssize_t>(sizeof(int))};
                d[k.c_str()] = py::array_t<int>(shape, strides, v.data(), self_obj);
            }
            return d;
        })
        .def_property_readonly("elemData3_", [](const stepData& self) {
            py::object self_obj = py::cast(&self);
            py::dict d;
            for (const auto& [k, v] : self.elemData3_) {
                pybind11::ssize_t n = static_cast<pybind11::ssize_t>(v.size());
                std::vector<pybind11::ssize_t> shape = {n, 3};
                std::vector<pybind11::ssize_t> strides = {static_cast<pybind11::ssize_t>(sizeof(v[0])), static_cast<pybind11::ssize_t>(sizeof(float))};
                const float* p = n > 0 ? &v[0].x : nullptr;
                d[k.c_str()] = py::array_t<float>(shape, strides, p, self_obj);
            }
            return d;
        });

    py::class_<Xdmf>(m, "Xdmf")
        .def(py::init<std::string, std::string>())
        .def("writeAll", &Xdmf::writeAll)
        .def("readXmf", &Xdmf::readXmf)
        .def("__getitem__", [](const Xdmf& self, int icycle) { return self[icycle]; }, py::return_value_policy::reference_internal);

    py::class_<Xdml, Xdmf>(m, "Xdml")
        .def(py::init<std::string>());

#ifdef VERSION_INFO
    m.attr("__version__") = TOSTRING(VERSION_INFO);
#else
    m.attr("__version__") = "dev";
#endif
}
