# Scope of the project
- Implement an analysis framework relying on MiniAOD to perform a calibration of the jet-charge tagger using di-leptonic and single-leptonic ttbar events
- Framework should contain 3 parts: 1) Ntuples processing with inference of jet-charge on MiniAOD, 2) Analysis framework to plot / debug and store histograms for fitting, 3) fitting framework (to be implemented later)


# Ntuples processing
- Framework should process MiniAODs and perform inference of jet-charge on each jets from MiniAOD events
- Apply trigger (single lepton, single muon triggers) / pre-selection (jets, leptons) + corrections on jets for both data and MC
- Save ntuples with all the variables reconstructed / possibly perform kinematic fit for ttbar reconstruction
- Framework should run on both signal (ttbar) and backgrounds (QCD, V+jets, single top)
- Need to save both the flavor (hadronFlavour) and the charge, based on the matching implemented in the examples

Use examples under:
/home/mstamenk/jet-charge-calibration/framework-examples/

-`/home/mstamenk/jet-charge-calibration/framework-examples/nanoAOD-tools`: framework for HHH6b analysis containing filesets for NanoAODs + corrections packages to be copied
-`/home/mstamenk/jet-charge-calibration/framework-examples/PhysicsTools/NanoNN/`: framework for HHH6b processing for Run 2, keep the correcitons / necessary inputs such as golden json and such
-`/home/mstamenk/jet-charge-calibration/framework-examples/PPSFramework`: MiniAOD framework for inspiration, running on CT-PPS which is not necessary for this project
-`/home/mstamenk/jet-charge-calibration/framework-examples/cmssw-charge-setup`: example for inference from onnx for jet-charge, ask user if needed to get the right files from the CMSSW_15_CHARGE

Additional informations for BTV processing / how to sample MiniAODs and important informations to perform training of jet-charge tagger:
-`/home/mstamenk/btv-nano-prod`
-`/home/mstamenk/ddp-charge-tagger/CMSSW_14_0_11/src`

Use all of it for the context / understand what lies where

- Constraint: able to run locally for small example, suitable to run on condor too, need samples for EGamma and Muon datasets

- Framework should be stored under: `/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod` to be able to push to github later
- Output samples to be stored under: `/home/mstamenk/jet-charge-calibration/samples` + `version` (v1, v2, ...)

# Analysis framework
- At first, simple plotting the trigger efficiency, top mass, lepton pT, jets pT, jet flavour, jet charge score, and useful debugging informations
