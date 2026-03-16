"""
Author: Kirill Kuroptev
Purpose: This script exports Scigrid data from pypsa into a MATPOWER format.
"""

import pandas as pd
import numpy as np
import pypsa
import os
import networkx as nx
# Load Scigrid data

def load_scigrid_data(snap: int, s_max_pu: float = 1.0,test_ec_opt: bool = False) -> dict:
    o = pypsa.examples.scigrid_de(from_master=True)
    snap = o.snapshots[snap]
    o.lines.s_max_pu = s_max_pu
    o.lines.loc[["316", "527", "602"], "s_nom"] = 1715 # change taken from https://pypsa.readthedocs.io/en/stable/examples/scigrid-redispatch.html
    o.set_snapshots([snap])

    largest_cc = max(nx.connected_components(o.graph()), key=len)

    assert len(largest_cc) == len(o.buses), "Network has more than 1 island!"
    
    # set the loads/generation according to snapshot
    o.loads.p_set = o.loads_t.p_set.loc[snap]
    o.loads.q_set = o.loads_t.q_set.loc[snap]
    o.loads.loc[np.isnan(o.loads.q_set), "q_set"] = 0

    o.generators.p_max_pu = o.generators_t.p_max_pu.loc[snap]
    o.generators.loc[np.isnan(o.generators.p_max_pu), "p_max_pu"] = 1

    # Economic dispatch for testing the loaded network
    if test_ec_opt:
        (opt_stat,sol_stat)=o.optimize(solver_name="gurobi")
        print(f"Economic dispatch Optimization status: {opt_stat}, Solution status: {sol_stat}")
    else: 
        #! If no powerflow is computed the line impedances are not loaded
        o.lpf()
    
    s_base_pypsa_mva = 1 #(o.lines.r_pu.iloc[1]*o.lines.voltage.iloc[1]**2)/(o.lines.r.iloc[1]*1e6)
    print(f"Base power in pypsa: {s_base_pypsa_mva} MVA")
    # if one would have googled, one would find that the base power in scigrid is 1 MVA https://pypsa.readthedocs.io/en/latest/user-guide/design.html
    dic_out = {"pypsa_network": o, "snap": snap, "s_base_pypsa_mva":s_base_pypsa_mva}
    return dic_out

