#####################################################################
## Clock Tree Synthesis (CTS) - Advanced Flow
#####################################################################

# 1. Create NDR (Non-Default Routing) Rule
create_routing_rule CLK_NDR \
  -default_reference_rule \
  -multiplier_width 2 \
  -spacings {M2 0.052 M3 0.052 M4 0.08 M5 0.08} \
  -shield \
  -shield_spacings {M2 0.026 M3 0.026 M4 0.04 M5 0.04} \
  -snap_to_track

# 2. Restrict Routing Layers
set_clock_routing_rules -rules CLK_NDR \
  -min_routing_layer M2 \
  -max_routing_layer M5

# 3. Set Target Skew
set_clock_tree_options -clocks [all_clocks] -target_skew 0.1

# 4. Clock Optimization Flow
clock_opt -to build_clock
clock_opt -from build_clock -to route_clock
clock_opt -to final_opto

# 5. Remove Global Routes and Add Shielding
remove_routes -global_route
set clock_nets [get_nets -hierarchical -filter "net_type == clock"]
create_shields -nets ${clock_nets} -with_ground VSS

# 6. Reconnect Power Nets and Verification
connect_pg_net -net VDD [get_pins -hierarchical */VDD]
connect_pg_net -net VSS [get_pins -hierarchical */VSS]
check_legality
