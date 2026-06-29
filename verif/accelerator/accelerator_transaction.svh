`ifndef ACCELERATOR_TRANSACTION_SVH
`define ACCELERATOR_TRANSACTION_SVH

import accelerator_pkg::*;

class accelerator_transaction;
	
	// Stimulus
	rand pixel_t   input_bus;
	rand bit       pixel_valid_in;
	rand bit       cfg_wr_en;
	
	// Timing Control
	rand int       injection_delay;
	
	// Results (For ScoreBoard)
	bit            actual_out;
	bit            expected_out;
	
	// Constraints
	// Mutex
	constraint c_valid_mutex {
		!(pixel_valid_in && cfg_wr_en);
	}
		
	constraint c_delay {
		injection_delay inside {[0:5]};
	}
	
	function void copy(output accelerator_transaction target);
		target = new();
		target.input_bus = this.input_bus;
		target.pixel_valid_in = this.pixel_valid_in;
		target.cfg_wr_en = this.cfg_wr_en;
		target.expected_out = this.expected_out;
	endfunction
	
	function void display(string prefix ="TOP_TR");
		string mode;
		if (pixel_valid_in) mode = "PIXEL";
		else if (cfg_wr_en) mode = "CONFIG";
		else mode = "IDLE"; // Added IDLE state printing
		
		$display("[%s] @%0t | Mode: %s | Data: 0x%h | ExpOut: %b",
				prefix, $time, mode, input_bus, expected_out);
	endfunction
	
endclass

`endif