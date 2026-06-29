/*
 * accel_display_wrapper.sv
 *
 * This wrapper bridges the conv_net_smooth module and the VGA_PARAM component.
 * Dynamic Configuration - loads network parameters on the first frame arrival.
 *
 * mode=0  ->  passthrough (conv_net_smooth data passes unmodified)
 * mode=1  ->  accelerator (data processed via accelerator_top, binary output formatted to 4-bit full/zero scale)
 *
 * ==================================================================
 * Usage in TOP.sv:
 *
 * // BEFORE:
 * logic [11:0] data;
 * always@(posedge clk25) data <= {r.pixel, g.pixel, b.pixel};
 * VGA_PARAM(.r_data(data), .r_dv(red_smooth.valid), ...)
 * VBUFF_READER(.row_i(red_smooth.row), .col_i(red_smooth.col))
 *
 * // AFTER:
 * accel_display_wrapper wrap(.rgb_in({r.pixel,g.pixel,b.pixel}),
 * .valid_in(red_smooth.valid),
 * .row_in(red_smooth.row), .col_in(red_smooth.col),
 * .mode(switches_PIN[0]),
 * .rgb_out(w_vga_rgb), .valid_out(w_vga_valid),
 * .row_out(w_vga_row), .col_out(w_vga_col), ...);
 * VGA_PARAM(.r_data(w_vga_rgb), .r_dv(w_vga_valid), ...)
 * VBUFF_READER(.row_i(w_vga_row), .col_i(w_vga_col))
 *
 * ==================================================================
 * Centering 256x256 window inside a 640x480 resolution frame:
 * col: 192 ... 447
 * row: 112 ... 367
 *
 * The accelerator expects valid stream data targeted exclusively via pixel_valid_in.
 * Memory row/col counters inside the core track the absolute spatial positioning.
 *
 * ==================================================================
 * Parameter Loading Protocol (Triggered once per frame reset):
 * At frame start (row==0, col==0, valid==1):
 * - Assert cfg_wr_en=1 for 13 clock cycles, streaming sequential bytes to input_bus.
 * - On cycle 13, de-assert cfg_wr_en=0 to introduce a 1-cycle latency gap.
 * - Resume normal frame streaming.
 *
 * Default Kernel Parameters: All 9 weights = 8'h05, bias=0, threshold=16
 * (Acts as an energy presence detector - activates white when features cross the ??)
 */

import accelerator_pkg::*;

