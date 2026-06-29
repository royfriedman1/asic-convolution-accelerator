
remove_pg_via_master_rules -all 
remove_pg_patterns -all 
remove_pg_strategies -all 
remove_pg_strategy_via_rules -all 


# Mesh M5 (Vertical)
create_pg_mesh_pattern M5_PG -layers { {vertical_layer: M5} {width: 1.6} {spacing: interleaving} {pitch: 16} } 
# Mesh M6 (Horizontal)
create_pg_mesh_pattern M6_PG -layers { {horizontal_layer: M6} {width: 1.6} {spacing: interleaving} {pitch: 16} } 


set_pg_strategy M5_PG_Strategy -core -pattern {{name: M5_PG} {nets:{VSS VDD}}}
set_pg_strategy M6_PG_Strategy -core -pattern {{name: M6_PG} {nets:{VSS VDD}}}


compile_pg -strategies {M5_PG_Strategy M6_PG_Strategy}


connect_pg_net -net VDD [get_pins -hierarchical */VDD] 
connect_pg_net -net VSS [get_pins -hierarchical */VSS]
