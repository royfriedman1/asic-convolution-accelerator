#######################################################################
## 1. Initial Setup & Library Setup
#######################################################################

close_lib -purge -all

set_host_options -max_cores 8

lappend search_path "/project/tsmc28mmwave/users/royfriedman/ws/ex_vlsi_9"
set TECH_FILE "/data/tsmc/28HPCPMMWAVE/synopsys/tsmcn28_9lm6X1Z1URDL.tf"


file mkdir v1
file mkdir v1/reports
file mkdir v1/netlist


set_svf v1/netlist/accelerator_top.svf


file delete -force accelerator_synth.dlib

create_lib -technology $TECH_FILE -ref_libs { \
    /data/tsmc/28HPCPMMWAVE/synopsys/libs/tcbn28hpcplusbwp30p140.ndm \
    /data/tsmc/28HPCPMMWAVE/synopsys/libs/tcbn28hpcplusbwp30p140hvt.ndm \
    /data/tsmc/28HPCPMMWAVE/synopsys/libs/tcbn28hpcplusbwp30p140lvt.ndm \
} accelerator_synth.dlib

open_lib accelerator_synth.dlib

read_parasitic_tech -tlup /data/tsmc/28HPCPMMWAVE/dig_libs/snpsflow/rcbest/crn28hpc+_1p09m+ut-alrdl_6x1z1u_rcbest.tluplus -name rcbest
read_parasitic_tech -tlup /data/tsmc/28HPCPMMWAVE/dig_libs/snpsflow/rcworst/crn28hpc+_1p09m+ut-alrdl_6x1z1u_rcworst.tluplus -name rcworst
save_lib

#######################################################################
## 2. Read RTL (SystemVerilog)
#######################################################################
analyze -format sverilog { \
    accelerator_pkg.sv \
    latch_based_icg.sv \
    configuration_register_bank.sv \
    processing_element.sv \
    line_buffer_write_steering_logic.sv \
    line_buffer_read_address_logic.sv \
    line_buffer_reordering_logic.sv \
    line_buffer_memory_bank_wrapper.sv \
    line_buffer_physical_memory_array.sv \
    line_buffer_top.sv \
    control_unit.sv \
    accelerator_top.sv \
}

elaborate accelerator_top
set_top_module accelerator_top
save_block -as accelerator_top/elaborate

#######################################################################
## 3. Multi-Corner Multi-Mode (MCMM) & Constraints Setup
#######################################################################
remove_corners   -all
remove_modes     -all
remove_scenarios -all

create_corner Fast
create_corner Slow

set_parasitics_parameters -early_spec rcbest -late_spec rcbest -corners {Fast}
set_parasitics_parameters -early_spec rcworst -late_spec rcworst -corners {Slow}

create_mode FUNC
current_mode FUNC

create_scenario -mode FUNC -corner Fast -name FUNC_Fast
create_scenario -mode FUNC -corner Slow -name FUNC_Slow

current_scenario FUNC_Fast 
source accelerator_top.sdc

current_scenario FUNC_Slow 
source accelerator_top.sdc

#######################################################################
## 4. Synthesis & Area/Power Optimization
#######################################################################
set_auto_floorplan_constraints -core_utilization 0.75 -side_ratio {1 1} -core_offset 2

set_lib_cell_purpose [get_lib_cells */CKL*] -include {optimization cts}
remove_attribute [get_lib_cells */CKL*] dont_use

set_app_options -name opt.area.effort -value high
set_app_options -name opt.power.effort -value high

set_placement_spacing_label -name {no_1X} -side both -lib_cells [get_lib_cells */*]
set_placement_spacing_rule -labels {no_1X no_1X} {1 1}

compile_fusion -to logic_opto
compile_fusion -to final_opto

save_block -as accelerator_top/final_opto

#######################################################################
## 5. Generate Reports & Export
#######################################################################
set_svf -off

report_area -hierarchy > v1/reports/area_report.log
report_power           > v1/reports/power_report.log
report_timing          > v1/reports/timing_report.log
report_utilization     > v1/reports/utilization_report.log
report_qor             > v1/reports/qor_report.log

write_verilog v1/netlist/accelerator_top_synth.v
write_sdc -output v1/netlist/accelerator_top_synth.sdc

puts "========================================================="
puts " Synthesis Completed Successfully for v1! "
puts " All outputs and the SVF file are ready in the v1 folder. "
puts "========================================================="
exit
