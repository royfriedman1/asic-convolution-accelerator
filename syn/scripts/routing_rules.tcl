# --- Setup Application Options ---
set_app_options -name route.global.force_rerun_after_global_route_opt -value true 
set_app_options -name route.global.timing_driven -value true 
set_app_options -name route.track.timing_driven -value true 
set_app_options -name route.detail.timing_driven -value true 

# --- TSMC 28nm Routing Options ---
set_app_options -name route.common.connect_within_pins_by_layer_name -value {{M1 via_wire_standard_cell_pins} {M2 off} {M3 off} {M4 off} {M5 off} {M6 off} {M7 off} {M8 off}}
set_app_options -name route.common.net_max_layer_mode -value allow_pin_connection
set_app_options -name route.common.global_max_layer_mode -value allow_pin_connection
set_app_options -name route.common.net_min_layer_mode -value soft
set_app_options -name route.common.global_min_layer_mode -value allow_pin_connection
set_app_options -name route.common.number_of_vias_under_net_min_layer -value 5
set_app_options -name route.common.number_of_vias_over_net_max_layer -value 5
set_app_options -name route.common.number_of_vias_over_global_max_layer -value 5
set_app_options -name route.common.rotate_default_vias -value false
set_app_options -name route.common.route_top_boundary_mode -value stay_half_min_space_inside
set_app_options -name route.common.shielding_nets -value {}
set_app_options -name route.common.threshold_noise_ratio -value 0.20

# --- Routing Constraints ---
# Restrict to M1-M6
set_ignored_layers -min_routing_layer M1 -max_routing_layer M6
