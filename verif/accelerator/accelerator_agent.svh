`ifndef ACCELERATOR_AGENT_SVH
`define ACCELERATOR_AGENT_SVH

class accelerator_agent;
	
	// Agent components
	accelerator_generator gen;
	accelerator_driver    drv;
	accelerator_monitor   mon;
	
	// Mailbox
	mailbox #(accelerator_transaction) gen2drv_mbx;
	
	// Interface to DUT
	virtual accelerator_if vif;
	
	// Constructor
	function new(virtual accelerator_if        vif,
			mailbox #(accelerator_transaction) gen2scb, // Expected
			mailbox #(accelerator_transaction) mon2scb); // Actual
		
		this.vif = vif;
		this.gen2drv_mbx = new(1);
		gen = new(gen2drv_mbx, gen2scb, vif);
		drv = new(vif.drv_mp, gen2drv_mbx);
		mon = new(vif.mon_mp, mon2scb);
		
	endfunction
	
	task run();
		$display("[Agent] @%0t: Agent is starting components...", $time);
		
		fork
			drv.run();
			mon.run();
		join_none
		
		gen.run();
		
		$display("[Agent] @%0t: Generator finished. Agent is done.", $time);
	endtask
	
endclass

`endif