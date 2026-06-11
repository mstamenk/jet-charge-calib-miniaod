# Analysis Quickstart

Run in a CMSSW environment with PyROOT available.

```bash
python3 analysis/plot_basic.py --input "path/to/ntuple.root" --outdir analysis/plots
```

For jet-charge by flavour/sign:

```bash
python3 analysis/plot_charge_by_flavor_sign.py --input "path/to/ntuple.root" --outdir analysis/plots_charge --normalize
```

Outputs:

- `trigger_efficiency.png`
- `top_mass_proxy.png`
- `lepton_pt.png`
- `jet_pt.png`
- `jet_flavour.png`
- `jet_charge_score.png`
- `debug_njets.png`
- `debug_nlep.png`
- `basic_plots.root`

Additional outputs from `plot_charge_by_flavor_sign.py`:

- `jet_charge_score_b_plus_vs_minus.png`
- `jet_charge_score_c_plus_vs_minus.png`
- `jet_charge_score_light_plus_vs_minus.png`
- `jet_charge_score_plus_vs_minus_combined.png`
- `charge_by_flavour_sign.root`
