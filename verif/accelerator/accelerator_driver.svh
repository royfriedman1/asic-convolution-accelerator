`ifndef ACCELERATOR_DRIVER_SVH
`define ACCELERATOR_DRIVER_SVH

class accelerator_driver;
	
	// virtual interface
	virtual accelerator_if.drv_mp vif;
	
	// Mailbox
	mailbox #(accelerator_transaction) gen2drv;
	
	function new(virtual accelerator_if.drv_mp    vif,
			mailbox #(accelerator_transaction) gen2drv);
		this.vif = vif;
		this.gen2drv = gen2drv;
	endfunction
	
	task run();
		$display("[Driver] @%0t: Accelerator Driver is active", $time);
		
		// Initial Reset Phase
		@(vif.drv_cb);
		vif.drv_cb.pixel_valid_in <= 1'b0;
		vif.drv_cb.cfg_wr_en      <= 1'b0;
		vif.drv_cb.input_bus      <= 8'h00;
		
		wait(vif.rst_n === 1'b1);
		@(vif.drv_cb);
		@(vif.drv_cb);
		
		// Mail-Man loop
		forever begin
			// If reset goes low, stop driving and wait until it goes high again
			if (vif.rst_n === 1'b0) begin
				vif.drv_cb.pixel_valid_in <= 1'b0;
				vif.drv_cb.cfg_wr_en      <= 1'b0;
				vif.drv_cb.input_bus      <= 8'h00;
				
				$display("[Driver] @%0t: Reset detected. Pausing driver...", $time);
				wait(vif.rst_n === 1'b1);
				@(vif.drv_cb); // Synchronize with the clock after reset is lifted
			end 
			else begin
				accelerator_transaction tr;
				
				// try_get
				if (gen2drv.try_get(tr)) begin
					
					// Delay (Idle cycles)
					repeat(tr.injection_delay) begin
						vif.drv_cb.pixel_valid_in <= 1'b0;
						vif.drv_cb.cfg_wr_en      <= 1'b0;
						@(vif.drv_cb); // wait for 1 clock cycle
					end
					
					// Drive
					vif.drv_cb.pixel_valid_in <= tr.pixel_valid_in;
					vif.drv_cb.cfg_wr_en      <= tr.cfg_wr_en;
					vif.drv_cb.input_bus      <= tr.input_bus;
					@(vif.drv_cb); // wait for 1 clock cycle
					
				end else begin
					// if Mailbox is empty we are in Idle. wait for 1 clock cycle
					vif.drv_cb.pixel_valid_in <= 1'b0;
					vif.drv_cb.cfg_wr_en      <= 1'b0;
					@(vif.drv_cb);
				end
			end
		end
	endtask
	
endclass

`endif