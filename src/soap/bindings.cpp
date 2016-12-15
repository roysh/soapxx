#include "bindings.hpp"
#include "coulomb.hpp"
#include "fieldtensor.hpp"

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

    soap::EnergySpectrum::registerPython();
    soap::HierarchicalCoulomb::registerPython();
    soap::AtomicSpectrumHC::registerPython();
    soap::FTSpectrum::registerPython();
    soap::AtomicSpectrumFT::registerPython();

    soap::RadialBasisFactory::registerAll();
    soap::AngularBasisFactory::registerAll();
    soap::CutoffFunctionFactory::registerAll();


    boost::python::def("silence", &soap::GLOG_SILENCE);
}
