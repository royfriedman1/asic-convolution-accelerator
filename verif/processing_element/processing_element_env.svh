`ifndef PROCESSING_ELEMENT_ENV_SVH
`define PROCESSING_ELEMENT_ENV_SVH

class processing_element_env;
	
	processing_element_agent   agent;
	processing_element_scoreboard scb;
	
	mailbox #(processing_element_transaction) mon2scb;
	
	virtual processing_element_if vif;
	
	// Constructor
	function new(virtual processing_element_if vif);
		this.vif = vif;
		mon2scb = new();
		agent = new(vif, mon2scb);
		scb = new(mon2scb);
	endfunction
	
	task run();
		$display("[Environment] @%t: Starting Environment...", $time);
		
		// Start Scoreboard as a background process (it has a forever loop)
		fork
			scb.run();
		join_none

		// block until the Sequencer finishes
		agent.run();
		
	endtask
	
endclass

`endif