CM_FLAGS = -cm line+tgl+cond+fsm+branch+assert

all: clean comp run waveverdi

test: comp run

clean:
	rm -rf simv* csrc* *.log *.fsdb *.rc *.key verdi_config_file verdiLog *.conf

comp:
	TMPDIR=. vcs -f build.cud -sverilog -kdb -debug_acc+all -debug_region+cell+udp +vcs+fsdbon -cm line+tgl+cond+fsm+branch+assert 2>&1 | tee comp_error.log
	
run:
	qrsh -V -cwd -b y -q normal ./simv $(CM_FLAGS) 2>&1 | tee log

waveverdi: 	
	verdi -ssf novas.fsdb

coverage:
	verdi -cov -covdir simv.vdb