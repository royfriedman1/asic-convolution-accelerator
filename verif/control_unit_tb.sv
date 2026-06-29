
import accelerator_pkg::*;

module control_unit_tb ();

logic clk;
logic rst_n;
logic cfg_wr_en;
logic pixel_valid;

// Outputs from DUT
logic [CFG_ADDR_W-1:0]  cfg_addr;
logic [BANK_ADDR_W-1:0] wr_addr;
logic [BANK_ADDR_W-1:0] rd_base_addr;
logic [1:0]             wr_bank_sel;
logic [1:0]             horiz_offset;
logic [1:0]             wr_row_sel;
logic [1:0]             vert_ptr;
logic                   wr_en;
logic                   window_valid;

initial begin
	clk = 0;
	forever #5 clk = ~clk;
end


initial begin
	$fsdbDumpfile("novas.fsdb");
	$fsdbDumpvars(0, control_unit_tb);
	$fsdbDumpMDA();
end

// Instantiate the DUT
wire rd_en;
control_unit dut (
	.*,
	.rd_en(rd_en)
);


initial begin
	
	// Initialize
	rst_n       = 0;
	cfg_wr_en   = 0;
	pixel_valid = 0;
	
	$display("[%0t] Starting Unit-Level Test for Control Unit", $time);
	
	#20 rst_n = 1;
	#10;
	
	// Send Configuration (13 cycles: Weights + Bias + Thresh)
	$display("[%0t] PHASE 1: Configuration", $time);
	@(posedge clk);
	cfg_wr_en = 1;
	repeat(NUM_WEIGHTS + 1 + THRESH_STEPS) @(posedge clk); 	// Wait for exactly TOTAL_CFG_CYCLES (13 cycles)
	cfg_wr_en = 0;
	$display("[%0t] Configuration Done. FSM should return to IDLE.", $time);
	
	#20; 
	
	// Send 3 Rows of Pixels (To see window_valid turn ON)
	$display("[%0t] PHASE 2: Pixel Streaming (3 Rows)", $time);
	
	for (int i = 0; i < 3; i++) begin
		send_row(i);
	end
	
	// End of Test
	#50;
	$display("[%0t] Test Finished", $time);
	$finish;
end


// Task to simulate a continuous row of pixels
task send_row(input int row_num);
	$display("[%0t] Streaming Row %0d", $time, row_num);
	
	@(posedge clk);
	pixel_valid <= 1;
	
	// Send exactly IMG_WIDTH pixels (256)
	repeat(IMG_WIDTH) @(posedge clk);
	
	pixel_valid <= 0;
	
	// Wait 5 cycles between rows
	repeat(5) @(posedge clk);
endtask

// Monitor 
initial begin
	$monitor("Time: %0t | FSM State: %0d | valid_in: %b | wr_en: %b | wr_bank: %0d | wr_row: %0d | window_valid: %b",
			$time, dut.current_state, pixel_valid, wr_en, wr_bank_sel, wr_row_sel, window_valid);
end

// Checker: Catches the exact moment the window becomes valid
always_ff @(posedge clk) begin
	if (window_valid && !($past(window_valid))) begin
		$display("[%0t] SUCCESS: window_valid went HIGH!", $time);
	end
end

endmodule