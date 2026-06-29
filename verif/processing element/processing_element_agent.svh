`ifndef PROCESSING_ELEMENT_AGENT_SVH
`define PROCESSING_ELEMENT_AGENT_SVH

class processing_element_agent;
	
	// Verification components
	processing_element_sequencer seq;
	processing_element_driver    drv;
	processing_element_monitor   mon;
	
	// Internal communication channels
	mailbox #(processing_element_transaction) seq2drv_mbx;
	mailbox #(processing_element_transaction) drv2mon_mbx;
	
	// Virtual Interface to the DUT
	virtual processing_element_if vif;
	
	function new(virtual processing_element_if vif, mailbox #(processing_element_transaction) mon2scb);
		this.vif = vif;
		
		// Initialize mailboxes. Size 1 for seq2drv provides backpressure.
		seq2drv_mbx = new(1);
		drv2mon_mbx = new();
		
		// Instantiate components and connect mailboxes
		seq = new(seq2drv_mbx);
		drv = new(vif, seq2drv_mbx, drv2mon_mbx);
		mon = new(vif, mon2scb, drv2mon_mbx);
	endfunction
	
	task run();
		// Start Driver and Monitor as background processes
		fork
			drv.run();
			mon.run();
		join_none
		
		// Sequencer controls the test duration
		seq.run();
		
	endtask
endclass

`endif