def scigrid_2_matpower(scigrid_dict: dict, file_name: str = 'scigrid_2_matpower',write_bus_mapping: bool = True, mva_base: float = 1000):
    o = scigrid_dict["pypsa_network"]
    snap = scigrid_dict["snap"]
    s_base_pypsa_mva = scigrid_dict["s_base_pypsa_mva"]
    # Write to matpower format
    mpc_comment = f"Converted from scigrid based on snapshot {snap}, storages are omitted"
    snap = str(snap.hour)
    mpc_baseMVA = mva_base 
    factor_baseMVA = mva_base/s_base_pypsa_mva
    #* Bus data
    load_df = o.loads.groupby("bus").agg({'p_set': 'sum', 'q_set': 'sum'}).reset_index()
    load_df.columns = ["Bus", "Pd", "Qd"]
    bus_df = pd.merge(o.buses, load_df,on="Bus", how="left")
    bus_df = bus_df.fillna(0)
    bus_df["Gs"] = 0
    bus_df["Bs"] = 0
    bus_df["area"] = 1
    bus_df["Vm"] = 1
    bus_df["Va"] = 0
    bus_df["baseKV"] = bus_df.v_nom
    bus_df["zone"] = 1
    bus_df["maxVm"] = 1.1
    bus_df["minVm"] = 0.9
    bus_df["type"] = np.where(bus_df["control"] == "Slack", 3, 1)
    bus_df.Pd=bus_df.Pd.round(decimals=0)
    bus_df.Qd=bus_df.Qd.round(decimals=0)
    bus_df=bus_df.filter(items=["Bus", "type","Pd","Qd","Gs","Bs","area","Vm","Va","baseKV","zone","maxVm","minVm"])
    bus_df["Bus_number"] = range(1, len(bus_df)+1)
    bus_df.insert(0, "Bus_number", bus_df.pop("Bus_number"))

    bus_2_number = bus_df.filter(items=["Bus", "Bus_number"])

    if write_bus_mapping:
        bus_2_number_out = pd.merge(bus_2_number,o.buses.filter(items=["x","y","osm_name","operator"]), left_on="Bus", right_index=True, how="left")
        bus_2_number_out.rename(columns={"Bus":"Bus_scigrid","Bus_number":"Bus_number_matpower_file", "x":"Longitude", "y":"Latitude"})
        bus_2_number_out.to_csv(os.path.join(os.getcwd(),"bus_mapping_scigrid_matpower.csv"))

    bus_df.drop(columns=["Bus"], inplace=True)
    #* Generator data
    gen_df = o.generators
    gen_df = pd.merge(gen_df, bus_2_number, left_on="bus", right_on="Bus", how="left")
    gen_df["Pg"] = 0
    gen_df["Qg"] = 0
    gen_df["Qmin"] = 0
    gen_df["Qmax"] = 0
    gen_df["Vg"] = 1
    gen_df["mBase"] = mpc_baseMVA
    gen_df["Status"] = 1
    gen_df["Pmax"] = round(gen_df.p_nom*gen_df.p_max_pu,ndigits=2) # due to p_max_pu being snapshot specific, the case is coupled to the snapshot
    gen_df["Pmin"] = 0
    gen_df=gen_df.filter(items=["Bus_number", "Pg", "Qg", "Qmax","Qmin", "Vg", "mBase", "Status", "Pmax", "Pmin"])
    for i in range(0,11):
        gen_df[f"help_{i}"]=0

    #* Generator cost data
    gen_cost_df = o.generators.filter(items=['start_up_cost','shut_down_cost','marginal_cost_quadratic','marginal_cost']).reset_index()
    gen_cost_df["type"]=2
    gen_cost_df["n"] =3
    gen_cost_df["c0"]=0
    gen_cost_df=gen_cost_df[["type",'start_up_cost','shut_down_cost',"n",'marginal_cost_quadratic','marginal_cost',"c0"]]

    #* Line data
    line_df = o.lines
    line_df = pd.merge(line_df, bus_2_number, left_on="bus0", right_on="Bus", how="left")
    line_df = pd.merge(line_df, bus_2_number, left_on="bus1", right_on="Bus", how="left")
    line_df["r_pu"] = line_df["r_pu"]*factor_baseMVA
    line_df["x_pu"] = line_df["x_pu"]*factor_baseMVA
    line_df["b_pu"] = line_df["b_pu"]/factor_baseMVA
    line_df["rateA"] = line_df.s_nom.round()
    line_df["rateB"] = line_df.s_nom.round()
    line_df["rateC"] = line_df.s_nom.round()
    line_df["ratio"]=0
    line_df["angle"]=0
    line_df["status"]=1
    line_df["angmin"]=-360
    line_df["angmax"]=360

    line_df=line_df.filter(items=["Bus_number_x","Bus_number_y","r_pu", "x_pu","b_pu","rateA","rateB","rateC","ratio","angle","status","angmin","angmax"])
    line_df[line_df.select_dtypes(include=['number']).columns] = line_df.select_dtypes(include=['number']).round(5)
    line_df[["r_pu", "x_pu","b_pu"]] =line_df[["r_pu", "x_pu","b_pu"]].map(lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else x)

    #* Transformer data
    trafo_df = o.transformers
    trafo_df = pd.merge(trafo_df, bus_2_number, left_on="bus0", right_on="Bus", how="left")
    trafo_df = pd.merge(trafo_df, bus_2_number, left_on="bus1", right_on="Bus", how="left")
    trafo_df["r_pu"] = trafo_df["r_pu"]*factor_baseMVA
    trafo_df["x_pu"] = trafo_df["x_pu"]*factor_baseMVA
    trafo_df["b_pu"] = trafo_df["b_pu"]/factor_baseMVA
    trafo_df["rateA"] = trafo_df.s_nom.round()
    trafo_df["rateB"] = trafo_df.s_nom.round()
    trafo_df["rateC"] = trafo_df.s_nom.round()
    trafo_df["ratio"]=0
    trafo_df["angle"]=0
    trafo_df["status"]=1
    trafo_df["angmin"]=-360
    trafo_df["angmax"]=360

    trafo_df=trafo_df.filter(items=["Bus_number_x","Bus_number_y","r_pu", "x_pu","b_pu","rateA","rateB","rateC","ratio","angle","status","angmin","angmax"])
    trafo_df[trafo_df.select_dtypes(include=['number']).columns] = trafo_df.select_dtypes(include=['number']).round(5)
    trafo_df[["r_pu", "x_pu","b_pu"]] =trafo_df[["r_pu", "x_pu","b_pu"]].map(lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else x)

    #* final branch data
    branch_df = pd.concat([line_df, trafo_df], axis=0, ignore_index=True)

    number_cols = bus_df.select_dtypes(include='number').columns
    bus_df[number_cols] = bus_df[number_cols].astype(str)
    number_cols = gen_df.select_dtypes(include='number').columns
    gen_df[number_cols] = gen_df[number_cols].astype(str)
    number_cols = line_df.select_dtypes(include='number').columns
    line_df[number_cols] = line_df[number_cols].astype(str)

    number_cols = gen_cost_df.select_dtypes(include='number').columns
    gen_cost_df[number_cols] = gen_cost_df[number_cols].astype(str)

    mpc_dict = {
        "comment":mpc_comment,
        "baseMVA": mpc_baseMVA,
        "bus": bus_df,
        "gen": gen_df,
        "line":branch_df,
        "cost":gen_cost_df
    }

    #os.path.join(os.getcwd(),f"/scigrid_data/{file_name}.m")
    current_dir = os.getcwd()
    file_path = os.path.join(current_dir,f"{file_name}_hour_{snap}.m")
    with open(file_path, 'w') as f:
            # Write header
            f.write("function mpc = case_scigrid;\n")
            f.write(f"% {mpc_comment} \n")
            f.write("%% MATPOWER Case Format : Version 2\n")
            f.write("mpc.version = '2';\n\n")

            # Write baseMVA
            f.write(f"mpc.baseMVA = {mpc_dict['baseMVA']};\n\n")

            # Write the data
            f.write("%% bus data\n\n")
            f.write("%	bus_i	type	Pd	Qd	Gs	Bs	area	Vm	Va	baseKV	zone	Vmax	Vmin\n")
            f.write("mpc.bus = [\n")
            for _, row in mpc_dict['bus'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")

            f.write("%% generator data\n")
            f.write("%	bus	Pg	Qg	Qmax	Qmin	Vg	mBase	status	Pmax	Pmin	Pc1	Pc2	Qc1min	Qc1max	Qc2min	Qc2max	ramp_agc	ramp_10	ramp_30	ramp_q	apf\n")
            f.write("mpc.gen = [\n")
            for _, row in mpc_dict['gen'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")

            f.write("%% branch data\n")
            f.write("%    fbus    tbus    r    x    b    rateA    rateB    rateC    ratio    angle    status    angmin    angmax\n")
            f.write("mpc.branch = [\n")
            for _, row in mpc_dict['line'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")

            f.write("%%-----  OPF Data  -----%%\n")
            f.write("%% generator cost data\n")
            f.write("%	1	startup	shutdown	n	x1	y1	...	xn	yn\n")
            f.write("%	2	startup	shutdown	n	c(n-1)	...	c0\n")
            f.write("mpc.gencost = [\n")
            for _, row in mpc_dict['cost'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")
    print(f"Matpower-data writen to file {file_path}")


def scigrid_2_matpower_scenario(scigrid_dict: dict, file_name: str = 'scigrid_2_matpower_scenario',write_bus_mapping: bool = True, mva_base: float = 1000, load_factor: float = 1.0, solar_factor: float = 1.0, wind_factor: float = 1.0):
    """Generates a MATPOWER case file from a SciGrid PyPSA network for a specific snapshot with an adjusted load, solar and wind.
    Remark, we have the total installed generation capacity (170 GW, with 80GW in wind and solar) in the scigrid and a varying load profile with a total load between 41 GW and 58 GW. Hence we can scale the available generation and load. """
    o = scigrid_dict["pypsa_network"]
    snap = scigrid_dict["snap"]
    s_base_pypsa_mva = scigrid_dict["s_base_pypsa_mva"]
    # Write to matpower format
    mpc_comment = f"Converted from scigrid based on snapshot {snap}, storages are omitted"
    snap = str(snap.hour)
    mpc_baseMVA = mva_base 
    factor_baseMVA = mva_base/s_base_pypsa_mva
    #* Bus data
    #* scaling of the loads
    o.loads.p_set = o.loads.p_set*load_factor
    o.loads.q_set = o.loads.q_set*load_factor
    load_df = o.loads.groupby("bus").agg({'p_set': 'sum', 'q_set': 'sum'}).reset_index()
    load_df.columns = ["Bus", "Pd", "Qd"]
    bus_df = pd.merge(o.buses, load_df,on="Bus", how="left")
    bus_df = bus_df.fillna(0)
    bus_df["Gs"] = 0
    bus_df["Bs"] = 0
    bus_df["area"] = 1
    bus_df["Vm"] = 1
    bus_df["Va"] = 0
    bus_df["baseKV"] = bus_df.v_nom
    bus_df["zone"] = 1
    bus_df["maxVm"] = 1.1
    bus_df["minVm"] = 0.9
    bus_df["type"] = np.where(bus_df["control"] == "Slack", 3, 1)
    bus_df.Pd=bus_df.Pd.round(decimals=0)
    bus_df.Qd=bus_df.Qd.round(decimals=0)
    bus_df=bus_df.filter(items=["Bus", "type","Pd","Qd","Gs","Bs","area","Vm","Va","baseKV","zone","maxVm","minVm"])
    bus_df["Bus_number"] = range(1, len(bus_df)+1)
    bus_df.insert(0, "Bus_number", bus_df.pop("Bus_number"))

    bus_2_number = bus_df.filter(items=["Bus", "Bus_number"])

    if write_bus_mapping:
        bus_2_number_out = pd.merge(bus_2_number,o.buses.filter(items=["x","y","osm_name","operator"]), left_on="Bus", right_index=True, how="left")
        bus_2_number_out.rename(columns={"Bus":"Bus_scigrid","Bus_number":"Bus_number_matpower_file", "x":"Longitude", "y":"Latitude"})
        bus_2_number_out.to_csv(os.path.join(os.getcwd(),"bus_mapping_scigrid_matpower.csv"))

    bus_df.drop(columns=["Bus"], inplace=True)
    #* Generator data
    gen_df = o.generators
    #* scaling of the renewable generation
    gen_df.loc[gen_df.carrier == "Solar", "p_nom"] = gen_df.p_nom*solar_factor
    gen_df.loc[gen_df.carrier.isin(["Wind Onshore", "Wind Offshore"]), "p_nom"] = gen_df.p_nom * wind_factor
    gen_df = pd.merge(gen_df, bus_2_number, left_on="bus", right_on="Bus", how="left")
    gen_df["Pg"] = 0
    gen_df["Qg"] = 0
    gen_df["Qmin"] = 0
    gen_df["Qmax"] = 0
    gen_df["Vg"] = 1
    gen_df["mBase"] = mpc_baseMVA
    gen_df["Status"] = 1
    gen_df["Pmax"] = round(gen_df.p_nom*gen_df.p_max_pu,ndigits=2) # due to p_max_pu being snapshot specific, the case is coupled to the snapshot
    gen_df["Pmin"] = 0
    gen_df=gen_df.filter(items=["Bus_number", "Pg", "Qg", "Qmax","Qmin", "Vg", "mBase", "Status", "Pmax", "Pmin"])
    for i in range(0,11):
        gen_df[f"help_{i}"]=0

    #* Generator cost data
    gen_cost_df = o.generators.filter(items=['start_up_cost','shut_down_cost','marginal_cost_quadratic','marginal_cost']).reset_index()
    gen_cost_df["type"]=2
    gen_cost_df["n"] =3
    gen_cost_df["c0"]=0
    gen_cost_df=gen_cost_df[["type",'start_up_cost','shut_down_cost',"n",'marginal_cost_quadratic','marginal_cost',"c0"]]

    #* Line data
    line_df = o.lines
    line_df = pd.merge(line_df, bus_2_number, left_on="bus0", right_on="Bus", how="left")
    line_df = pd.merge(line_df, bus_2_number, left_on="bus1", right_on="Bus", how="left")
    line_df["r_pu"] = line_df["r_pu"]*factor_baseMVA
    line_df["x_pu"] = line_df["x_pu"]*factor_baseMVA
    line_df["b_pu"] = line_df["b_pu"]/factor_baseMVA
    line_df["rateA"] = line_df.s_nom.round()
    line_df["rateB"] = line_df.s_nom.round()
    line_df["rateC"] = line_df.s_nom.round()
    line_df["ratio"]=0
    line_df["angle"]=0
    line_df["status"]=1
    line_df["angmin"]=-360
    line_df["angmax"]=360

    line_df=line_df.filter(items=["Bus_number_x","Bus_number_y","r_pu", "x_pu","b_pu","rateA","rateB","rateC","ratio","angle","status","angmin","angmax"])
    line_df[line_df.select_dtypes(include=['number']).columns] = line_df.select_dtypes(include=['number']).round(5)
    line_df[["r_pu", "x_pu","b_pu"]] =line_df[["r_pu", "x_pu","b_pu"]].map(lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else x)

    #* Transformer data
    trafo_df = o.transformers
    trafo_df = pd.merge(trafo_df, bus_2_number, left_on="bus0", right_on="Bus", how="left")
    trafo_df = pd.merge(trafo_df, bus_2_number, left_on="bus1", right_on="Bus", how="left")
    trafo_df["r_pu"] = trafo_df["r_pu"]*factor_baseMVA
    trafo_df["x_pu"] = trafo_df["x_pu"]*factor_baseMVA
    trafo_df["b_pu"] = trafo_df["b_pu"]/factor_baseMVA
    trafo_df["rateA"] = trafo_df.s_nom.round()
    trafo_df["rateB"] = trafo_df.s_nom.round()
    trafo_df["rateC"] = trafo_df.s_nom.round()
    trafo_df["ratio"]=0
    trafo_df["angle"]=0
    trafo_df["status"]=1
    trafo_df["angmin"]=-360
    trafo_df["angmax"]=360

    trafo_df=trafo_df.filter(items=["Bus_number_x","Bus_number_y","r_pu", "x_pu","b_pu","rateA","rateB","rateC","ratio","angle","status","angmin","angmax"])
    trafo_df[trafo_df.select_dtypes(include=['number']).columns] = trafo_df.select_dtypes(include=['number']).round(5)
    trafo_df[["r_pu", "x_pu","b_pu"]] =trafo_df[["r_pu", "x_pu","b_pu"]].map(lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else x)

    #* final branch data
    branch_df = pd.concat([line_df, trafo_df], axis=0, ignore_index=True)

    number_cols = bus_df.select_dtypes(include='number').columns
    bus_df[number_cols] = bus_df[number_cols].astype(str)
    number_cols = gen_df.select_dtypes(include='number').columns
    gen_df[number_cols] = gen_df[number_cols].astype(str)
    number_cols = line_df.select_dtypes(include='number').columns
    line_df[number_cols] = line_df[number_cols].astype(str)

    number_cols = gen_cost_df.select_dtypes(include='number').columns
    gen_cost_df[number_cols] = gen_cost_df[number_cols].astype(str)

    mpc_dict = {
        "comment":mpc_comment,
        "baseMVA": mpc_baseMVA,
        "bus": bus_df,
        "gen": gen_df,
        "line":branch_df,
        "cost":gen_cost_df
    }

    #os.path.join(os.getcwd(),f"/scigrid_data/{file_name}.m")
    current_dir = os.getcwd()
    file_path = os.path.join(current_dir,f"{file_name}_hour_{snap}.m")
    with open(file_path, 'w') as f:
            # Write header
            f.write("function mpc = case_scigrid;\n")
            f.write(f"% {mpc_comment} \n")
            f.write("%% MATPOWER Case Format : Version 2\n")
            f.write("mpc.version = '2';\n\n")

            # Write baseMVA
            f.write(f"mpc.baseMVA = {mpc_dict['baseMVA']};\n\n")

            # Write the data
            f.write("%% bus data\n\n")
            f.write("%	bus_i	type	Pd	Qd	Gs	Bs	area	Vm	Va	baseKV	zone	Vmax	Vmin\n")
            f.write("mpc.bus = [\n")
            for _, row in mpc_dict['bus'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")

            f.write("%% generator data\n")
            f.write("%	bus	Pg	Qg	Qmax	Qmin	Vg	mBase	status	Pmax	Pmin	Pc1	Pc2	Qc1min	Qc1max	Qc2min	Qc2max	ramp_agc	ramp_10	ramp_30	ramp_q	apf\n")
            f.write("mpc.gen = [\n")
            for _, row in mpc_dict['gen'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")

            f.write("%% branch data\n")
            f.write("%    fbus    tbus    r    x    b    rateA    rateB    rateC    ratio    angle    status    angmin    angmax\n")
            f.write("mpc.branch = [\n")
            for _, row in mpc_dict['line'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")

            f.write("%%-----  OPF Data  -----%%\n")
            f.write("%% generator cost data\n")
            f.write("%	1	startup	shutdown	n	x1	y1	...	xn	yn\n")
            f.write("%	2	startup	shutdown	n	c(n-1)	...	c0\n")
            f.write("mpc.gencost = [\n")
            for _, row in mpc_dict['cost'].iterrows():
                f.write("\t" + "\t".join(map(str, row)) + ";\n")
            f.write("];\n")
    print(f"Matpower-data writen to file {file_path}")

#* creating the matpower files for all 24 snapshots
# for i in range(24):
#     scigrid_dict = load_scigrid_data(i)
#     scigrid_2_matpower(scigrid_dict)

#* creating matpower files for scenario analysis
#* remark, we have the total installed generation capacity (170 GW, with 80GW in wind and solar) in the scigrid and a varying load profile with a total load between 41 GW and 58 GW. Hence we can scale the available generation and load. 
#* scenario data from https://www.energy-charts.info/charts/power/chart.htm?c=DE&source=public&interval=year&year=2014
#! note that the scigrid generation data is based on 2014 data, hence the scenarios are also based on 2014 data


#* case with medium loads and high renewables => summer day
scigrid_dict = load_scigrid_data(5)
scigrid_2_matpower_scenario(scigrid_dict, file_name="scigrid_scenario_MLHR", load_factor=1.5, solar_factor=0.68, wind_factor=0.82)

#* case with high loads and low renewables => winter evening with dunkelflaute
scigrid_dict = load_scigrid_data(5)
scigrid_2_matpower_scenario(scigrid_dict, file_name="scigrid_scenario_HLLR", load_factor=1.8, solar_factor=0, wind_factor=0.05)

#* case with low loads and high wind => winter night
scigrid_dict = load_scigrid_data(5)
scigrid_2_matpower_scenario(scigrid_dict, file_name="scigrid_scenario_LLNP", solar_factor=0, wind_factor=0.82)

#* case with low loads and high pv => summer day
scigrid_dict = load_scigrid_data(5)
scigrid_2_matpower_scenario(scigrid_dict, file_name="scigrid_scenario_LLLW", solar_factor=0.68, wind_factor=0.05)
