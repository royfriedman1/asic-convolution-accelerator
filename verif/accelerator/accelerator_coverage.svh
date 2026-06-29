`ifndef ACCELERATOR_COVERAGE_SVH
`define ACCELERATOR_COVERAGE_SVH

class accelerator_coverage;

	virtual accelerator_if vif;

	// Covergroup 1: Input and Configuration Path
	covergroup cg_inputs @(posedge vif.clk);
		option.per_instance = 1;
		option.goal = 100;

		// Sample only when not in reset
		cp_cfg_en: coverpoint vif.cfg_wr_en iff (vif.rst_n == 1'b1);
		cp_valid:  coverpoint vif.pixel_valid_in iff (vif.rst_n == 1'b1);

		cr_system_state: cross cp_cfg_en, cp_valid {
			bins config_mode = binsof(cp_cfg_en) intersect {1} && binsof(cp_valid) intersect {0};
			bins data_mode   = binsof(cp_cfg_en) intersect {0} && binsof(cp_valid) intersect {1};
			bins idle_bubble = binsof(cp_cfg_en) intersect {0} && binsof(cp_valid) intersect {0};
			illegal_bins collision = binsof(cp_cfg_en) intersect {1} && binsof(cp_valid) intersect {1};
		}

		cp_pixel_in: coverpoint vif.input_bus iff (vif.rst_n == 1'b1 && vif.pixel_valid_in == 1'b1) {
			bins min_val    = {8'h00};
			bins max_val    = {8'hFF};
			bins low_range  = {[8'h01 : 8'h7F]};
			bins high_range = {[8'h80 : 8'hFE]};
		}

		cp_config_data: coverpoint vif.input_bus iff (vif.rst_n == 1'b1 && vif.cfg_wr_en == 1'b1) {
			bins min_val    = {8'h00};          // 0
			bins max_val    = {8'hFF};          // 255
			bins lower_half = {[8'h01 : 8'h7F]}; // 1 to 127
			bins upper_half = {[8'h80 : 8'hFE]}; // 128 to 254
		}
	endgroup

	// Covergroup 2: Output and Pipeline Recovery
	covergroup cg_outputs @(posedge vif.clk);
		option.per_instance = 1;
		option.goal = 100;

		// Pipeline recovery mechanism: valid drops for 2 cycles between rows
		cp_pipeline_bubbles: coverpoint vif.pixel_valid_out iff (vif.rst_n == 1'b1) {
			bins row_transition = (1 => 0 [* 2] => 1); 
		}

		cp_pixel_out: coverpoint vif.pixel_out iff (vif.rst_n == 1'b1 && vif.pixel_valid_out == 1'b1) {
			bins classified_zero = {0}; 
			bins classified_one  = {1}; 
		}
	endgroup

	// Constructor gets the physical wires (virtual interface)
	function new(virtual accelerator_if v_if);
		this.vif = v_if;
		cg_inputs = new();
		cg_outputs = new();
		$display("[Coverage] @%0t: Cycle-Accurate Coverage Collector initialized", $time);
	endfunction

endclass

`endif