#include <cstdint>

#include "FWCore/Framework/interface/Frameworkfwd.h"
#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/one/EDAnalyzer.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/ServiceRegistry/interface/Service.h"
#include "CommonTools/UtilAlgos/interface/TFileService.h"
#include "FWCore/MessageLogger/interface/MessageLogger.h"

#include "SimDataFormats/GeneratorProducts/interface/GenEventInfoProduct.h"
#include "TH1D.h"

class InputEventWeightCounter : public edm::one::EDAnalyzer<edm::one::SharedResources> {
public:
  explicit InputEventWeightCounter(const edm::ParameterSet&);
  ~InputEventWeightCounter() override = default;

  void analyze(const edm::Event&, const edm::EventSetup&) override;
  void beginJob() override;
  void endJob() override;

private:
  edm::EDGetTokenT<GenEventInfoProduct> genEventInfoToken_;
  bool isData_;

  uint64_t nInputEvents_ = 0;
  double sumGenWeightsInput_ = 0.0;

  TH1D* inputWeightMetadata_ = nullptr;
};

InputEventWeightCounter::InputEventWeightCounter(const edm::ParameterSet& cfg)
    : genEventInfoToken_(consumes<GenEventInfoProduct>(cfg.getParameter<edm::InputTag>("genEventInfo"))),
      isData_(cfg.getParameter<bool>("isData")) {
  usesResource("TFileService");
}

void InputEventWeightCounter::beginJob() {
  edm::Service<TFileService> fs;
  inputWeightMetadata_ = fs->make<TH1D>("inputWeightMetadata", "inputWeightMetadata", 2, 0.5, 2.5);
  inputWeightMetadata_->GetXaxis()->SetBinLabel(1, "n_input_events");
  inputWeightMetadata_->GetXaxis()->SetBinLabel(2, "sum_gen_weights_input");
}

void InputEventWeightCounter::analyze(const edm::Event& event, const edm::EventSetup&) {
  ++nInputEvents_;
  if (isData_) {
    return;
  }

  edm::Handle<GenEventInfoProduct> genInfo;
  event.getByToken(genEventInfoToken_, genInfo);
  if (genInfo.isValid()) {
    sumGenWeightsInput_ += static_cast<double>(genInfo->weight());
  } else {
    // Keep the event count valid even if generator info is missing in some events.
    sumGenWeightsInput_ += 1.0;
  }
}

void InputEventWeightCounter::endJob() {
  if (inputWeightMetadata_ != nullptr) {
    inputWeightMetadata_->SetBinContent(1, static_cast<double>(nInputEvents_));
    inputWeightMetadata_->SetBinContent(2, sumGenWeightsInput_);
  }
  edm::LogPrint("InputEventWeightCounter")
      << "[jet-charge-calib] input-event metadata: n_input_events=" << nInputEvents_
      << " sum_gen_weights_input=" << sumGenWeightsInput_;
}

DEFINE_FWK_MODULE(InputEventWeightCounter);
