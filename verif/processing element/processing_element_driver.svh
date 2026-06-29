`ifndef PROCESSING_ELEMENT_DRIVER_SVH
`define PROCESSING_ELEMENT_DRIVER_SVH

class processing_element_driver;
	
	virtual processing_element_if.DRV vif;
	
	mailbox #(processing_element_transaction) seq2drv; // From Sequencer
	mailbox #(processing_element_transaction) drv2mon; // To Monitor (for latency sync)
	
	function new(virtual processing_element_if.DRV    vif,
			mailbox #(processing_element_transaction) seq2drv,
			mailbox #(processing_element_transaction) drv2mon);
		this.vif = vif;
		this.seq2drv = seq2drv;
		this.drv2mon = drv2mon;
	endfunction
	
	task run();
		$display("[Driver] @%t: Processing Element Driver is active", $time);
		
		@(vif.cb);
		vif.cb.window_valid_in <= 1'b0;
		
		forever begin
			processing_element_transaction tr;
			
			if (seq2drv.try_get(tr) != 0) begin
				drive_item(tr);
			end else begin
				@(vif.cb);
				vif.cb.window_valid_in <= 1'b0;
			end
		end
	endtask
	
	task drive_item(processing_element_transaction tr);
		@(vif.cb);
		
		vif.cb.window_valid_in <= tr.valid;
		vif.cb.pixels          <= tr.pixels;
		vif.cb.weights         <= tr.weights;
		vif.cb.bias            <= tr.bias;
		vif.cb.threshold       <= tr.threshold;
		
		drv2mon.put(tr);
		
		$display("[Driver] @%t: Driven Processing Element transaction. Valid=%b", $time, tr.valid);
	endtask
	
endclass

`endif