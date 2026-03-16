"""
Author: Kirill Kuroptev
Purpose: This script tests the to a matpower file exported Scigrid data from pypsa.
"""

import Pkg; Pkg.activate("cso_segmentation/Project.toml")
using JuMP
import HiGHS
using PowerModels
using DataFrames
using CSV

network_data = parse_file("Scigrid_data/test_run/scigrid_2_matpower.m")

ccs = calc_connected_components(network_data)
println("Connected components found in scigrid data $(length(ccs))")
@assert length(ccs)==1 "More than 1 connected component!"
gen_sum = 0
for key in keys(network_data["gen"]) gen_sum += network_data["gen"][key]["pmax"] end

load_sum = 0
for key in keys(network_data["load"]) load_sum += network_data["load"][key]["pd"] end

println("generation ttl $gen_sum, load ttl $load_sum")
@assert gen_sum > load_sum "Load exceeds installed generation"

network_data["gen"]["306"]
network_data["branch"]["1"]
network_data["bus"]["1"]
network_data["load"]["1"]


res_dcopf = solve_opf(network_data, DCPPowerModel, HiGHS.Optimizer)

println("Termination status of DC Opf $(res_dcopf["termination_status"])")
@assert res_dcopf["termination_status"] == JuMP.OPTIMAL "DCOPF not solved to optimality"

#! Caveat, the following is a very strict "test" on the objective value and only valid for the snapshot 2011-01-01 01:00:00
obj_val_pypsa = 2.737648879e05

println("Relative difference between pypsa DC OPF WITH STORAGES and PowerModels DC OPF WITHOUT STORAGES \n
        $(res_dcopf["objective"]/obj_val_pypsa -1 )")
#* load the charging point data and inspect difference between buses numbered 1-n in py and by make_basic_network

network_data_basic = make_basic_network(network_data)
Charging_stations = DataFrame(CSV.File("Simulation_setting/Charging_Stations_BNetzA_2025-07-18_engl_brief.csv"));
Charging_stations.Bus_scigrid_NC_euclidean = string.(Charging_stations.Bus_scigrid_NC_euclidean);
Bus_mapping = DataFrame(CSV.File("Scigrid_data/test_run/bus_mapping_scigrid_matpower.csv"));
Bus_mapping.Bus_number = string.(Bus_mapping.Bus_number);
Charging_stations = leftjoin(Charging_stations, Bus_mapping[!,[:Bus, :Bus_number]], on=[:Bus_scigrid_NC_euclidean =>:Bus]);    

x = unique(Charging_stations.Bus_number)
y = string.(keys(network_data_basic["bus"]))
setdiff(x,y)

#! no difference, as the bus numbering is the same, as the buses are already numbered 1-n in py.
