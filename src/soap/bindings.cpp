#include "bindings.hpp"
#include "coulomb.hpp"
#include "fieldtensor.hpp"
#include "npfga.hpp"
#include "kernel.hpp"
#include "dmap.hpp"
#include "cgraph.hpp"

namespace soap {

}

BOOST_PYTHON_MODULE(_soapxx)
{
    using namespace boost::python;

    soap::Structure::registerPython();
    soap::Segment::registerPython();
    soap::Particle::registerPython();
    soap::Options::registerPython();

    soap::Spectrum::registerPython();
    soap::Basis::registerPython();
    soap::AtomicSpectrum::registerPython();
    soap::BasisExpansion::registerPython();
    soap::PowerExpansion::registerPython();
    soap::Mol2D::registerPython();

    soap::EnergySpectrum::registerPython();
    soap::HierarchicalCoulomb::registerPython();
    soap::AtomicSpectrumHC::registerPython();
    soap::FTSpectrum::registerPython();
    soap::AtomicSpectrumFT::registerPython();

    soap::RadialBasisFactory::registerAll();
    soap::AngularBasisFactory::registerAll();
    soap::CutoffFunctionFactory::registerAll();

    soap::npfga::FNode::registerPython();
    soap::npfga::FGraph::registerPython();
    soap::cgraph::CGraph::registerPython();
    soap::cgraph::CNode::registerPython();
    soap::cgraph::CNodeFactory::registerAll();
    soap::cgraph::OptimizerFactory::registerAll();

    soap::TopKernelFactory::registerAll();
    soap::BaseKernelFactory::registerAll();
    soap::Kernel::registerPython();
    soap::KernelInterface::registerPython();

    soap::DMap::registerPython();
    soap::GradMap::registerPython();
    soap::DMapMatrix::registerPython();
    soap::DMapMatrixSet::registerPython();
    soap::TypeEncoder::registerPython();
    soap::BlockLaplacian::registerPython();
    soap::Proto::registerPython();

    boost::python::def("silent", &soap::GLOG_SET_SILENT);
    boost::python::def("verbose", &soap::GLOG_SET_VERBOSE);
    boost::python::def("toggle_logger", &soap::GLOG_TOGGLE_SILENCE);
    boost::python::def("is_silent", &soap::GLOG_IS_SILENT);
    boost::python::def("silence", &soap::GLOG_SILENCE); // <- Deprecate
}
