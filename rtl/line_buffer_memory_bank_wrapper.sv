import accelerator_pkg::*;

module line_buffer_memory_bank_wrapper #(
	parameter int ADDR_WIDTH = BANK_ADDR_W, 
	parameter int DATA_WIDTH = PIXEL_WIDTH,
	parameter int BANK_DEPTH = 1 << ADDR_WIDTH
) (
	input  logic                  clk,
	
	// Write Interface (Synchronous)
	input  logic                  wr_en,
	input  logic [ADDR_WIDTH-1:0] wr_addr,
	input  logic [DATA_WIDTH-1:0] data_in,
	
	// Read Interface (Synchronous Read-Latency = 1)
	input  logic [ADDR_WIDTH-1:0] rd_addr,
	output logic [DATA_WIDTH-1:0] data_out
);

	// Internal Storage Array
	logic [DATA_WIDTH-1:0] memory_array [0:BANK_DEPTH-1];


	// Write Path 
	always_ff @(posedge clk) begin
		if (wr_en) begin
			memory_array[wr_addr] <= data_in;
		end
	end

	// Read Path (Synchronous with Bypass to solve Read After Write) 
	always_ff @(posedge clk) begin
		if (wr_en && (wr_addr == rd_addr)) begin
			data_out <= data_in;
		end else begin
			data_out <= memory_array[rd_addr];
		end
	end

endmodule