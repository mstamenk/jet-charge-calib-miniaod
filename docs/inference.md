# Inference Notes

This framework assumes jet-charge inference is already available in MiniAOD through CMSSW charge-tagging integration.

## Current Model

- `model-onnx/dp-2025-071-model.onnx`
- Size: ~4.5 MB
- SHA256: `74cf06aacb237581b81fc5be3069f58ec2df802a4465fdf7f9f58e6784c77c3e`

## Expected CMSSW Model Location

`RecoBTag/Combined/data/RobustParTAK4/PUPPI/V00/modelfile/final_model.onnx`

Use:

```bash
scripts/install_model_in_cmssw.sh /path/to/CMSSW_15_1_0_patch4 model-onnx/dp-2025-071-model.onnx
```

## What The Ntuplizer Reads

The ntuplizer stores:

- `jet_btagRobustParTAK4B`
- `jet_btagRobustParTAK4CvB`
- `jet_btagRobustParTAK4CvL`
- `jet_btagRobustParTAK4QG`
- `jet_ParTPosvsAll`
- `jet_ParTNegvsAll`
- `jet_ParTZerovsAll`
- `jet_ParTPosvsNeg`
- `jet_charge_score`

If these discriminator labels are not found in MiniAOD jets, values default to fallback (`-1` for discriminators; charge-score fallback to k=0.5 jet charge).

## If Inference Outputs Are Missing

Confirm the CMSSW release includes the charge-topic integration (CMSSW_15_CHARGE) and that the ONNX model is placed at the exact path above.