module accel_display_wrapper (
    input  logic        clk,
    input  logic        rst_n,

    // Interface from conv_net_smooth module
    input  logic [11:0] rgb_in,      // {R[3:0], G[3:0], B[3:0]}
    input  logic        valid_in,
    input  logic [15:0] row_in,
    input  logic [15:0] col_in,

    // Runtime control inputs
    input  logic        mode,        // 0=passthrough  1=accelerator
    input  logic [2:0]  sw_thr,      // SW[14:12] - Controls the MID byte of the threshold value

    // Interface to VGA_PARAM component (Drives physical display)
    output logic [11:0] rgb_out,
    output logic        valid_out,
    output logic [15:0] row_out,
    output logic [15:0] col_out
);

    // Geometry parameters to center the 256x256 window inside 640x480 resolution
    localparam int COL_START = 192;
    localparam int COL_END   = 447;   // COL_START + 256 - 1
    localparam int ROW_START = 112;
    localparam int ROW_END   = 367;   // ROW_START + 256 - 1

    // Config payload parameters (13 bytes total configuration)
    // weights[0..8]=0x05, bias=0x00, threshold=0x000010 (=16)
    localparam int CFG_LEN = 13;
    logic [7:0] cfg_rom [0:CFG_LEN-1];
    
    // Derived threshold MID byte determined dynamically by external SW[14:12]
    // LSB and MSB are padded to 0, providing coarse threshold tuning on the MID byte
    // Threshold MID register mapping (Bits 15:8)
    logic [7:0] thr_mid;
    // Threshold LSB register mapping (Bits 7:0) - Needed for exact resolution step
    logic [7:0] thr_lsb;    always_comb begin
        case (sw_thr)
            // ????? ???? ???? / ???? ??????
            3'b000: begin thr_mid = 8'h01; thr_lsb = 8'h00; end // TH = 256
            // ????? ????? ?? ???? (????? ???? ??)
            3'b001: begin thr_mid = 8'h03; thr_lsb = 8'h00; end // TH = 768
            // ????? ?? ???? ???? ???? (???? ?????, ???? ??????)
            3'b010: begin thr_mid = 8'h05; thr_lsb = 8'h00; end // TH = 1280
            // ????? ????? ???? (?? ???? ????)
            3'b011: begin thr_mid = 8'h07; thr_lsb = 8'h00; end // TH = 1792
            // ??? "??????" - ?? ??????? ??? ???? (??????/????) ??????
            3'b100: begin thr_mid = 8'h09; thr_lsb = 8'h00; end // TH = 2304
            // ???? ??? ????????
            3'b101: begin thr_mid = 8'h0B; thr_lsb = 8'h00; end // TH = 2816
            3'b110: begin thr_mid = 8'h0D; thr_lsb = 8'h00; end // TH = 3328
            3'b111: begin thr_mid = 8'h0F; thr_lsb = 8'hFF; end // TH = 4095
        endcase
    end

    always_comb begin
        cfg_rom[0]  = 8'h08; cfg_rom[1]  = 8'h00; cfg_rom[2]  = 8'h00;
        cfg_rom[3]  = 8'h08; cfg_rom[4]  = 8'h08; cfg_rom[5]  = 8'h00;
        cfg_rom[6]  = 8'h08; cfg_rom[7]  = 8'h00; cfg_rom[8]  = 8'h00;
        cfg_rom[9]  = 8'h00;       // bias
        cfg_rom[10] = thr_lsb;      // threshold LSB
        cfg_rom[11] = thr_mid;     // threshold MID byte assigned via SW[14:12]
        cfg_rom[12] = 8'h00;       // threshold MSB
    end

    // FSM to control the sequential configuration phase
    typedef enum logic [1:0] {
        S_BOOT,   // Post-reset state - waits for the first valid_in pulse
        S_CFG,    // Configuration burst state - streams 13 configuration cycles
        S_GAP,    // Protection state - pulls down cfg_wr_en to 0 before execution
        S_RUN     // Active processing state - streams frame pixels to the core
    } fsm_t;

    fsm_t       state, state_next;
    logic [3:0] cfg_cnt, cfg_cnt_next;

    // Detects absolute frame start coordinates: row=0, col=0, valid=1
    wire frame_start = valid_in && (row_in == 16'd0) && (col_in == 16'd0);

    always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) begin
            state   <= S_BOOT;
            cfg_cnt <= 4'd0;
        end else begin
            state   <= state_next;
            cfg_cnt <= cfg_cnt_next;
        end

    // Input Window boundary: Checks if coordinates are within the full 256x256 array
    wire in_window = (col_in >= COL_START) && (col_in <= COL_END) &&
                     (row_in >= ROW_START) && (row_in <= ROW_END);

    // Display boundary: Truncates 2 padding columns to skip invalid kernel border pixels
    wire in_display = (col_in >= COL_START + 2) && (col_in <= COL_END) &&
                      (row_in >= ROW_START + 2) && (row_in <= ROW_END);

    // Interconnect network signals to the core accelerator top module
    logic [7:0] accel_bus;
    logic       accel_cfg_wr_en;

    // pixel_valid_in control: Active only during S_RUN state when stream hits the active array area
    logic       accel_pix_valid;

    always_comb begin
        state_next      = state;
        cfg_cnt_next    = cfg_cnt;
        accel_bus       = 8'h00;
        accel_cfg_wr_en = 1'b0;
        accel_pix_valid = 1'b0;

        case (state)
            // Wait for structural frame alignment synchronization
            S_BOOT: begin
                if (frame_start) begin
                    state_next   = S_CFG;
                    cfg_cnt_next = 4'd0;
                end
            end

            // Drive 13 continuous parameter loading write cycles
            S_CFG: begin
                accel_cfg_wr_en = 1'b1;
                accel_bus       = cfg_rom[cfg_cnt];

                if (cfg_cnt == CFG_LEN - 1) begin
                    cfg_cnt_next = 4'd0;
                    state_next   = S_GAP;
                end else begin
                    cfg_cnt_next = cfg_cnt + 4'd1;
                end
            end

            // Introduce 1-cycle pipeline gap protection
            S_GAP: begin
                accel_cfg_wr_en = 1'b0;
                state_next      = S_RUN;
            end

            // Active frame processing cycle stream
            S_RUN: begin
                accel_pix_valid = valid_in && in_window;

                // Re-trigger configuration routine on subsequent scan frames
                if (frame_start) begin
                    state_next   = S_CFG;
                    cfg_cnt_next = 4'd0;
                end
            end
        endcase
    end

    // Instantiation block mapping data to the physical hardware module
    // 12-bit input converted to 8-bit unsigned grayscale luminance: (R+G+B)/3
    logic accel_out, accel_valid;

    // Luminance math converter: Sums channels and normalizes 4-bit depth to an 8-bit bus
    wire [5:0] lum6 = ({2'b0, rgb_in[11:8]} + {2'b0, rgb_in[7:4]} + {2'b0, rgb_in[3:0]});
    wire [3:0] lum4 = lum6[5:2];          // Divided by 4 as a fast division approximation (/3)
    wire [7:0] lum8 = {lum4, lum4};       // Padded structure to expand 4-bit to 8-bit unsigned bus

    accelerator_top u_accel (
        .clk            (clk),
        .rst_n          (rst_n),
        .input_bus      (state == S_CFG ? accel_bus : lum8),
        .pixel_valid_in (accel_pix_valid),
        .cfg_wr_en      (accel_cfg_wr_en),
        .pixel_out      (accel_out),
        .pixel_valid_out(accel_valid)
    );

    // Format single bit classification result to 12-bit binary representation
    // Pixels outside the active valid display frame are clamped to zero
    wire [3:0] px_bin = (accel_out && accel_valid && in_display) ? 4'hF : 4'h0;
    wire [11:0] rgb_accel = {px_bin, px_bin, px_bin};

    // Output data path multi-plexer selector logic
    // Coordinates and global validations are kept synchronized via passthrough wiring
    always_ff @(posedge clk) begin
        rgb_out <= mode ? rgb_accel : rgb_in;
    end

    assign valid_out = valid_in;
    assign row_out   = row_in;
    assign col_out   = col_in;

endmodule