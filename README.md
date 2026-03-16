# Defending the power grid by segmenting the EV charging cyber infrastructure

This repo contains the case study files used within the numerical case study on the near-real-world case of Germany in our paper *Defending the power grid by segmenting the EV charging cyber infrastructure*.

```
Authors (paper): Kirill Kuroptev, Florian Steinke, Efthymios Karangelos
Author (software): Kirill Kuroptev
Venue to be presented: PSCC 2026
```
**In case you use the code or curated data sets, please cite our work using the BibTeX:**

```
@inproceedings{kuroptev2025segmentation,
  author    = {Kirill Kuroptev, Florian Steinke, Efthymios Karangelos},
  title     = {Defending the power grid by segmenting the EV charging cyber infrastructure},
  year      = {2025},
  note      = {Accepted for presentation at the PSCC 2026}
}
```


## Data sources

We thank the authors of the data sources, we have used to create near-real-world case of Germany. 
We use the *Scigrid data set* to model the German power system, i.e., grid, loads, generators. 
We use the official charging station data of the BNetzA to obtain the spatial location and operator of charging stations in Germany.

**Scigrid data set:**
- We obtained the Scigrid data using [`PyPSA`](https://doi.org/10.5281/zenodo.14824654). 
- The Scigrid data set was created by [Matke et al., 2017](https://link.springer.com/chapter/10.1007/978-3-319-51795-7_11).

**Charging station data:**
Official charging station data of the BNetzA (German regulating authority for the power sector), obtained on 30.07.2025. The data is provided under this [link](https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/E-Mobilitaet/start.html). You find it in the download section. 

## Mapping charging station data to the Scigrid

We explore the charging station data and map it to the buses in the Scigrid model in the [mapping notebook](Real_data/mapping_eda_charging_stations_2_buses.ipynb). 

__Mapping logic:__ We use the [Nearest Centroid Classifier](https://scikit-learn.org/stable/modules/neighbors.html#nearest-centroid-classifier) centered at the *buses containing 110kV substations in the Scrigrid* and assign the charging stations according to the centroids/buses. 

## Creating the grid scenarios used in the paper

We use the script [sigrid_to_matpower.py](Scigrid_data/scigrid_to_matpower.py) to create the grid scenarios (MLHR, HLLR, LLNP, LLLW) used in our paper. The intentions behind the scenarios are explained in our paper. As we used PowerModels data structure in our optimization problem, it was necessary to export the Scigrid data set from PyPSA to a matpower case.
In general, we omit storages in our export of the Scigrid, and modify three branch parameters of the initial data. For more details see in the script.

We "test" our matpower export by loading one, running the DC-OPF of PowerModels, and compare the objective values. The comparing value is obtained from a DC-OPF in PyPSA. The objective values differ by 0.25%, as the one computed by PowerModels does not include storages and is therefore slightly higher. For more details, we refer to [test_scigrid_to_matpower.jl](Scigrid_data/test_run/test_scigrid_to_matpower.jl). 


## Research ideas based on the data sets

Besides our work, we think that these curated data sets can contribute to research on 

- congestion management by shifting the charging and discharging of EVs; 
- local marginal pricing of charging stations to incentive charging behavior (on long hauls);
- grid-informed planning of new charging stations.



## Detailed code structure

```
CSO_Segmentation/
├── LICENSE                            # License file
├── requirements.txt                   # Python dependencies
│
├── cso_segmentation/                  # Julia package for CSO segmentation
│   ├── Project.toml                   # Julia project dependencies
│   └── Manifest.toml                  # Julia dependency lock file
│
├── Real_data/                         # Raw and processed EV charging station data
│   ├── Ladesaeulenregister_BNetzA_2025-07-18.xlsx          # Source data from BNetzA
│   ├── Ladesaeulenregister_BNetzA_2025-07-18_engl_brief.csv # Cleaned English version with mapping to Scigrid buses
│   ├── Ladesaeulenregister_BNetzA_2025-07-18_dt_kurz.csv   # Cleaned German version with mapping to Scigrid buses
│   └── mapping_2_eda_charging_stations_2_buses.ipynb       # EDA & bus mapping notebook
│
├── scigrid_data/                      # SciGRID power grid data and conversion scripts
│   ├── scigrid_to_matpower.py         # Script to convert SciGRID data to MATPOWER format
│   ├── raw/
│   │   └── buses.csv                  # Raw SciGRID bus data
│   ├── hourly_files/                  # MATPOWER case files for each hour (0–23)
│   │   ├── scigrid_2_matpower_hour_0.m
│   │   ├── ...
│   │   └── scigrid_2_matpower_hour_23.m
│   └── test_run/                      # Test scripts and validation files
│       ├── scigrid_2_matpower.m       # MATPOWER test case
│       ├── bus_mapping_scigrid_matpower.csv  # Bus index mapping
│       └── test_scigrid_to_matpower.jl      # Julia test script
│
└── Simulation_Setting/                # Scenario files for the case study simulations
    ├── Charging_Stations_BNetzA_2025-07-18_engl_brief.csv  # Charging stations with mapping to Scigrid buses used in simulation    
        └── case_study_files/          # MATPOWER scenario files for 4 representative grid settings
        ├── scigrid_scenario_HLLR.m    # High load, high renewables
        ├── scigrid_scenario_LLLW.m    # Low load, low wind
        ├── scigrid_scenario_LLNP.m    # Low load, no PV
        └── scigrid_scenario_MLHR.m    # Medium load, high renewables
``` 