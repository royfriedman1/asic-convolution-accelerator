# ASIC Verification & Analysis Suite

A standalone PyQt6 desktop application that hosts the Python **golden model** for the
3x3 convolution accelerator and provides tools to generate test stimulus, visualize the
hardware's internal architecture, and compare golden-model output against real RTL/GLS
simulation output.

## Golden model

[`core/golden_model.py`](core/golden_model.py) bit-exactly reproduces the hardware spec:

- Input: 256x256 grayscale image, 8-bit unsigned, raster-scan order
- Kernel: 3x3, 8-bit unsigned weights
- `MAC = sum(pixel * weight) + bias`, masked to 20 bits (wrap-around, matching the RTL's `ACCUM_W`)
- Output: 1 bit per pixel — `1` if `MAC > threshold`, else `0`
- Valid region: rows/cols 2-255 (first 2 rows/cols are pipeline flush) → 254x254 output

This model is what the testbench scoreboard checks RTL/GLS output against.

## Running the app

```
pip install -r requirements.txt
python main.py
```

Tested with Python 3.11 on Windows 11. OpenCV is optional but recommended for fast
video/image I/O (falls back to Pillow if absent).

## What the app does

- **Generator** ([`ui/generator_widget.py`](ui/generator_widget.py)) — define a kernel/bias/threshold,
  run it over an image or video through the golden model, and export `.hex` stimulus files
  (`$readmemh`-compatible) plus golden reference output for the RTL testbench.
- **Analyst** ([`ui/analyst_widget.py`](ui/analyst_widget.py)) — load a completed run and compare
  golden-model output, RTL/GLS simulation output, and the source image side by side.
- **Memory / PE / Synthesis visualizers** ([`ui/memory_sim_widget.py`](ui/memory_sim_widget.py),
  [`ui/pe_widget.py`](ui/pe_widget.py), [`ui/synthesis_widget.py`](ui/synthesis_widget.py)) — visualize
  the line-buffer memory banking, the processing element pipeline, and synthesis QoR/power/area reports.

Sample runs (input frame, golden output, run parameters) are under [`demo/`](demo).

## Tests

```
pytest tests/test_golden_model.py
```

## Building a standalone executable

[`do_build.py`](do_build.py) / [`main.spec`](main.spec) package the app with PyInstaller.
