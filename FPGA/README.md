# FPGA Integration & Live Demo

This accelerator was integrated as a live demo into the open-source FPGA project
**[Marc103/OV7670-with-FPGA-and-Demosaicing](https://github.com/Marc103/OV7670-with-FPGA-and-Demosaicing)**,
which already implements OV7670 camera capture, demosaicing, and VGA display on a
Nexys-3 (Spartan-6) board. This repo does **not** vendor that project — clone it
separately and drop the accelerator in as described below.

## What's here

- [`accel_display_wrapper.sv`](accel_display_wrapper.sv) — bridges the base project's
  `conv_net_smooth` pixel stream to [`accelerator_top`](../rtl/accelerator_top.sv) and
  back to the `VGA_PARAM` display module. It:
  - converts the base project's 12-bit RGB stream to 8-bit grayscale luminance,
  - streams a 13-byte configuration burst (9 weights + bias + 3-byte threshold) into
    the accelerator at the start of every frame,
  - centers the accelerator's 256x256 processing window inside the 640x480 VGA frame,
  - multiplexes between passthrough video (`mode=0`) and the accelerator's
    black/white classification output (`mode=1`).
- `demo/board_setup.jpeg` — the physical setup: OV7670 camera + Nexys-3 board + VGA monitor.
- `demo/fpga_demo.mp4` — the accelerator running live on hardware.

## Integration steps

1. Clone the base project and get it building/working on your board first:
   `git clone https://github.com/Marc103/OV7670-with-FPGA-and-Demosaicing`
2. Copy [`accel_display_wrapper.sv`](accel_display_wrapper.sv) and the contents of
   [`../rtl`](../rtl) into the base project's source tree (or add them to its build script).
3. In the base project's top-level module, replace the direct connection from
   `conv_net_smooth` to `VGA_PARAM` with the wrapper, as shown in the header comment
   of `accel_display_wrapper.sv`:

   ```systemverilog
   accel_display_wrapper wrap (
       .rgb_in   ({r.pixel, g.pixel, b.pixel}),
       .valid_in (red_smooth.valid),
       .row_in   (red_smooth.row),
       .col_in   (red_smooth.col),
       .mode     (switches_PIN[0]),   // SW0: 0=passthrough, 1=accelerator
       .sw_thr   (switches_PIN[14:12]), // SW14:12: threshold tuning
       .rgb_out  (w_vga_rgb),
       .valid_out(w_vga_valid),
       .row_out  (w_vga_row),
       .col_out  (w_vga_col)
   );
   VGA_PARAM(.r_data(w_vga_rgb), .r_dv(w_vga_valid), ...);
   VBUFF_READER(.row_i(w_vga_row), .col_i(w_vga_col));
   ```
4. Re-synthesize and program the board. Toggle `SW0` to switch between the live
   passthrough camera feed and the accelerator's classification output; `SW14:12`
   adjusts the detection threshold at runtime.

Default kernel parameters (loaded automatically every frame) are all-weights=`0x05`,
bias=`0`, base threshold=`16`, acting as a simple energy/edge presence detector.

## Demo

| Hardware setup | Live demo |
|---|---|
| ![board setup](demo/board_setup.jpeg) | [`demo/fpga_demo.mp4`](demo/fpga_demo.mp4) |
