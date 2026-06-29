#######################################################################
## 1. Load Library & Block
#######################################################################
close_lib -purge -all
open_lib accelerator_synth.dlib

open_block accelerator_top/elaborate

puts "--- LOADING TIMING AND MCMM CONSTRAINTS ---"

#######################################################################
## 2. MCMM & SDC Constraints 
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

puts "--- STARTING THE 16-STEP PHYSICAL SYNTHESIS FLOW ---"


# 1. Set auto floorplan constraints
set_auto_floorplan_constraints -core_utilization 0.6 -side_ratio {1 1} -core_offset 2 

# 2. Continue on missing scandef
set_app_options -name place.coarse.continue_on_missing_scandef -value true 

# 3. Design integrity check
compile_fusion -check_only 

# 4. Initial logic mapping
compile_fusion -to initial_map 

# 5. Early logic optimization based on physical placement
compile_fusion -from logic_opto -to logic_opto 

# 6. Enable auto pin placement
set_app_options -name compile.auto_floorplan.place_pins -value all 

# 7. Create a collection of ports excluding VDD and VSS
set ports [remove_from_collection [get_ports] {VDD VSS}] 

# 8. Report pin constraints
report_block_pin_constraints -self 

# 9. Place pins using existing routing
place_pins -use_existing_routing -self 

# 10. Initial standard cell placement
compile_fusion -from initial_place -to initial_place 

# 11. Early DRC correction
compile_fusion -from initial_drc -to initial_drc 

# 12. Early timing-driven optimization
compile_fusion -from initial_opto -to initial_opto 

# 13. Final placement and row legalization
compile_fusion -from final_place -to final_place 

# 14. Final physical optimization for CTS readiness
compile_fusion -from final_opto -to final_opto 

# 15. Check legality of the standard cells
check_legality 

# 16. Save the final physical milestone
save_block -as accelerator_top/floorplan

puts "========================================================="
puts " ALL 16 STEPS COMPLETED SUCCESSFULLY! "
puts "========================================================="
exit
